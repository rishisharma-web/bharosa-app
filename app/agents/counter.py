"""Counter Agent (v2 spec §9.5): shopkeeper text → {customer, amount}.

The rule parser always runs first: "<name> <amount>" with a fuzzy name match. The AI is called
only if the rules fail and SARVAM_ENABLED is on; its answer must name a known customer id and an
amount of ₹1–50,000, or the shopkeeper is asked to tap a name.
"""
import json
import re
from difflib import get_close_matches

from sqlmodel import Session, select

from app.ai import sarvam
from app.models import Customer, StoreCustomer

RULE = re.compile(r"^\s*([A-Za-zಀ-೿ऀ-ॿ ]+?)\s+(\d{2,6})\b")
CUTOFF = 0.75
SYSTEM = (
    "You convert a kirana shopkeeper's short sentence (English, Hindi, Kannada or mixed) into JSON.\n"
    "Known customers: {customers}.\n"
    'Return {{"customer_id": "<id or null>", "amount": <integer rupees or null>, '
    '"type": "udhaar"|"cash_repayment"|"unknown", "clarify": "<short question or null>"}}.\n'
    "Use only ids from the list. Convert number words to digits. Never invent a customer or amount. JSON only."
)
DIDNT_CATCH = "Didn't catch that. Tap a name or type again."


def known_customers(s: Session, store_id: str) -> list[dict]:
    """The store's customers plus loginable network customers who can walk in (e.g. Anita)."""
    here = {c.id for c in s.exec(select(Customer).join(StoreCustomer, StoreCustomer.customer_id == Customer.id)
                                 .where(StoreCustomer.store_id == store_id)).all()}
    rows = s.exec(select(Customer)).all()
    return [{"id": c.id, "name": c.name} for c in rows if c.id in here or c.loginable]


def _match(name: str, customers: list[dict]) -> str | None:
    name = name.strip().lower()
    keys = {}
    for c in customers:
        keys.setdefault(c["name"].lower(), set()).add(c["id"])
        keys.setdefault(c["name"].split()[0].lower(), set()).add(c["id"])
    hits = get_close_matches(name, list(keys), n=2, cutoff=CUTOFF)
    ids = set().union(*(keys[h] for h in hits)) if hits else set()
    return ids.pop() if len(ids) == 1 else None


def rule_parse(text: str, customers: list[dict]) -> tuple[str, int] | None:
    m = RULE.match(text or "")
    if not m:
        return None
    name = re.sub(r"\b(udhaar|udhar|credit|khata|ka|ko|ne)\b", "", m.group(1), flags=re.I).strip()
    cid = _match(name, customers)
    return (cid, int(m.group(2))) if cid else None


async def parse(s: Session, store_id: str, text: str) -> dict:
    """{"customer_id", "amount", "source": rule|ai} or {"error": ...}."""
    customers = known_customers(s, store_id)
    hit = rule_parse(text, customers)
    if hit:
        return {"customer_id": hit[0], "amount": hit[1], "source": "rule"}
    if not sarvam.enabled():
        return {"error": DIDNT_CATCH, "source": "rule"}
    out = await sarvam.chat_json(SYSTEM.format(customers=json.dumps(customers, ensure_ascii=False)), text)
    ids = {c["id"] for c in customers}
    if (isinstance(out, dict) and out.get("type") == "udhaar" and out.get("customer_id") in ids
            and isinstance(out.get("amount"), int) and 1 <= out["amount"] <= 50_000):
        return {"customer_id": out["customer_id"], "amount": out["amount"], "source": "ai"}
    clarify = out.get("clarify") if isinstance(out, dict) else None
    return {"error": clarify if isinstance(clarify, str) and clarify else DIDNT_CATCH, "source": "ai"}
