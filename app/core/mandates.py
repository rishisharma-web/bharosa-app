"""Salary-week auto-pay (v2 spec §4.9): set up and scheduled, never executed in the prototype.

Compliant design (UPI AutoPay): the customer approves a mandate with a cap; each month the
merchant side triggers the debit on the collection day, after a pre-debit notice at least 24 h
before, for the exact verified dues (never more than the cap). The customer can skip a month.
"""
from datetime import date, timedelta

from sqlmodel import Session, select

from app.config import now, today
from app.core import activity, payments
from app.core.money import inr
from app.errors import EventError
from app.models import Customer, Mandate, Store

DEFAULT_CAP = 3_000
DEFAULT_DAY = 2


def verified_dues(s: Session, store_id: str, customer_id: str) -> int:
    return sum(e.amount - e.paid for e in payments.open_entries(s, store_id, customer_id))


def next_collection(day: int) -> date:
    t = today()
    if t.day < day:
        return t.replace(day=day)
    first_next = (t.replace(day=1) + timedelta(days=32)).replace(day=1)
    return first_next.replace(day=day)


def active(s: Session, customer_id: str, store_id: str | None = None) -> list[Mandate]:
    q = select(Mandate).where(Mandate.customer_id == customer_id, Mandate.status == "active")
    if store_id:
        q = q.where(Mandate.store_id == store_id)
    return list(s.exec(q).all())


def schedule(s: Session, m: Mandate) -> dict:
    when = next_collection(m.collection_day)
    dues = verified_dues(s, m.store_id, m.customer_id)
    return {"mandate_id": m.id, "store": s.get(Store, m.store_id).name, "store_id": m.store_id, "cap": m.cap,
            "collection_day": m.collection_day, "next_collection": when.isoformat(),
            "notice_on": (when - timedelta(days=1)).isoformat(), "amount_now": min(dues, m.cap),
            "verified_dues": dues}


def create(s: Session, customer_id: str, store_id: str, cap: int, collection_day: int) -> Mandate:
    if not (500 <= cap <= 15_000):
        raise EventError("Cap must be between ₹500 and ₹15,000", 422)
    if not (1 <= collection_day <= 28):
        raise EventError("Collection day must be between 1 and 28", 422)
    if active(s, customer_id, store_id):
        raise EventError("Auto-pay is already set up for this shop", 409)
    m = Mandate(customer_id=customer_id, store_id=store_id, cap=cap, collection_day=collection_day, created_at=now())
    s.add(m)
    s.flush()
    sch = schedule(s, m)
    name = s.get(Customer, customer_id).name
    activity.log(s, store_id, "payment", f"{name} set up salary-week auto-pay: up to {inr(cap)}, "
                                         f"next collection {date.fromisoformat(sch['next_collection']):%a %d %b}")
    return m
