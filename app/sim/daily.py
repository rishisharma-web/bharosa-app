"""Daily jobs run by `advance_day` (spec 7.14), in order:

close yesterday's cash → expire unscanned entries → mark defaults → pay bills due today →
advance backstop → promises past their date → salary-day mandate sweeps → forecast →
integrity nightly → morning briefing.

In Demo Mode no organic customer activity is simulated between days, so every number
after `advance_day` is a consequence of scripted events and mandates only.
"""
import random
from datetime import datetime, time, timedelta

from sqlmodel import select

from app import clock
from app.adapters import soundbox
from app.adapters.payments import DistributorAdapter
from app.agents import munim
from app.core import forecast, integrity, ledger, score
from app.core.money import inr
from app.models import Advance, Bill, Entry, Mandate, Promise, Repayment, Sale, Store
from app.realtime.trace import trace

DEFAULT_AFTER_DAYS = 60
MORNING = time(9, 0)


def next_morning() -> datetime:
    return datetime.combine(clock.today() + timedelta(days=1), MORNING)


def close_day(s, store: Store, day) -> None:
    """Book the day's walk-in UPI sales (deterministic per store and date) and roll cash forward:
    daily net cash plus the shop's share of repayments received that day."""
    lo, hi = clock.datetime_floor(day), clock.datetime_floor(day + timedelta(days=1))
    total = round(store.avg_daily_upi_sales * random.Random(f"{store.id}:{day.isoformat()}").uniform(0.85, 1.15) / 10) * 10
    booked = sum(s.exec(select(Sale.amount).where(Sale.store_id == store.id, Sale.note.like("walk-in%"),
                                                  Sale.created_at >= lo, Sale.created_at < hi)).all())
    if total > booked:
        s.add(Sale(store_id=store.id, amount=total - booked, note="walk-in UPI (rest of day)",
                   created_at=datetime.combine(day, time(21, 0))))
    received = sum(s.exec(select(Repayment.merchant_share).where(
        Repayment.store_id == store.id, Repayment.created_at >= lo, Repayment.created_at < hi)).all())
    store.cash_on_hand += store.daily_net_cash + received
    s.add(store)


def mark_defaults(s) -> None:
    today = clock.today()
    for e in s.exec(select(Entry).where(Entry.state.in_(("verified", "partly_paid")), Entry.verified_at != None)).all():  # noqa: E711
        if ledger.overdue_days(e, today) > DEFAULT_AFTER_DAYS:
            e.state = "defaulted"
            s.add(e)
            trace("ledger", f"Entry #{e.id} > {DEFAULT_AFTER_DAYS} days overdue → defaulted", {"entry_id": e.id})
            score.apply_delta(s, e.customer_id, -40, "entry defaulted", ref=f"default:{e.id}", store_id=e.store_id)


def pay_bills_due(s) -> None:
    today = clock.today()
    for b in s.exec(select(Bill).where(Bill.status != "paid", Bill.due_date <= today)).all():
        store = s.get(Store, b.store_id)
        left = b.amount - b.paid_by_lender - b.paid_by_store
        b.paid_by_store += left
        b.status = "paid"
        store.cash_on_hand -= left
        s.add_all([b, store])
        DistributorAdapter.mark_paid(b, store.name, left)
        if store.cash_on_hand < 0:
            trace("forecast", f"{store.name} paid {b.distributor} but is {inr(-store.cash_on_hand)} short in cash")


def check_backstops(s) -> None:
    today = clock.today()
    for a in s.exec(select(Advance).where(Advance.state == "repaying", Advance.backstop_date <= today)).all():
        a.state = "backstop_due"
        s.add(a)
        trace("advance", f"{a.id}: {inr(a.total_due - a.repaid)} unpaid at backstop → becomes an instalment")


def settle_promises(s) -> None:
    today = clock.today()
    for p in s.exec(select(Promise).where(Promise.status == "open", Promise.date < today)).all():
        owed = sum(ledger.remaining(e) for e in ledger.open_entries(s, p.store_id, p.customer_id))
        p.status = "kept" if owed == 0 else "broken"
        s.add(p)


async def run_day(uow) -> list:
    """Advance the sim clock to tomorrow 09:00 and run the jobs. Returns effects."""
    s = uow.s
    yesterday = clock.today()
    clock.set(next_morning())
    trace("router", f"New day: {clock.today():%a %d %b}")
    for store in s.exec(select(Store)).all():
        close_day(s, store, yesterday)
    for e in ledger.expire_stale(s):
        soundbox.clear_front_if_showing(s, e.id)
    mark_defaults(s)
    pay_bills_due(s)
    check_backstops(s)
    settle_promises(s)

    effects = []
    today = clock.today()
    payers = s.exec(select(Mandate.customer_id).where(Mandate.status == "active",
                                                     Mandate.window_start_day == today.day).distinct()).all()
    for cid in sorted(payers):
        await uow.emit("salary_credited", {"customer_id": cid})

    for store in s.exec(select(Store)).all():
        fc = forecast.forecast(s, store.id)
        trace("forecast", f"{store.name}: 14-day forecast, {len(fc['gaps'])} gap(s)",
              {"gaps": fc["gaps"]})
    for store in s.exec(select(Store)).all():
        integrity.check(s, store.id, "nightly")
    b = await munim.compose_briefing(s, "S1")
    soundbox.display(s, "S1", front=soundbox.IDLE_FRONT)
    effects.append(soundbox.play("S1", b["text"], b["lang"]))
    return effects
