"""Counter Agent (spec 7.9.1): shopkeeper speech text → udhaar / cash actions.

The LLM only proposes. The validator keeps ids inside this store's customer list and
amounts inside ₹1–50,000; ambiguity goes back to the shopkeeper as a picker. The
fallback is a keyword + fuzzy-name parser that handles the demo's sentence shapes.
"""
import re
from difflib import SequenceMatcher
from typing import Literal, Optional

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import clock
from app.agents.base import AgentResult, call_llm, prompt
from app.models import Customer, StoreCustomer
from app.realtime.trace import trace

UDHAAR_WORDS = {"udhaar", "udhar", "udhari", "udaar", "khata", "credit", "likh", "likho", "likhdo", "उधार", "उधारी"}
CASH_WORDS = {"cash", "diye", "diya", "jama", "paid", "nakad", "nagad", "नकद", "दिए", "दिया"}
FILLER = {"ne", "ko", "ka", "ki", "ke", "rs", "rupees", "rupaye", "rupay", "do", "de", "dena", "diya", "hai",
          "aur", "and", "ji", "bhai", "का", "को", "ने", "रुपये"}
NAME_MATCH = 0.8


class Action(BaseModel):
    type: Literal["udhaar", "cash_repayment", "unknown"]
    customer_id: Optional[str] = None
    name_heard: Optional[str] = None
    candidate_ids: list[str] = Field(default_factory=list)
    amount: Optional[int] = None


class CounterOutput(BaseModel):
    actions: list[Action] = Field(default_factory=list)
    clarify_question: Optional[str] = None


def store_customers(s: Session, store_id: str) -> list[dict]:
    rows = s.exec(select(Customer).join(StoreCustomer, StoreCustomer.customer_id == Customer.id)
                  .where(StoreCustomer.store_id == store_id).order_by(Customer.id)).all()
    return [{"id": c.id, "name": c.name, "aliases": c.aliases or []} for c in rows]


def _name_keys(c: dict) -> list[str]:
    return [c["name"].split()[0].lower(), c["name"].lower(), *[a.lower() for a in c["aliases"]]]


def match_name(heard: str, customers: list[dict]) -> list[str]:
    """Customers whose first name, full name or alias resembles what was heard."""
    heard = heard.lower().strip()
    if not heard:
        return []
    exact = [c["id"] for c in customers if heard in _name_keys(c)]
    if exact:
        return exact
    return [c["id"] for c in customers
            if max(SequenceMatcher(None, heard, k).ratio() for k in _name_keys(c)) >= NAME_MATCH]


def fallback(text: str, customers: list[dict], lang: str) -> CounterOutput:
    """Clauses split on aur/and/commas; each needs a name and an amount; intent from keywords."""
    words = re.findall(r"[\wऀ-ॿಀ-೿]+", text.lower())
    sentence_intent = ("cash_repayment" if any(w in CASH_WORDS for w in words)
                       else "udhaar" if any(w in UDHAAR_WORDS for w in words) else "unknown")
    actions, clarify = [], None
    for clause in re.split(r"\s+(?:aur|and|और)\s+|,", text.lower()):
        toks = re.findall(r"[\wऀ-ॿಀ-೿]+", clause)
        nums = [int(t) for t in toks if t.isdigit()]
        names = [t for t in toks if not t.isdigit() and t not in UDHAAR_WORDS | CASH_WORDS | FILLER]
        if not nums and not names:
            continue
        intent = ("cash_repayment" if any(t in CASH_WORDS for t in toks)
                  else "udhaar" if any(t in UDHAAR_WORDS for t in toks) else sentence_intent)
        heard = names[0] if names else None
        cands = match_name(heard, customers) if heard else []
        actions.append(Action(type=intent if nums else "unknown", customer_id=cands[0] if len(cands) == 1 else None,
                              name_heard=heard.title() if heard else None, candidate_ids=cands,
                              amount=nums[0] if nums else None))
        if len(cands) > 1:
            full = [c["name"] for c in customers if c["id"] in cands]
            clarify = (f"Kaun sa {heard.title()}: {' ya '.join(full)}?" if lang == "hi-IN"
                       else f"Which {heard.title()}: {' or '.join(full)}?")
    return CounterOutput(actions=actions, clarify_question=clarify)


def validate(out: CounterOutput, customers: list[dict]) -> tuple[CounterOutput, list[str]]:
    ids = {c["id"] for c in customers}
    notes = []
    for a in out.actions:
        if a.customer_id and a.customer_id not in ids:
            notes.append(f"dropped unknown id {a.customer_id}")
            a.customer_id = None
        a.candidate_ids = [c for c in a.candidate_ids if c in ids]
        if a.customer_id is None and len(a.candidate_ids) == 1:
            a.customer_id = a.candidate_ids[0]
        if a.amount is not None and not (1 <= a.amount <= 50_000):
            notes.append(f"amount {a.amount} out of range")
            a.amount, a.type = None, "unknown"
        if a.type != "unknown" and a.amount is None:
            a.type = "unknown"
    return out, notes


async def parse(s: Session, store_id: str, text: str, lang: str) -> AgentResult[CounterOutput]:
    customers = store_customers(s, store_id)
    payload = {"text": text, "lang": lang, "today": clock.today().isoformat(), "store_customers": customers}
    out, source, ms = await call_llm("counter", "counter_agent", prompt("counter"), payload, CounterOutput)
    if out is None:
        out = fallback(text, customers, lang)
    out, notes = validate(out, customers)
    trace("counter_agent", f"“{text[:40]}” → " + ", ".join(
        f"{a.type} {a.name_heard or a.customer_id} {a.amount or ''}".strip() for a in out.actions) or "nothing",
          {"actions": out.model_dump()["actions"]}, ms=ms, source=source)
    if notes:
        trace("validator", "Counter output corrected", {"notes": notes})
    return AgentResult(out, source, ms)
