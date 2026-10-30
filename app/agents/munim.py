"""Munim Agent (spec 7.9.4): the shopkeeper's copilot, plus the spoken morning briefing.

Tool loop: the model returns either {"tool", "args"} or {"final": {answer, actions}}; at most
4 tool steps, then a forced final. Tools are read-only. The validator requires every ₹ figure
in the answer to appear in a tool result from this conversation and every action to be one
of the allowed types with real ids; otherwise the answer is rebuilt from the tool results by
the deterministic planner, which is also the fallback when no LLM is available.
"""
import json
import re
import time
from datetime import date, timedelta
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import clock, state
from app.adapters import llm
from app.agents.base import PROMPT_VERSION, call_llm, prompt, rupee_figures
from app.core import advance, briefing, collector, forecast, ledger, risk, score
from app.core.money import inr
from app.models import Bill, Customer, Sale, StoreCustomer
from app.realtime.trace import trace

MAX_STEPS = 4
ALLOWED_ACTIONS = {"send_nudges", "offer_advance", "open_customer"}
WEEKDAY_HI = ["Somvar", "Mangalvar", "Budhvar", "Guruvar", "Shukravar", "Shanivar", "Ravivar"]


# ---------------------------------------------------------------- tools (read-only)

def _sales(s: Session, store_id: str, day: date) -> int:
    lo, hi = clock.datetime_floor(day), clock.datetime_floor(day + timedelta(days=1))
    return sum(s.exec(select(Sale.amount).where(Sale.store_id == store_id, Sale.created_at >= lo,
                                                Sale.created_at < hi)).all())


def get_store_summary(s: Session, store_id: str) -> dict:
    today = clock.today()
    entries = ledger.open_entries(s, store_id)
    t = ledger.totals(entries, today)
    per = ledger.totals_by_customer(entries, today)
    return {"sales_today": _sales(s, store_id, today), "sales_yesterday": _sales(s, store_id, today - timedelta(days=1)),
            "outstanding": t.outstanding, "verified": t.verified, "overdue": t.overdue,
            "overdue_customers": sum(1 for x in per.values() if x.overdue > 0)}


def get_forecast(s: Session, store_id: str, days: int = 14) -> dict:
    fc = forecast.forecast(s, store_id, max(1, min(int(days), 14)))
    return {"today": fc["today"], "cash_on_hand": fc["cash_on_hand"], "gaps": fc["gaps"],
            "days": [{"date": d["date"], "cash": d["cash"]} for d in fc["days"]]}


def list_collectable_dues(s: Session, store_id: str, until_date: str | None = None) -> dict:
    until = date.fromisoformat(until_date) if until_date else clock.today() + timedelta(days=6)
    fc = forecast.forecast(s, store_id)
    items = [{"customer_id": c["customer_id"], "name": c["name"], "amount": c["amount"], "date": c["date"],
              "probability": c["probability"], "basis": c["basis"]}
             for c in fc["collections"] if date.fromisoformat(c["date"]) <= until]
    return {"until": until.isoformat(), "total": sum(i["amount"] for i in items), "items": items}


def list_overdue(s: Session, store_id: str, top_n: int = 5) -> dict:
    today = clock.today()
    per = ledger.totals_by_customer(ledger.open_entries(s, store_id), today)
    rows = sorted(((cid, t) for cid, t in per.items() if t.overdue > 0), key=lambda kv: (-kv[1].overdue, kv[0]))
    names = {c.id: c.name for c in s.exec(select(Customer).where(Customer.id.in_([r[0] for r in rows] or [""]))).all()}
    return {"count": len(rows), "items": [{"customer_id": cid, "name": names[cid], "overdue": t.overdue,
                                           "days": t.oldest_overdue_days} for cid, t in rows[:max(1, min(int(top_n), 10))]]}


def check_advance_eligibility(s: Session, store_id: str, bill_id: str) -> dict:
    return advance.eligibility(s, store_id, bill_id)


def get_customer(s: Session, store_id: str, name: str) -> dict:
    rows = s.exec(select(Customer).join(StoreCustomer, StoreCustomer.customer_id == Customer.id)
                  .where(StoreCustomer.store_id == store_id)).all()
    key = (name or "").strip().lower()
    hits = [c for c in rows if key and (key in c.name.lower() or key in [a.lower() for a in (c.aliases or [])])]
    if len(hits) != 1:
        return {"found": len(hits), "matches": [{"customer_id": c.id, "name": c.name} for c in hits[:5]]}
    c = hits[0]
    t = ledger.totals(ledger.open_entries(s, store_id, c.id), clock.today())
    r = risk.evaluate(s, store_id, c.id, 340)
    return {"found": 1, "customer_id": c.id, "name": c.name, "outstanding": t.outstanding, "verified": t.verified,
            "oldest_overdue_days": t.oldest_overdue_days, "score": c.score, "score_band": score.band(c.score),
            "safe_limit": r.safe_limit}


