"""Reminders, the reply contract and auto-pay (spec §4.9, §4.11), with AI off."""
import asyncio

from conftest import counter, ok

from app.agents import recovery


def test_reply_contract_with_ai_off(world):
    counter(world, "C_RAMESH", 340)  # Ramesh takes ₹200 more → dues ₹1,900
    token = ok(world["soundbox"].get("/api/soundbox/state"))["front"]["token"]
    ok(world["C_RAMESH"].post(f"/api/requests/{token}/confirm", json={"pay_method": "upi", "device_id": "d"}))
    ok(world["merchant"].post("/api/merchant/growth/A_REMIND/approve"))
    reminder = ok(world["C_RAMESH"].get("/api/customer/messages"))[0]["messages"][0]["text"]
    assert "₹1,900" in reminder and "19 din se" in reminder
    out = ok(world["C_RAMESH"].post("/api/customer/messages/reply",
                                    json={"store_id": "S1", "text": "Salary 1 tareekh ko aati hai, tab de dunga"}))
    assert out == {"intent": "promise", "promise": {"amount": 1_900, "date": "2026-11-01"}}
    last = ok(world["C_RAMESH"].get("/api/customer/messages"))[0]["messages"][-1]
    assert [a["type"] for a in last["actions"]] == ["setup_autopay", "pay"]
    assert ok(world["merchant"].get("/api/merchant/collect"))["promises"] == [
        {"customer": "Ramesh Kumar", "amount": 1_900, "date": "2026-11-01"}]


def test_keyword_rules():
    assert recovery.rule_interpret("Salary 1 tareekh ko aati hai, tab de dunga", 1_900, False) == {
        "intent": "promise", "promise": {"amount": 1_900, "date": "2026-11-01"}, "suggest_mandate": True,
        "escalate": False}
    assert recovery.rule_interpret("galat hai", 1_900, False)["intent"] == "dispute"
    assert recovery.rule_interpret("hospital mein hoon", 1_900, False)["escalate"] is True
    assert recovery.rule_interpret("abhi bhej raha hoon", 1_900, False)["intent"] == "pay_now"
    assert asyncio.run(recovery.interpret("hmm", "Ramesh Kumar", 1_900, False, "hi-IN"))["intent"] == "other"


def test_draft_validator():
    assert recovery.valid_draft("Aapka ₹1,900 baaki hai", 1_900)
    assert not recovery.valid_draft("₹1,900 + ₹100 fee", 1_900)


def test_autopay_schedule(world):
    sch = ok(world["C_RAMESH"].post("/api/customer/mandates", json={"store_id": "S1", "cap": 3_000, "collection_day": 2}))
    assert (sch["next_collection"], sch["notice_on"], sch["cap"], sch["amount_now"]) == ("2026-11-02", "2026-11-01", 3_000, 1_700)
    assert world["C_RAMESH"].post("/api/customer/mandates", json={"store_id": "S1"}).status_code == 409
    assert ok(world["merchant"].get("/api/merchant/collect"))["schedules"][0]["customer"] == "Ramesh Kumar"
