"""Salary-day Auto-pay (spec 5.2 B4): mandate creation and the mandate executor."""
from sqlmodel import Session, select

from app import clock
from app.adapters.payments import MandateAdapter
from app.core import ledger, score
from app.errors import EventError
from app.models import Consent, Mandate, Promise, Repayment


def active(s: Session, customer_id: str, store_id: str | None = None) -> list[Mandate]:
    q = select(Mandate).where(Mandate.customer_id == customer_id, Mandate.status == "active")
    if store_id:
        q = q.where(Mandate.store_id == store_id)
    return list(s.exec(q).all())


def create(s: Session, customer_id: str, store_id: str, cap: int, start_day: int, end_day: int) -> Mandate:
    if active(s, customer_id, store_id):
        raise EventError("auto-pay is already active for this store", 409)
    now = clock.now()
    m = Mandate(customer_id=customer_id, store_id=store_id, cap=cap, window_start_day=start_day,
                window_end_day=end_day, status="active", created_at=now)
    s.add(m)
    s.flush()
    MandateAdapter.create(m)
    s.add(Consent(customer_id=customer_id, store_id=store_id, type="payment_mandate", granted_at=now))
    score.apply_delta(s, customer_id, 5, "auto-pay set up", ref=f"mandate:{store_id}", store_id=store_id)
    return m


def verified_dues(s: Session, store_id: str, customer_id: str) -> int:
    """A mandate only ever clears dues the customer has confirmed."""
    return sum(ledger.remaining(e) for e in ledger.open_entries(s, store_id, customer_id) if e.verified_at)


def execute(s: Session, m: Mandate) -> Repayment | None:
    """Debit min(verified dues, cap) if today is inside the mandate window."""
    today = clock.today()
    if not (m.window_start_day <= today.day <= m.window_end_day):
        return None
    amount = min(verified_dues(s, m.store_id, m.customer_id), m.cap)
    if amount <= 0:
        return None
    MandateAdapter.execute(m, amount)
    rep = ledger.apply_repayment(s, m.store_id, m.customer_id, amount, "mandate", matched_by="mandate")
    score.apply_delta(s, m.customer_id, 3, "auto-pay executed", ref=f"mandate-pay:{rep.id}", store_id=m.store_id)
    for p in s.exec(select(Promise).where(Promise.customer_id == m.customer_id, Promise.store_id == m.store_id,
                                          Promise.status == "open")).all():
        if verified_dues(s, m.store_id, m.customer_id) == 0 or amount >= p.amount:
            p.status = "kept"
            s.add(p)
    return rep