TOOLS = {
    "get_store_summary": (get_store_summary, "store", "Store summary"),
    "get_forecast": (get_forecast, "forecast", "Cash forecast"),
    "list_collectable_dues": (list_collectable_dues, "forecast", "Collectable dues"),
    "list_overdue": (list_overdue, "ledger", "Overdue customers"),
    "check_advance_eligibility": (check_advance_eligibility, "advance", "Advance eligibility"),
    "get_customer": (get_customer, "ledger", "Customer lookup"),
}


def run_tool(s: Session, store_id: str, name: str, args: dict) -> dict:
    fn, node, label = TOOLS[name]
    t0 = time.perf_counter()
    result = fn(s, store_id, **args)
    ms = round((time.perf_counter() - t0) * 1000, 1)
    trace("munim_agent", f"Tool {name}({', '.join(f'{k}={v}' for k, v in args.items())})", {"result": result}, ms=ms)
    if node != "store":
        trace(node, f"{label} for Munim", ms=ms)
    return {"tool": name, "args": args, "result": result, "ms": ms}


# ---------------------------------------------------------------- deterministic planner (fallback)

_BILL = re.compile(r"bill|supplier|distributor|kaise\s+d|kaise\s+chuk|advance|paisa\s+kam|short|pay\s+kar|"
                   r"friday|shukravar|शुक्रवार|सप्लायर", re.I)
_OVERDUE = re.compile(r"overdue|baaki|baki|bakaya|kisne|kaun|reminder|wapas|collect|udhaar\s+kitna", re.I)


def _find_bill(s: Session, store_id: str, question: str) -> Bill | None:
    bills = s.exec(select(Bill).where(Bill.store_id == store_id, Bill.status != "paid").order_by(Bill.due_date)).all()
    q = question.lower()
    for b in bills:
        if any(tok.lower() in q for tok in b.distributor.split() if len(tok) > 3):
            return b
    return bills[0] if bills else None


def plan(s: Session, store_id: str, question: str) -> tuple[str, list[tuple[str, dict]]]:
    """Pick an intent and the tool calls that answer it."""
    bill = _find_bill(s, store_id, question)
    if bill and _BILL.search(question):
        until = (bill.due_date - timedelta(days=1)).isoformat()
        return "bill", [("get_forecast", {"days": 14}), ("list_collectable_dues", {"until_date": until}),
                        ("check_advance_eligibility", {"bill_id": bill.id}), ("list_overdue", {"top_n": 5})]
    names = s.exec(select(Customer).join(StoreCustomer, StoreCustomer.customer_id == Customer.id)
                   .where(StoreCustomer.store_id == store_id)).all()
    words = set(re.findall(r"\w+", question.lower()))
    for c in names:
        if c.name.split()[0].lower() in words:
            return "customer", [("get_customer", {"name": c.name.split()[0]})]
    if _OVERDUE.search(question):
        return "overdue", [("list_overdue", {"top_n": 5})]
    return "summary", [("get_store_summary", {})]


def _day(d: str, lang: str) -> str:
    dd = date.fromisoformat(d)
    return WEEKDAY_HI[dd.weekday()] if lang == "hi-IN" else f"{dd:%a} {dd.day} {dd:%b}"


