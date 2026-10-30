"""Agents, validators, fallbacks and the LLM gateway (spec 7.9, 7.10; M6 acceptance).

Tests run with LLM_MODE=template. Where an LLM answer matters, `fake_llm` replaces the
gateway with canned responses so the validators can be exercised deterministically.
"""
import json
from datetime import date

import pytest
from sqlmodel import select

from app import db
from app.adapters import llm
from app.agents import recovery
from app.agents.base import rupee_figures
from app.agents.counter import Action, CounterOutput, validate as validate_counter
from app.agents.recovery import PlanItem, ReplyOut
from app.models import Entry, Message, Promise, Repayment

TODAY = date(2026, 10, 26)


def ev(client, type_, expect=200, **payload):
    r = client.post("/api/events", json={"type": type_, "payload": payload})
    assert r.status_code == expect, r.text
    return r.json()


def snap(client):
    return client.get("/api/snapshot").json()


@pytest.fixture
def fake_llm(monkeypatch):
    """Queue of canned contents per agent name; anything not queued behaves like 'no LLM'."""
    queue: dict[str, list[str]] = {}

    async def complete(agent, prompt_version, key_input, messages, response_format=None, mode=None):
        if queue.get(agent):
            return llm.GatewayResult(queue[agent].pop(0), "live", 12.0, "k")
        return llm.GatewayResult(None, "template", 0.0, "k")

    async def no_repair(messages, fmt):
        return None

    monkeypatch.setattr(llm, "complete", complete)
    monkeypatch.setattr(llm, "live_repair", no_repair)
    return queue


# ---------------------------------------------------------------- Counter Agent

def test_counter_fallback_udhaar_text(fresh):
    ev(fresh, "udhaar_spoken", store_id="S1", text="Ramesh 500 udhaar")
    top = snap(fresh)["soundbox"]["top"]
    assert (top["customer_id"], top["credit_now"], top["collect_now"]) == ("C_RAMESH", 400, 100)


def test_counter_fallback_cash_and_two_clauses(fresh):
    ev(fresh, "cash_reported", store_id="S1", text="Ramesh ne 300 cash diye")
    with db.session() as s:
        r = s.exec(select(Repayment).where(Repayment.customer_id == "C_RAMESH").order_by(Repayment.id.desc())).first()
        assert (r.amount, r.source) == (300, "cash")
    out = ev(fresh, "udhaar_spoken", store_id="S1", text="Priya 200 aur Meena 150 udhaar")
    assert len(out["child_event_ids"]) == 2
    with db.session() as s:
        assert {(e.customer_id, e.amount) for e in s.exec(select(Entry).where(Entry.state == "proposed")).all()} == {
            ("C_PRIYA", 200), ("C_MEENA", 150)}


def test_counter_ambiguous_name_asks(fresh):
    ev(fresh, "new_customer", store_id="S1", name="Ramesh Bhat", mobile="9000022222")
    ev(fresh, "udhaar_spoken", store_id="S1", text="Ramesh 100 udhaar")
    top = snap(fresh)["soundbox"]["top"]
    assert top["band"] == "clarify" and {c["id"] for c in top["candidates"]} == {"C_RAMESH", "C_N001"}
    assert "Ramesh Kumar" in top["text"] and "Ramesh Bhat" in top["text"]


def test_counter_unknown_name_starts_new_customer(fresh):
    ev(fresh, "udhaar_spoken", store_id="S1", text="Zubin 250 udhaar")
    assert snap(fresh)["soundbox"]["front"] == {"mode": "new_customer", "name": "Zubin", "amount": 250}


def test_counter_validator_drops_invented_ids_and_amounts():
    customers = [{"id": "C_RAMESH", "name": "Ramesh Kumar", "aliases": []}]
    out, notes = validate_counter(CounterOutput(actions=[
        Action(type="udhaar", customer_id="C_FAKE", candidate_ids=["C_FAKE", "C_RAMESH"], amount=340),
        Action(type="udhaar", customer_id="C_RAMESH", amount=900_000)]), customers)
    assert out.actions[0].customer_id == "C_RAMESH"  # only valid candidate left
    assert out.actions[1].type == "unknown" and out.actions[1].amount is None
    assert len(notes) == 2


