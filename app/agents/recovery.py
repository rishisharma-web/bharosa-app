"""Recovery Agent (spec 7.9.2): drafts reminders and reads customers' replies.

The collector policy (code) decides who is nudged; the merchant approves every draft; the
validator rejects any message that invents a rupee figure and any promise or plan outside
policy. Fallbacks are templates and keyword rules, so the demo runs without an LLM.
"""
import re
from datetime import date, timedelta
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.agents.base import AgentResult, call_llm, prompt, rupee_figures
from app.core.money import inr
from app.realtime.trace import trace

POLICY = {"max_days": 30, "max_installments": 3, "min_first_pct": 25}
MAX_NUDGE_CHARS = 320


# ---------------------------------------------------------------- draft_nudge

class DraftOut(BaseModel):
    message: str
    lang: str = "hi-IN"


def draft_template(first: str, dues: int, days: int, store: str, lang: str) -> str:
    if lang == "kn-IN":
        since = f" ({days} ದಿನಗಳಿಂದ)" if days else ""
        return (f"ನಮಸ್ಕಾರ {first} ಅವರೇ, {store} ನಲ್ಲಿ ನಿಮ್ಮ {inr(dues)} ಬಾಕಿ ಇದೆ{since}. "
                f"ದಯವಿಟ್ಟು Paytm ನಲ್ಲಿ 'Pay now' ಒತ್ತಿ ಪಾವತಿಸಿ. ಧನ್ಯವಾದಗಳು!")
    if lang == "en-IN":
        since = f" (due for {days} days)" if days else ""
        return f"Hello {first}, your udhaar of {inr(dues)} at {store} is pending{since}. Tap 'Pay now' on Paytm when convenient. Thank you!"
    since = f" ({days} din se)" if days else ""
    return (f"Namaste {first} ji, {store} par aapka {inr(dues)} udhaar baaki hai{since}. "
            f"Suvidha ho to Paytm par 'Pay now' dabakar chuka dein. Dhanyavaad!")


def validate_draft(message: str, dues: int) -> str | None:
    """Returns a rejection reason, or None if the draft is acceptable."""
    if len(message) > MAX_NUDGE_CHARS:
        return f"too long ({len(message)} chars)"
    figs = rupee_figures(message)
    if dues not in figs:
        return f"dues {inr(dues)} missing"
    if figs - {dues}:
        return f"invented figure(s) {sorted(figs - {dues})}"
    return None


async def draft_nudge(customer_name: str, lang: str, dues: int, overdue_days: int, persona_hint: str | None,
                      store_name: str) -> AgentResult[DraftOut]:
    first = customer_name.split()[0]
    payload = {"customer_name": customer_name, "lang": lang, "dues_total": dues, "oldest_overdue_days": overdue_days,
               "persona_hint": persona_hint, "store_name": store_name, "policy": POLICY}
    out, source, ms = await call_llm("recovery_draft", "recovery_agent", prompt("recovery_draft"), payload, DraftOut)
    note = None
    if out is not None:
        note = validate_draft(out.message, dues)
        if note:
            trace("validator", f"Draft rejected: {note}", {"message": out.message})
            out = None
    if out is None:
        out, source = DraftOut(message=draft_template(first, dues, overdue_days, store_name, lang), lang=lang), "template"
    trace("recovery_agent", f"Reminder drafted for {first} ({inr(dues)})", {"message": out.message}, ms=ms, source=source)
    return AgentResult(out, source, ms, note)


# ---------------------------------------------------------------- interpret_reply

class PlanItem(BaseModel):
    amount: int
    date: date


class ReplyOut(BaseModel):
    intent: Literal["promise", "pay_now", "plan_request", "dispute", "hardship", "other"]
    promise: Optional[PlanItem] = None
    proposed_plan: list[PlanItem] = Field(default_factory=list)
    suggest_mandate: bool = False
    reply_message: str = ""
    escalate: bool = False


def next_first(today: date) -> date:
    return today if today.day == 1 else (today.replace(day=1) + timedelta(days=32)).replace(day=1)


def _d(d: date) -> str:
    return f"{d.day} {d:%b}"


def reply_template(out: ReplyOut, first: str, dues: int, store: str) -> str:
    if out.intent == "promise" and out.promise:
        msg = f"Dhanyavaad {first} ji! {_d(out.promise.date)} ko {inr(out.promise.amount)} ka vaada note kar liya hai."
        if out.suggest_mandate:
            msg += " Salary-day auto-pay set kar dein, to yaad rakhne ki zaroorat nahi padegi?"
        return msg
    if out.intent == "plan_request" and out.proposed_plan:
        parts = "; ".join(f"{inr(p.amount)} {_d(p.date)} tak" for p in out.proposed_plan)
        return f"Theek hai {first} ji, kishton mein: {parts}."
    if out.intent == "pay_now":
        return f"Dhanyavaad {first} ji! Neeche 'Pay now' dabakar abhi {inr(dues)} chuka sakte hain."
    if out.intent == "dispute":
        return f"Maaf kijiye {first} ji, hum {store} ko bata rahe hain. Woh aapse seedha baat karenge."
    if out.intent == "hardship":
        return f"Samajh sakte hain {first} ji. {store} aapse baat karke aasaan plan banayenge."
    return f"Dhanyavaad {first} ji. Aapka {inr(dues)} baaki hai; jab suvidha ho 'Pay now' se chuka dein."


