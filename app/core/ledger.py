"""Ledger and entry state machine (spec 7.2).

This file currently holds the read side (balances, overdue). The write side
(propose / confirm / dispute / allocate) is added with the credit-sale milestone.

Definitions used everywhere:
- open entry: state in OPEN_STATES (counts toward what the customer owes)
- remaining: amount - paid_amount
- verified receivable: `verified_at is not None` (independent of payment progress)
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlmodel import Session, select

from app.models import Entry

OPEN_STATES = ("verified", "partly_paid", "unverified", "defaulted")


def remaining(e: Entry) -> int:
    return e.amount - e.paid_amount


def is_verified(e: Entry) -> bool:
    return e.verified_at is not None


def overdue_days(e: Entry, today: date) -> int:
    if e.state not in OPEN_STATES:
        return 0
    return max(0, (today - e.due_date).days)


def open_entries(s: Session, store_id: str | None = None, customer_id: str | None = None) -> list[Entry]:
    q = select(Entry).where(Entry.state.in_(OPEN_STATES))
    if store_id:
        q = q.where(Entry.store_id == store_id)
    if customer_id:
        q = q.where(Entry.customer_id == customer_id)
    return list(s.exec(q.order_by(Entry.created_at, Entry.id)).all())


@dataclass
class Totals:
    outstanding: int = 0
    verified: int = 0
    unverified: int = 0
    overdue: int = 0
    oldest_overdue_days: int = 0
    open_count: int = 0

    def add(self, e: Entry, today: date) -> None:
        r = remaining(e)
        self.outstanding += r
        if is_verified(e):
            self.verified += r
        else:
            self.unverified += r
        d = overdue_days(e, today)
        if d > 0:
            self.overdue += r
            self.oldest_overdue_days = max(self.oldest_overdue_days, d)
        self.open_count += 1


def totals(entries: list[Entry], today: date) -> Totals:
    t = Totals()
    for e in entries:
        t.add(e, today)
    return t


def totals_by_customer(entries: list[Entry], today: date) -> dict[str, Totals]:
    out: dict[str, Totals] = defaultdict(Totals)
    for e in entries:
        out[e.customer_id].add(e, today)
    return out


def pending_confirm_count(s: Session, store_id: str) -> int:
    return len(s.exec(select(Entry.id).where(Entry.store_id == store_id, Entry.state == "proposed")).all())