def test_counter_llm_output_is_used_when_valid(fresh, fake_llm):
    fake_llm["counter"] = [json.dumps({"actions": [{"type": "udhaar", "customer_id": "C_PRIYA", "name_heard": "Priya",
                                                    "candidate_ids": ["C_PRIYA"], "amount": 340}],
                                       "clarify_question": None})]
    ev(fresh, "udhaar_spoken", store_id="S1", text="woh doctor madam ka 340 likh do")  # fallback cannot resolve this
    assert snap(fresh)["soundbox"]["top"]["customer_id"] == "C_PRIYA"


# ---------------------------------------------------------------- Recovery Agent

def beat_2(client):
    ev(client, "udhaar_spoken", store_id="S1", customer_id="C_RAMESH", amount=500)
    ev(client, "customer_confirm", token=snap(client)["soundbox"]["front"]["token"], device_id="dev-ramesh")


def test_recovery_beat_3(fresh):
    beat_2(fresh)
    ev(fresh, "nudges_requested", store_id="S1", customer_ids=["C_RAMESH"])
    [d] = snap(fresh)["merchant"]["drafts"]
    assert rupee_figures(d["text"]) == {1_900}
    assert snap(fresh)["customer"]["messages"] == []  # the customer sees nothing until the merchant approves
    ev(fresh, "nudges_approved", message_ids=[d["message_id"]])
    assert snap(fresh)["customer"]["messages"][0]["text"] == d["text"]

    ev(fresh, "customer_reply", customer_id="C_RAMESH", store_id="S1",
       text="Salary 1 tareekh ko aati hai, tab pura de dunga")
    with db.session() as s:
        p = s.exec(select(Promise).where(Promise.customer_id == "C_RAMESH")).one()
        assert (p.amount, p.date, p.status) == (1_900, date(2026, 11, 1), "open")
        reply = s.exec(select(Message).where(Message.customer_id == "C_RAMESH").order_by(Message.id.desc())).first()
        ag = reply.agent_output
        assert (ag["intent"], ag["suggest_mandate"], ag["escalate"]) == ("promise", True, False)
    msgs = snap(fresh)["customer"]["messages"]
    assert [a["type"] for a in msgs[-1]["actions"]] == ["setup_autopay", "pay"]
    [t] = snap(fresh)["merchant"]["threads"]
    assert t["promise"]["label"] == "Promised ₹1,900 on 1 Nov" and t["intent"] == "promise"

    # Ramesh taps "Set up auto-pay"
    ev(fresh, "mandate_created", customer_id="C_RAMESH", store_id="S1", cap=3_000, window_start_day=1, window_end_day=5)
    assert snap(fresh)["customer"]["score"] == 665


def test_collector_policy_and_cooldown(fresh):
    ev(fresh, "nudges_requested", store_id="S1", customer_ids=["C_PRIYA"])  # owes nothing
    assert snap(fresh)["merchant"]["drafts"] == []
    ev(fresh, "nudges_requested", store_id="S1")  # policy: overdue ≥ 7 days
    drafts = snap(fresh)["merchant"]["drafts"]
    assert {d["customer_id"] for d in drafts} == {"C_DEEPAK", "C_VIKRAM", "C_RAMESH"}
    ev(fresh, "nudges_approved", message_ids=[d["message_id"] for d in drafts])
    ev(fresh, "nudges_requested", store_id="S1", customer_ids=[drafts[0]["customer_id"]])  # 3-day cooldown
    assert snap(fresh)["merchant"]["drafts"] == []


def test_dispute_reply_escalates(fresh):
    ev(fresh, "customer_reply", customer_id="C_VIKRAM", store_id="S1", text="Maine itna nahi liya, galat hai")
    [t] = snap(fresh)["merchant"]["threads"]
    assert t["escalated"] is True and t["intent"] == "dispute"


