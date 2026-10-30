"""Cash forecaster (spec 7.6). Deterministic 14-day projection.

    cash[d] = cash_on_hand + Σ_{t=today..d} (daily_net_cash + expected_collections[t]) − Σ bills due ≤ d

A bill is paid on its due day before that day's inflows, so the cash available for a
bill is cash_on_hand + inflows from today up to the day before it is due.

Expected collections per customer (only customers who owe something):
- active mandate at this store: verified dues, capped, on the next salary day (prob 1.0)
- an open promise (from the Recovery Agent) inside the horizon: that amount on that date
- otherwise, from the customer's own repayment history at this store:
  on_time_rate = entries settled by their due date / (settled entries + open overdue entries)
  pay_day      = last entry date + median days to pay
  amount       = open dues × on_time_rate, rounded to ₹10, placed on pay_day if it falls in
                 the horizon. A pay day already in the past is "late against habit" and is not
                 counted (nudges handle those). No history, or a 0 rate, contributes nothing.

Entries waiting for confirmation (proposed/disputed) are not dues yet and are ignored.
The core (`expected_collections`, `project`) is pure so the seed can calibrate against it.
"""
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlmodel import Session, select

from app import clock
from app.core import ledger
from app.core.money import round_half_up
from app.models import Bill, Customer, Entry, Mandate, Promise, Store

HORIZON_DAYS = 14


@dataclass
class History:
    customer_id: str
    name: str
    open_remaining: int = 0
    verified_dues: int = 0
    last_entry: date | None = None
    days_to_pay: list[int] = field(default_factory=list)
    settled_on_time: int = 0
    settled_total: int = 0
    open_overdue: int = 0
    mandate_cap: int | None = None
    mandate_day: int | None = None
    promises: list[tuple[date, int]] = field(default_factory=list)


@dataclass
class Collection:
    customer_id: str
    name: str
    date: date
    amount: int
    probability: float
    basis: str  # mandate | promise | history


def _next_day_of_month(today: date, day: int) -> date:
    d = today.replace(day=day) if today.day <= day else None
    if d is None:
        nxt = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        d = nxt.replace(day=day)
    return d


def expected_collections(hist: list[History], today: date, horizon: int = HORIZON_DAYS) -> list[Collection]:
    end = today + timedelta(days=horizon - 1)
    out: list[Collection] = []
    for h in hist:
        if h.open_remaining <= 0:
            continue
        if h.mandate_cap is not None:
            when = _next_day_of_month(today, h.mandate_day or 1)
            amt = min(h.verified_dues, h.mandate_cap)
            if amt and when <= end:
                out.append(Collection(h.customer_id, h.name, when, amt, 1.0, "mandate"))
            continue
        promised = [(d, a) for d, a in h.promises if today <= d <= end]
        if promised:
            out.extend(Collection(h.customer_id, h.name, d, min(a, h.open_remaining), 1.0, "promise")
                       for d, a in promised)
            continue
        if not h.days_to_pay or h.last_entry is None:
            continue
        rate = h.settled_on_time / (h.settled_total + h.open_overdue)
        amt = round_half_up(h.open_remaining * rate / 10) * 10
        when = h.last_entry + timedelta(days=round_half_up(statistics.median(h.days_to_pay)))
        if amt and today <= when <= end:
            out.append(Collection(h.customer_id, h.name, when, amt, round(rate, 2), "history"))
    return sorted(out, key=lambda c: (c.date, c.customer_id))


@dataclass
class BillDue:
    bill_id: str
    distributor: str
    due: date
    remaining: int  # what the store itself still has to pay