def compose(s: Session, store_id: str, intent: str, steps: list[dict], lang: str) -> tuple[str, list[dict]]:
    """Template answer + actions built only from tool results."""
    r = {st["tool"]: st["result"] for st in steps}
    hi = lang == "hi-IN"
    if intent == "bill" and "check_advance_eligibility" in r:
        el, coll, od = r["check_advance_eligibility"], r["list_collectable_dues"], r.get("list_overdue", {"items": []})
        gap = next((g for g in r["get_forecast"]["gaps"] if g["bill_id"] == el["bill_id"]), None)
        payers = ", ".join(i["name"].split()[0] for i in coll["items"])
        nudge_ids = [i["customer_id"] for i in od["items"]]
        actions = []
        if nudge_ids:
            actions.append({"type": "send_nudges", "params": {"customer_ids": nudge_ids},
                            "label": f"Send {len(nudge_ids)} reminders"})
        if el["eligible"]:
            actions.append({"type": "offer_advance", "params": {"bill_id": el["bill_id"]},
                            "label": "Get Supplier Advance"})
        if gap is None:
            text = (f"{_day(el['due'], lang)} ko {el['distributor']} ka bill cover ho jayega, koi kami nahi dikh rahi."
                    if hi else f"{el['distributor']}'s bill on {_day(el['due'], lang)} is covered; no shortfall.")
            return text, actions
        if hi:
            back = (f"Usse pehle sirf {inr(coll['total'])} udhaar wapas aane ki ummeed hai ({payers})." if coll["total"]
                    else "Usse pehle koi udhaar wapas aane ki ummeed nahi hai.")
            text = (f"{_day(el['due'], lang)} ko {el['distributor']} ko {inr(gap['amount'])} dene hain. Tab tak aapke paas "
                    f"lagbhag {inr(gap['available'])} honge, yaani {inr(gap['gap'])} kam. {back} Do raaste: 1) overdue "
                    f"customers ko reminder bhejein")
            text += (f"; 2) {el['lender']} se {inr(el['amount'])} Supplier Advance lein (fee {inr(el['fee'])}), jo "
                     f"seedha {el['distributor']} ko jayega aur udhaar wapsi ke 20% se chukega." if el["eligible"] else ".")
        else:
            back = (f"Only {inr(coll['total'])} of udhaar is expected back before then ({payers})." if coll["total"]
                    else "No udhaar is expected back before then.")
            text = (f"You owe {el['distributor']} {inr(gap['amount'])} on {_day(el['due'], lang)}. You will have about "
                    f"{inr(gap['available'])}, so {inr(gap['gap'])} short. {back} Two options: 1) send reminders to "
                    f"overdue customers")
            text += (f"; 2) take a {inr(el['amount'])} Supplier Advance from {el['lender']} (fee {inr(el['fee'])}), "
                     f"paid straight to {el['distributor']} and repaid from 20% of udhaar collections."
                     if el["eligible"] else ".")
        return text, actions
    if intent == "customer" and r["get_customer"].get("found") == 1:
        c = r["get_customer"]
        text = (f"{c['name']}: {inr(c['outstanding'])} baaki, sabse purana {c['oldest_overdue_days']} din. Score "
                f"{c['score']} ({c['score_band']}). Aaj ki safe limit {inr(c['safe_limit'])}." if hi else
                f"{c['name']} owes {inr(c['outstanding'])}, oldest {c['oldest_overdue_days']} days overdue. Score "
                f"{c['score']} ({c['score_band']}). Safe limit today {inr(c['safe_limit'])}.")
        return text, [{"type": "open_customer", "params": {"customer_id": c["customer_id"]}, "label": "Open"}]
    if intent == "overdue":
        od = r["list_overdue"]
        items = od["items"]
        lst = ", ".join(f"{i['name'].split()[0]} {inr(i['overdue'])} ({i['days']} {'din' if hi else 'days'})" for i in items)
        text = (f"{od['count']} customers overdue. Sabse zyada: {lst}." if hi else
                f"{od['count']} customers are overdue. Largest: {lst}.")
        ids = [i["customer_id"] for i in items]
        return text, ([{"type": "send_nudges", "params": {"customer_ids": ids}, "label": f"Send {len(ids)} reminders"}]
                      if ids else [])
    sm = r.get("get_store_summary") or run_tool(s, store_id, "get_store_summary", {})["result"]
    text = (f"Aaj ki UPI bikri {inr(sm['sales_today'])}, kal {inr(sm['sales_yesterday'])}. Kul udhaar "
            f"{inr(sm['outstanding'])}, jismein {inr(sm['verified'])} verified. {sm['overdue_customers']} customers overdue."
            if hi else
            f"UPI sales today {inr(sm['sales_today'])}, yesterday {inr(sm['sales_yesterday'])}. Udhaar outstanding "
            f"{inr(sm['outstanding'])}, {inr(sm['verified'])} verified. {sm['overdue_customers']} customers overdue.")
    return text, []


# ---------------------------------------------------------------- validator

def _numbers(obj: Any, out: set[int]) -> set[int]:
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.add(int(round(obj)))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _numbers(v, out)
    return out


def validate_final(s: Session, store_id: str, answer: str, actions: list[dict], steps: list[dict]) -> list[str]:
    problems = []
    known = _numbers([st["result"] for st in steps], set())
    invented = rupee_figures(answer) - known
    if invented:
        problems.append(f"₹ figures not in any tool result: {sorted(invented)}")
    for a in actions:
        t, p = a.get("type"), a.get("params") or {}
        if t not in ALLOWED_ACTIONS:
            problems.append(f"action {t} not allowed")
        elif t == "offer_advance" and s.get(Bill, p.get("bill_id")) is None:
            problems.append(f"unknown bill {p.get('bill_id')}")
        elif t == "send_nudges" and not all(s.get(StoreCustomer, (store_id, cid)) for cid in p.get("customer_ids", [])):
            problems.append("send_nudges with a customer outside this store")
        elif t == "open_customer" and not s.get(StoreCustomer, (store_id, p.get("customer_id"))):
            problems.append("open_customer outside this store")
    return problems