def test_draft_validator():
    assert recovery.validate_draft("Namaste, ₹2,000 baaki hai.", 2_000) is None
    assert "invented" in recovery.validate_draft("₹2,000 baaki, ₹50 late fee", 2_000)
    assert "missing" in recovery.validate_draft("Aapka udhaar baaki hai", 2_000)
    assert "too long" in recovery.validate_draft("₹2,000 " + "x" * 400, 2_000)


def test_draft_llm_invention_falls_back(fresh, fake_llm):
    fake_llm["recovery_draft"] = [json.dumps({"message": "Ramesh ji, ₹1,900 + ₹100 penalty bhejiye", "lang": "hi-IN"})]
    beat_2(fresh)
    ev(fresh, "nudges_requested", store_id="S1", customer_ids=["C_RAMESH"])
    [d] = snap(fresh)["merchant"]["drafts"]
    assert "penalty" not in d["text"] and rupee_figures(d["text"]) == {1_900}


def test_reply_validator_policy():
    out, _ = recovery.validate_reply(ReplyOut(intent="promise", promise=PlanItem(amount=2_000, date=date(2026, 12, 15)),
                                              reply_message="ok"), 2_000, TODAY, False)
    assert out.promise is None and out.escalate and out.intent == "other"
    bad_plan = [PlanItem(amount=200, date=date(2026, 11, 1)), PlanItem(amount=1_800, date=date(2026, 11, 10))]
    out, _ = recovery.validate_reply(ReplyOut(intent="plan_request", proposed_plan=bad_plan), 2_000, TODAY, False)
    assert out.proposed_plan == [] and out.escalate  # first part < 25%
    good = [PlanItem(amount=1_000, date=date(2026, 11, 1)), PlanItem(amount=1_000, date=date(2026, 11, 15))]
    out, _ = recovery.validate_reply(ReplyOut(intent="plan_request", proposed_plan=good), 2_000, TODAY, False)
    assert len(out.proposed_plan) == 2 and not out.escalate
    out, _ = recovery.validate_reply(ReplyOut(intent="promise", promise=PlanItem(amount=2_000, date=date(2026, 11, 1)),
                                              suggest_mandate=True, reply_message="₹5,000 kal"), 2_000, TODAY, True)
    assert out.suggest_mandate is False and out.reply_message == ""  # invented ₹5,000 → template reply


def test_reply_fallback_contract():
    out = recovery.reply_fallback("Salary 1 tareekh ko aati hai, tab pura de dunga", 2_000, TODAY, False)
    assert out.intent == "promise" and out.promise == PlanItem(amount=2_000, date=date(2026, 11, 1))
    assert out.suggest_mandate is True


# ---------------------------------------------------------------- Reconciliation Agent

KAMALA = dict(store_id="S1", payer_vpa="9876500000@ptyes", payer_name="Kamala Kumar", amount=500,
              remark="Ramesh ka udhaar")


def test_recon_agent_confident_match_auto_applies(fresh, fake_llm):
    fake_llm["recon"] = [json.dumps({"customer_id": "C_RAMESH", "confidence": 0.91,
                                     "reason": "remark names Ramesh; same surname"})]
    ev(fresh, "upi_payment", **KAMALA)
    assert snap(fresh)["merchant"]["pending_matches"] == []
    with db.session() as s:
        r = s.exec(select(Repayment).where(Repayment.customer_id == "C_RAMESH").order_by(Repayment.id.desc())).first()
        assert (r.matched_by, r.match_confidence, r.amount) == ("agent", 0.91, 500)


def test_recon_agent_cannot_pick_outside_candidates(fresh, fake_llm):
    fake_llm["recon"] = [json.dumps({"customer_id": "C_2001", "confidence": 0.99, "reason": "?"})]
    ev(fresh, "upi_payment", **KAMALA)
    [pm] = snap(fresh)["merchant"]["pending_matches"]
    assert pm["agent"]["customer_id"] is None


# ---------------------------------------------------------------- Munim Agent

QUESTION = "Friday ko Sharma ko 15,000 kaise dunga?"


