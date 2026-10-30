"""Ledger and entry state machine (spec 7.2).

    proposed ──confirm──► verified ──partial──► partly_paid ──full──► settled
       ├──dispute──► disputed ──correct──► proposed
       └──timeout (10 sim-min)──► unverified (still collectable, never lendable)

Definitions used everywhere:
- open entry: state in OPEN_STATES (counts toward what the customer owes)
- remaining: amount - paid_amount
- verified receivable: `verified_at is not None` (independent of payment progress)
"""
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlmodel import Session, select

from app import clock
from app.errors import EventError
from app.models import Entry, Store
from app.realtime.trace import trace

OPEN_STATES = ("verified", "partly_paid", "unverified", "defaulted")
CONFIRM_WINDOW = timedelta(minutes=10)


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


# ---------------------------------------------------------------- write side

def _require(e: Entry, *states: str) -> None:
    if e.state not in states:
        raise EventError(f"entry #{e.id} is {e.state}, expected {' or '.join(states)}", 409)


def _new_token(e: Entry) -> None:
    e.confirm_token = uuid.uuid4().hex
    e.token_expires_at = clock.now() + CONFIRM_WINDOW


def propose(s: Session, store: Store, customer_id: str, amount: int, requested: int,
            source_text: str | None = None, override: bool = False) -> Entry:
    """Create a proposed entry with a confirm token (customer scans to verify)."""
    if amount < 1:
        raise EventError("an udhaar entry needs a positive amount", 422)
    now = clock.now()
    e = Entry(store_id=store.id, customer_id=customer_id, amount=amount, requested_amount=requested,
              state="proposed", created_at=now, due_date=now.date() + timedelta(days=store.due_days),
              override=override, source_text=source_text)
    _new_token(e)
    s.add(e)
    s.flush()
    trace("ledger", f"Entry #{e.id} proposed ₹{amount}" + (" (override)" if override else ""),
          {"entry_id": e.id, "customer_id": customer_id, "amount": amount, "requested": requested})
    return e


def by_token(s: Session, token: str) -> Entry:
    e = s.exec(select(Entry).where(Entry.confirm_token == token)).first()
    if e is None:
        raise EventError("unknown confirmation code", 404)
    return e


def confirm(s: Session, e: Entry, device_id: str) -> Entry:
    if e.state == "unverified":
        raise EventError("this confirmation has expired; ask the shop for a new QR", 410)
    _require(e, "proposed")
    e.state = "verified"
    e.verified_at = clock.now()
    e.confirm_device_id = device_id
    e.token_expires_at = None
    s.add(e)
    trace("ledger", f"Entry #{e.id} proposed → verified", {"entry_id": e.id, "device_id": device_id})
    return e


def dispute(s: Session, e: Entry, reason: str, claimed_amount: int | None) -> Entry:
    _require(e, "proposed")
    e.state = "disputed"
    e.dispute_reason = reason
    e.dispute_amount = claimed_amount
    e.disputed_from_amount = e.amount
    e.token_expires_at = None
    s.add(e)
    trace("ledger", f"Entry #{e.id} disputed", {"entry_id": e.id, "reason": reason, "claimed": claimed_amount})
    return e


def correct(s: Session, e: Entry, amount: int) -> Entry:
    """Merchant answers a dispute with an amount; back to proposed with a fresh QR."""
    _require(e, "disputed")
    e.amount = amount
    e.state = "proposed"
    _new_token(e)
    s.add(e)
    trace("ledger", f"Entry #{e.id} corrected to ₹{amount} → proposed", {"entry_id": e.id, "amount": amount})
    return e


def override_amount(s: Session, e: Entry) -> Entry:
    """Shopkeeper ignores the guardrail split and gives the full requested amount."""
    _require(e, "proposed")
    if not e.requested_amount or e.requested_amount <= e.amount:
        raise EventError("nothing to override: entry already has the full amount", 409)
    e.amount = e.requested_amount
    e.override = True
    s.add(e)
    trace("ledger", f"Entry #{e.id} override → ₹{e.amount}", {"entry_id": e.id, "override": True})
    return e


def expire_stale(s: Session) -> list[Entry]:
    """proposed → unverified once the 10-minute (sim) confirm window has passed."""
    now = clock.now()
    stale = s.exec(select(Entry).where(Entry.state == "proposed", Entry.token_expires_at < now)).all()
    for e in stale:
        e.state = "unverified"
        s.add(e)
        trace("ledger", f"Entry #{e.id} not confirmed in 10 min → unverified", {"entry_id": e.id})
    return list(stale)