def project(today: date, cash_on_hand: int, daily_net_cash: int, collections: list[Collection],
            bills: list[BillDue], horizon: int = HORIZON_DAYS) -> dict:
    by_day: dict[date, int] = {}
    for c in collections:
        by_day[c.date] = by_day.get(c.date, 0) + c.amount
    cash, days, gaps = cash_on_hand, [], []
    for i in range(horizon):
        d = today + timedelta(days=i)
        due_today = [b for b in bills if (b.due <= d if i == 0 else b.due == d)]
        outflow = 0
        for b in due_today:
            available = cash - outflow
            gap = b.remaining - available
            if gap > 0:
                gaps.append({"bill_id": b.bill_id, "distributor": b.distributor, "due": b.due.isoformat(),
                             "amount": b.remaining, "available": available, "gap": gap,
                             "flagged_on": max(today, b.due - timedelta(days=1)).isoformat()})
            outflow += b.remaining
        coll = by_day.get(d, 0)
        inflow = daily_net_cash + coll
        cash = cash - outflow + inflow
        days.append({"date": d.isoformat(), "cash": cash, "inflow": inflow, "outflow": outflow, "collections": coll})
    return {"days": days, "gaps": gaps}


# ---------------------------------------------------------------- DB loading

def load_history(s: Session, store_id: str, today: date) -> list[History]:
    entries = s.exec(select(Entry).where(Entry.store_id == store_id,
                                         Entry.state.in_(ledger.OPEN_STATES + ("settled",)))).all()
    by_c: dict[str, History] = {}
    names = {c.id: c.name for c in s.exec(select(Customer).where(
        Customer.id.in_({e.customer_id for e in entries} or {""}))).all()}
    for e in entries:
        h = by_c.setdefault(e.customer_id, History(e.customer_id, names.get(e.customer_id, e.customer_id)))
        d = e.created_at.date()
        h.last_entry = d if h.last_entry is None else max(h.last_entry, d)
        if e.state == "settled":
            h.settled_total += 1
            h.settled_on_time += int(e.settled_at.date() <= e.due_date)
            h.days_to_pay.append((e.settled_at.date() - d).days)
        else:
            r = ledger.remaining(e)
            h.open_remaining += r
            if e.verified_at is not None:
                h.verified_dues += r
            if ledger.overdue_days(e, today) > 0:
                h.open_overdue += 1
    for m in s.exec(select(Mandate).where(Mandate.store_id == store_id, Mandate.status == "active")).all():
        if m.customer_id in by_c:
            by_c[m.customer_id].mandate_cap, by_c[m.customer_id].mandate_day = m.cap, m.window_start_day
    for p in s.exec(select(Promise).where(Promise.store_id == store_id, Promise.status == "open")).all():
        if p.customer_id in by_c:
            by_c[p.customer_id].promises.append((p.date, p.amount))
    return list(by_c.values())


def load_bills(s: Session, store_id: str) -> list[BillDue]:
    return [BillDue(b.id, b.distributor, b.due_date, b.amount - b.paid_by_lender - b.paid_by_store)
            for b in s.exec(select(Bill).where(Bill.store_id == store_id, Bill.status != "paid")).all()
            if b.amount - b.paid_by_lender - b.paid_by_store > 0]


def forecast(s: Session, store_id: str, days: int = HORIZON_DAYS) -> dict:
    """Spec 7.6 output: {days:[{date, cash, inflow, outflow}], gaps:[{bill_id, due, gap, flagged_on}]}."""
    store = s.get(Store, store_id)
    today = clock.today()
    colls = expected_collections(load_history(s, store_id, today), today, days)
    out = project(today, store.cash_on_hand, store.daily_net_cash, colls, load_bills(s, store_id), days)
    out["collections"] = [
        {"customer_id": c.customer_id, "name": c.name, "date": c.date.isoformat(), "amount": c.amount,
         "probability": c.probability, "basis": c.basis}
        for c in colls
    ]
    out["today"] = today.isoformat()
    out["cash_on_hand"] = store.cash_on_hand
    return out


def gap_for_bill(fc: dict, bill_id: str) -> dict | None:
    return next((g for g in fc["gaps"] if g["bill_id"] == bill_id), None)