def test_munim_template_contract(fresh):
    r = fresh.post("/api/agents/munim/ask", json={"store_id": "S1", "question": QUESTION, "lang": "hi-IN"}).json()
    assert [st["tool"] for st in r["steps"]][:3] == ["get_forecast", "list_collectable_dues", "check_advance_eligibility"]
    figs = rupee_figures(r["answer"])
    assert {15_000, 10_000, 5_000, 75} <= figs
    assert "koi udhaar wapas aane ki ummeed nahi" in r["answer"]
    types = {a["type"]: a["params"] for a in r["actions"]}
    assert types["offer_advance"] == {"bill_id": "B1"} and types["send_nudges"]["customer_ids"]
    assert r["source"] == "template"
    assert snap(fresh)["merchant"]["munim_last"]["answer"] == r["answer"]


def test_munim_llm_tool_loop_accepted(fresh, fake_llm):
    fake_llm["munim"] = [
        json.dumps({"tool": "check_advance_eligibility", "args": {"bill_id": "B1"}}),
        json.dumps({"final": {"answer": "₹5,000 kam hai; ₹5,000 ka advance mil sakta hai, fee ₹75.",
                              "actions": [{"type": "offer_advance", "params": {"bill_id": "B1"}}]}}),
    ]
    r = fresh.post("/api/agents/munim/ask", json={"question": QUESTION, "lang": "hi-IN"}).json()
    assert r["source"] == "live" and r["answer"].startswith("₹5,000 kam hai")


def test_munim_invented_number_rejected(fresh, fake_llm):
    fake_llm["munim"] = [json.dumps({"final": {"answer": "Aapko ₹7,777 ka loan milega.",
                                               "actions": [{"type": "transfer_money", "params": {}}]}})]
    r = fresh.post("/api/agents/munim/ask", json={"question": QUESTION, "lang": "hi-IN"}).json()
    assert r["source"] == "template" and 7_777 not in rupee_figures(r["answer"])
    assert {a["type"] for a in r["actions"]} <= {"send_nudges", "offer_advance", "open_customer"}


def test_munim_other_intents(fresh):
    r = fresh.post("/api/agents/munim/ask", json={"question": "Vikram ka kitna baaki hai?", "lang": "hi-IN"}).json()
    assert "₹2,500" in r["answer"] and r["actions"][0]["type"] == "open_customer"
    r = fresh.post("/api/agents/munim/ask", json={"question": "Kaun kaun overdue hai?", "lang": "en-IN"}).json()
    assert r["actions"][0]["type"] == "send_nudges"


def test_briefing_rephrase_must_keep_numbers(fresh, fake_llm):
    fake_llm["briefing"] = [json.dumps({"text": "Suprabhat! Aaj sab theek hai, ₹1 bhi kam nahi."})]
    ev(fresh, "advance_day", days=1)
    b = snap(fresh)["merchant"]["briefing"]
    assert b["source"] == "template" and "₹1 " not in b["text"]


# ---------------------------------------------------------------- gateway

def test_gateway_record_then_replay(tmp_path, monkeypatch):
    import asyncio

    class FakeProvider:
        name = "fake"

        async def chat(self, messages, response_format, timeout):
            return '{"ok": true}'

    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "providers", lambda: [FakeProvider()])
    msgs = [{"role": "user", "content": "hi"}]
    rec = asyncio.run(llm.complete("t", "v1", {"x": 1}, msgs, mode="record"))
    assert rec.source == "live" and (tmp_path / f"{rec.key}.json").exists()
    monkeypatch.setattr(llm, "providers", lambda: [])
    rep = asyncio.run(llm.complete("t", "v1", {"x": 1}, msgs, mode="replay"))
    assert (rep.content, rep.source) == ('{"ok": true}', "replay")
    miss = asyncio.run(llm.complete("t", "v1", {"x": 2}, msgs, mode="auto"))
    assert (miss.content, miss.source) == (None, "template")
    assert asyncio.run(llm.complete("t", "v1", {"x": 1}, msgs, mode="template")).content is None
