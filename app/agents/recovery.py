"""Recovery Agent (v2 spec §9.6): reminder drafts and reading customers' replies.

Rules first, AI second, validators always:
- a draft may mention only the exact dues figure;
- a promise must fall within 30 days of the demo date and not exceed the dues;
- a reply message may mention no rupee figure other than the dues.
"""
import json
import re
from datetime import date, timedelta

from app.agents.common import rupee_figures
from app.ai import sarvam
from app.config import today
from app.core.money import inr

MAX_DRAFT = 300

DRAFT_SYSTEM = ("Write a short, polite payment reminder from a neighbourhood shop to a regular customer, "
                "in the customer's language ({lang}; for hi-IN use friendly Hinglish in Roman script). "
                "At most 300 characters. Mention the dues exactly once as {dues} and no other rupee amount. "
                'Return JSON {{"message": "..."}}.')

REPLY_SYSTEM = ("Classify a kirana customer's reply to a payment reminder. Dues are {dues}; today is {today}. "
                'Return JSON {{"intent": "promise|pay_now|dispute|hardship|other", '
                '"promise": {{"amount": int, "date": "YYYY-MM-DD"}} or null, "suggest_mandate": bool, '
                '"reply_message": "short warm reply in the customer\'s language", "escalate": bool}}. '
                "A promise must not exceed the dues. Use no rupee figure other than the dues.")

KEYWORDS = [
    (re.compile(r"salary|tankhwa|tankha|1\s*tareekh|first|1st|pagar", re.I), "promise"),
    (re.compile(r"\babhi\b|\bnow\b|pay kar|bhej", re.I), "pay_now"),
    (re.compile(r"galat|wrong|nahi liya|didn'?t", re.I), "dispute"),
    (re.compile(r"problem|mushkil|hospital|\bjob\b", re.I), "hardship"),
]


def draft_template(name: str, dues: int, days: int, lang: str) -> str:
    first = name.split()[0]
    if lang == "hi-IN":
        return (f"Namaste {first} ji, Lakshmi Stores par aapka {inr(dues)} udhaar baaki hai ({days} din se). "
                f"Aap Paytm se 'Pay now' kar sakte hain. Dhanyavaad!")
    return (f"Hello {first}, your udhaar of {inr(dues)} at Lakshmi Stores is pending ({days} days). "
            f"You can tap 'Pay now' in Paytm. Thank you!")


def valid_draft(msg: str, dues: int) -> bool:
    return bool(msg) and len(msg) <= MAX_DRAFT and rupee_figures(msg) == {dues}


async def draft(name: str, dues: int, days: int, lang: str) -> tuple[str, str]:
    """(message, source)."""
    out = await sarvam.chat_json(DRAFT_SYSTEM.format(lang=lang, dues=inr(dues)),
                                 json.dumps({"customer": name, "dues": dues, "days_overdue": days}))
    msg = (out or {}).get("message") if isinstance(out, dict) else None
    if isinstance(msg, str) and valid_draft(msg, dues):
        return msg, "ai"
    return draft_template(name, dues, days, lang), "template"


def next_first(d: date) -> date:
    return (d.replace(day=1) + timedelta(days=32)).replace(day=1)


def _template_reply(intent: str, name: str, dues: int, promise: dict | None, suggest: bool, lang: str) -> str:
    first = name.split()[0]
    hi = lang == "hi-IN"
    if intent == "promise" and promise:
        d = date.fromisoformat(promise["date"])
        msg = (f"Dhanyavaad {first} ji! {d.day} {d:%b} ko {inr(promise['amount'])} ka vaada note kar liya."
               if hi else f"Thank you {first}! Noted: {inr(promise['amount'])} on {d.day} {d:%b}.")
        if suggest:
            msg += (" Salary-week auto-pay set kar dein? Yaad rakhne ki zaroorat nahi padegi." if hi
                    else " Set up salary-week auto-pay so you never have to remember?")
        return msg
    if intent == "pay_now":
        return f"Dhanyavaad {first} ji! 'Pay now' dabakar abhi chuka sakte hain." if hi else \
            f"Thank you {first}! Tap 'Pay now' to pay."
    if intent in ("dispute", "hardship"):
        return (f"Samajh gaye {first} ji. Lakshmi Stores aapse seedha baat karenge." if hi
                else f"Understood, {first}. Lakshmi Stores will talk to you directly.")
    return f"Dhanyavaad {first} ji." if hi else f"Thank you, {first}."


def rule_interpret(text: str, dues: int, has_mandate: bool) -> dict | None:
    for pat, intent in KEYWORDS:
        if pat.search(text or ""):
            out = {"intent": intent, "promise": None, "suggest_mandate": False,
                   "escalate": intent in ("dispute", "hardship")}
            if intent == "promise":
                out["promise"] = {"amount": dues, "date": next_first(today()).isoformat()}
                out["suggest_mandate"] = not has_mandate
            return out
    return None


def _validate(out: dict, dues: int, has_mandate: bool) -> dict | None:
    if not isinstance(out, dict) or out.get("intent") not in ("promise", "pay_now", "dispute", "hardship", "other"):
        return None
    p = out.get("promise")
    if p is not None:
        try:
            d = date.fromisoformat(str(p["date"]))
            amt = int(p["amount"])
        except (KeyError, TypeError, ValueError):
            return None
        if not (today() <= d <= today() + timedelta(days=30)) or not (0 < amt <= dues):
            return None
        p = {"amount": amt, "date": d.isoformat()}
    reply = out.get("reply_message") if isinstance(out.get("reply_message"), str) else ""
    if rupee_figures(reply) - {dues}:
        reply = ""
    intent = out["intent"]
    return {"intent": intent, "promise": p if intent == "promise" else None,
            "suggest_mandate": bool(out.get("suggest_mandate")) and not has_mandate,
            "escalate": bool(out.get("escalate")) or intent in ("dispute", "hardship"), "reply_message": reply}


async def interpret(text: str, name: str, dues: int, has_mandate: bool, lang: str) -> dict:
    """{"intent", "promise", "suggest_mandate", "escalate", "reply_message", "source"}."""
    res, source = rule_interpret(text, dues, has_mandate), "rule"
    if res is None and sarvam.enabled():
        out = await sarvam.chat_json(REPLY_SYSTEM.format(dues=inr(dues), today=today().isoformat()), text)
        res = _validate(out, dues, has_mandate)
        source = "ai" if res else "template"
    if res is None:
        res = {"intent": "other", "promise": None, "suggest_mandate": False, "escalate": False}
    if not res.get("reply_message"):
        res["reply_message"] = _template_reply(res["intent"], name, dues, res["promise"], res["suggest_mandate"], lang)
    res["source"] = source
    return res