_SALARY = re.compile(r"salary|salery|tankh?w?a|tankha|1\s*(?:tareekh|tarikh|tarik)|pehli|first|1st|वेतन|तनख्वाह", re.I)
_DISPUTE = re.compile(r"\bgalat\b|\bwrong\b|maine nahi|mera nahi|nahi liya|kabhi nahi|गलत", re.I)
_HARDSHIP = re.compile(r"bimar|beemar|hospital|naukri|job (?:chali|gayi|lost)|paise nahi hai|mushkil", re.I)
_PLAN = re.compile(r"kisht|installment|thoda thoda|parts?\b|do baar|EMI", re.I)
_NOW = re.compile(r"\babhi\b|\bnow\b|\baaj\b|kar raha|kar deta", re.I)


def reply_fallback(text: str, dues: int, today: date, has_mandate: bool) -> ReplyOut:
    nums = [int(n) for n in re.findall(r"\d{3,6}", text)]
    amount = dues if re.search(r"\bpura\b|\bpoora\b|\bfull\b|\bsab\b|\bsaara\b", text, re.I) or not nums else min(nums[0], dues)
    if _DISPUTE.search(text):
        return ReplyOut(intent="dispute", escalate=True)
    if _HARDSHIP.search(text):
        return ReplyOut(intent="hardship", escalate=True)
    if _PLAN.search(text):
        first = -(-dues // 2 // 10) * 10  # half, rounded up to ₹10
        return ReplyOut(intent="plan_request", proposed_plan=[PlanItem(amount=first, date=next_first(today)),
                                                              PlanItem(amount=dues - first,
                                                                       date=next_first(today) + timedelta(days=14))])
    if _SALARY.search(text):
        return ReplyOut(intent="promise", promise=PlanItem(amount=amount, date=next_first(today)),
                        suggest_mandate=not has_mandate)
    if _NOW.search(text):
        return ReplyOut(intent="pay_now")
    return ReplyOut(intent="other")


def validate_reply(out: ReplyOut, dues: int, today: date, has_mandate: bool) -> tuple[ReplyOut, list[str]]:
    notes = []
    last_day = today + timedelta(days=POLICY["max_days"])
    if out.promise is not None:
        if not (today <= out.promise.date <= last_day) or not (0 < out.promise.amount <= dues):
            notes.append(f"promise {out.promise.amount} on {out.promise.date} outside policy")
            out.promise, out.escalate = None, True
    if out.intent == "promise" and out.promise is None:
        out.intent = "other"
    if out.proposed_plan:
        p = out.proposed_plan
        ok = (len(p) <= POLICY["max_installments"] and sum(x.amount for x in p) == dues
              and p[0].amount * 100 >= POLICY["min_first_pct"] * dues
              and all(today <= x.date <= last_day for x in p)
              and all(a.date < b.date for a, b in zip(p, p[1:])))
        if not ok:
            notes.append("plan outside policy")
            out.proposed_plan, out.escalate = [], True
    if out.suggest_mandate and has_mandate:
        out.suggest_mandate = False
    if out.intent in ("dispute", "hardship"):
        out.escalate = True
    allowed = {dues} | ({out.promise.amount} if out.promise else set()) | {x.amount for x in out.proposed_plan}
    bad = rupee_figures(out.reply_message) - allowed
    if not out.reply_message or bad or len(out.reply_message) > 400:
        if out.reply_message:
            notes.append(f"reply rewritten (figures {sorted(bad)})" if bad else "reply rewritten")
        out.reply_message = ""
    return out, notes


async def interpret_reply(reply_text: str, customer_name: str, dues: int, today: date, has_mandate: bool,
                          store_name: str, lang: str) -> AgentResult[ReplyOut]:
    first = customer_name.split()[0]
    payload = {"reply_text": reply_text, "customer_name": customer_name, "dues_total": dues,
               "today": today.isoformat(), "policy": POLICY, "has_mandate": has_mandate,
               "store_name": store_name, "lang": lang}
    out, source, ms = await call_llm("recovery_reply", "recovery_agent", prompt("recovery_reply"), payload, ReplyOut)
    if out is None:
        out, source = reply_fallback(reply_text, dues, today, has_mandate), "template"
    out, notes = validate_reply(out, dues, today, has_mandate)
    if notes:
        trace("validator", "Reply corrected: " + "; ".join(notes), {"notes": notes})
    if not out.reply_message:
        out.reply_message = reply_template(out, first, dues, store_name)
    label = f"{out.intent}" + (f" {inr(out.promise.amount)} on {_d(out.promise.date)}" if out.promise else "")
    trace("recovery_agent", f"Reply read: {label}", out.model_dump(mode="json"), ms=ms, source=source)
    return AgentResult(out, source, ms)