# ---------------------------------------------------------------- the loop

class Final(BaseModel):
    answer: str
    actions: list[dict] = Field(default_factory=list)


class Step(BaseModel):
    tool: Optional[str] = None
    args: dict = Field(default_factory=dict)
    final: Optional[Final] = None


def _parse_step(content: str) -> Step | None:
    try:
        m = re.search(r"\{.*\}", content, re.S)
        return Step.model_validate(json.loads(m.group(0) if m else content))
    except (ValueError, TypeError):
        return None


async def _llm_loop(s: Session, store_id: str, question: str, lang: str) -> tuple[Final | None, list[dict], str]:
    messages = [{"role": "system", "content": prompt("munim")},
                {"role": "user", "content": json.dumps({"question": question, "lang": lang,
                                                        "today": clock.today().isoformat()}, ensure_ascii=False)}]
    steps: list[dict] = []
    source = "template"
    for i in range(MAX_STEPS + 1):
        if i == MAX_STEPS:
            messages.append({"role": "user", "content": "Give your final answer now."})
        key = {"question": question, "lang": lang, "today": clock.today().isoformat(),
               "steps": [(st["tool"], st["args"]) for st in steps]}
        res = await llm.complete("munim", PROMPT_VERSION, key, messages, {"type": "json_object"})
        if res.content is None:
            return None, steps, "template"
        source = res.source if source != "live" else source
        step = _parse_step(res.content)
        if step is None:
            return None, steps, source
        if step.final is not None:
            return step.final, steps, source
        if step.tool not in TOOLS or i == MAX_STEPS:
            return None, steps, source
        try:
            st = run_tool(s, store_id, step.tool, step.args)
        except Exception as e:  # bad args from the model: tell it once, then fall back
            trace("validator", f"Munim tool {step.tool} failed: {e}")
            return None, steps, source
        steps.append(st)
        messages += [{"role": "assistant", "content": res.content},
                     {"role": "user", "content": f"TOOL_RESULT {step.tool}: "
                                                 + json.dumps(st["result"], ensure_ascii=False, default=str)}]
    return None, steps, source


async def ask(s: Session, store_id: str, question: str, lang: str) -> dict:
    t0 = time.perf_counter()
    trace("merchant_app", f"Ask Munim: {question[:60]}")
    final, steps, source = await _llm_loop(s, store_id, question, lang)
    if final is not None:
        problems = validate_final(s, store_id, final.answer, final.actions, steps)
        if problems:
            trace("validator", "Munim answer rejected: " + "; ".join(problems), {"answer": final.answer})
            final = None
    if final is None:
        intent, calls = plan(s, store_id, question)
        have = {st["tool"] for st in steps}
        steps += [run_tool(s, store_id, name, args) for name, args in calls if name not in have]
        answer, actions = compose(s, store_id, intent, steps, lang)
        final, source = Final(answer=answer, actions=actions), "template"
    ms = round((time.perf_counter() - t0) * 1000, 1)
    trace("munim_agent", f"Answered with {len(final.actions)} action(s)", {"answer": final.answer}, ms=ms, source=source)
    out = {"question": question, "answer": final.answer, "actions": final.actions, "source": source, "ms": ms,
           "steps": [{"tool": st["tool"], "args": st["args"], "ms": st["ms"], "result": st["result"]} for st in steps]}
    state.put(s, "munim_last", out)
    return out


# ---------------------------------------------------------------- morning briefing

class BriefingText(BaseModel):
    text: str


async def compose_briefing(s: Session, store_id: str = "S1") -> dict:
    """Deterministic summary + template, optionally rephrased by the LLM (numbers must survive)."""
    b = briefing.refresh(s, store_id)
    payload = {"lang": b["lang"], "summary": b["summary"], "template": b["text"]}
    out, source, ms = await call_llm("briefing", "munim_agent", prompt("briefing"), payload, BriefingText)
    if out is not None:
        allowed = _numbers(b["summary"], set())
        if rupee_figures(out.text) <= allowed and rupee_figures(b["text"]) <= rupee_figures(out.text) \
                and len(out.text.split()) <= 70:
            b = {**b, "text": out.text, "source": source}
            state.put(s, "briefing", b)
            trace("munim_agent", "Briefing phrased", ms=ms, source=source)
        else:
            trace("validator", "Briefing rephrase changed the numbers → template kept")
    return b
