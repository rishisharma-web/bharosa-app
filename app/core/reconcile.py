"""Reconciliation rules for incoming UPI payments (spec 7.5). Deterministic except rule 3.

Rule 0  ref starts with SALE-      → a sale (the "pay ₹140 now" QR). NEVER allocated to old dues.
Rule 1  payer VPA known at store   → repayment (matched_by=rule); no dues at all → a sale.
Rule 2  payer VPA unknown anywhere, exactly one no-VPA customer has an open entry of exactly
        this amount               → repayment, VPA linked (matched_by=rule_amount).
Rule 3  rank candidates by name similarity (payer name, remark) then amount closeness, and ask
        the matcher (Reconciliation Agent, or its fallback) → auto-apply at confidence ≥ 0.85,
        else a "Who paid?" card for the merchant.
Rule 4  nothing resembles any customer → a sale.

`decide()` only decides; the event handler performs the writes.
"""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from sqlmodel import Session, select

from app import clock
from app.core import ledger
from app.models import Customer, StoreCustomer

AUTO_APPLY_CONFIDENCE = 0.85
MIN_SIMILARITY = 0.5  # below this, an unknown payer is treated as a walk-in sale (rule 4)
TOP_N = 5
SALE_PREFIX = "SALE-"

_STOP = {"ka", "ki", "ke", "ko", "ne", "se", "for", "the", "udhaar", "udhar", "payment", "paid", "pay", "rs",
         "baaki", "baki", "dues", "due", "khata", "credit", "maa", "mother", "papa", "bhai", "ji"}


@dataclass
class Decision:
    kind: str  # sale | repayment | pending
    rule: str
    customer_id: str | None = None
    matched_by: str | None = None
    confidence: float | None = None
    link_vpa: bool = False
    candidates: list[dict] = field(default_factory=list)
    reason: str = ""


def _tokens(text: str | None) -> list[str]:
    return [t for t in re.findall(r"[a-zA-Zऀ-ॿಀ-೿]+", (text or "").lower()) if t not in _STOP]


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def name_similarity(c: Customer, payer_name: str | None, remark: str | None) -> float:
    """Best match between any hint token (payer name, remark) and the customer's name/aliases.
    A full-name match on the payer counts as well, so 'Ramesh K' still finds 'Ramesh Kumar'."""
    names = [c.name.lower(), *[a.lower() for a in (c.aliases or [])]]
    name_tokens = {t for n in names for t in _tokens(n)}
    hints = _tokens(payer_name) + _tokens(remark)
    best = 0.0
    for h in hints:
        for t in name_tokens:
            best = max(best, _sim(h, t))
    if payer_name:
        best = max(best, *(_sim(payer_name.lower(), n) for n in names))
    return round(best, 3)


def candidates(s: Session, store_id: str, amount: int, payer_name: str | None, remark: str | None) -> list[dict]:
    """Customers at this store who owe something, ranked by name similarity then amount closeness."""
    per = ledger.totals_by_customer(ledger.open_entries(s, store_id), clock.today())
    if not per:
        return []
    custs = s.exec(select(Customer).where(Customer.id.in_(list(per)))).all()
    open_amounts: dict[str, list[int]] = {}
    for e in ledger.open_entries(s, store_id):
        open_amounts.setdefault(e.customer_id, []).append(ledger.remaining(e))
    rows = []
    for c in custs:
        owed = per[c.id].outstanding
        rows.append({
            "id": c.id, "name": c.name, "outstanding": owed, "open_entries": open_amounts.get(c.id, []),
            "similarity": name_similarity(c, payer_name, remark),
            "amount_gap": min(abs(owed - amount), *(abs(a - amount) for a in open_amounts.get(c.id, [owed]))),
        })
    rows.sort(key=lambda r: (-r["similarity"], r["amount_gap"], r["id"]))
    return rows[:TOP_N]


def fallback_match(payment: dict, cands: list[dict]) -> dict:
    """Deterministic stand-in for the Reconciliation Agent (spec 7.9.3): best name ratio × 0.8,
    so it rarely clears the auto-apply bar and usually routes to the merchant."""
    if not cands:
        return {"customer_id": None, "confidence": 0.0, "reason": "no candidates", "source": "template"}
    best = cands[0]
    return {"customer_id": best["id"], "confidence": round(best["similarity"] * 0.8, 3),
            "reason": f"closest name match ({best['similarity']:.2f})", "source": "template"}


def decide(s: Session, store_id: str, payer_vpa: str, amount: int, payer_name: str | None = None,
           remark: str | None = None, ref: str | None = None) -> Decision:
    """Rules 0–2 and the candidate list for rule 3. The matcher call for rule 3 is the caller's."""
    owner = s.exec(select(Customer).where(Customer.vpa == payer_vpa)).first()
    at_store = owner is not None and s.get(StoreCustomer, (store_id, owner.id)) is not None

    if ref and ref.upper().startswith(SALE_PREFIX):
        return Decision("sale", "rule0", customer_id=owner.id if at_store else None,
                        reason=f"payment for the current purchase ({ref})")

    if at_store:
        owes = ledger.open_entries(s, store_id, owner.id)
        if not owes:
            return Decision("sale", "rule1", customer_id=owner.id, reason="known customer with no dues: a purchase")
        return Decision("repayment", "rule1", customer_id=owner.id, matched_by="rule", confidence=1.0,
                        reason="payer VPA on file")

    if owner is None:
        no_vpa = {c.id for c in s.exec(select(Customer).join(StoreCustomer, StoreCustomer.customer_id == Customer.id)
                                        .where(StoreCustomer.store_id == store_id, Customer.vpa == None)).all()}  # noqa: E711
        exact = {e.customer_id for e in ledger.open_entries(s, store_id)
                 if e.customer_id in no_vpa and ledger.remaining(e) == amount}
        if len(exact) == 1:
            return Decision("repayment", "rule2", customer_id=exact.pop(), matched_by="rule_amount", confidence=1.0,
                            link_vpa=True, reason=f"only open entry of exactly ₹{amount}")

    cands = candidates(s, store_id, amount, payer_name, remark)
    if not cands or cands[0]["similarity"] < MIN_SIMILARITY:
        return Decision("sale", "rule4", candidates=cands, reason="payer resembles no customer: a walk-in sale")
    return Decision("pending", "rule3", candidates=cands, reason="unclear payer")
