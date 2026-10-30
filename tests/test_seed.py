"""Seed contracts: the simplified, round-number world (see app/sim/seed.py docstring)."""
import time
from datetime import date, timedelta

import pytest
from sqlmodel import select

from app import clock, db
from app.core import advance, forecast, ledger
from app.models import Bill, Customer, Entry, Mandate, StoreCustomer
from app.sim import seed as seed_mod


@pytest.fixture(scope="module")
def world():
    t0 = time.perf_counter()
    seed_mod.seed()
    elapsed = time.perf_counter() - t0
    with db.session() as s:
        clock.load(s)
        yield s, elapsed


def _per_customer(s):
    return ledger.totals_by_customer(ledger.open_entries(s, "S1"), clock.today())


def test_seed_is_fast(world):
    assert world[1] < 5


def test_clock_starts_monday_morning(world):
    assert clock.now().isoformat() == "2026-10-26T09:00:00"
    assert clock.today().weekday() == 0


def test_store_totals_are_round(world):
    s, _ = world
    t = ledger.totals(ledger.open_entries(s, "S1"), clock.today())
    assert (t.outstanding, t.verified, t.unverified, t.overdue) == (18_000, 17_000, 1_000, 7_000)
    assert len(s.exec(select(StoreCustomer).where(StoreCustomer.store_id == "S1")).all()) == 9


@pytest.mark.parametrize("cid,score,outstanding,overdue_days", [
    ("C_PRIYA", 780, 0, 0),
    ("C_RAMESH", 660, 1_500, 20),
    ("C_VIKRAM", 420, 2_500, 45),
])
def test_story_customers(world, cid, score, outstanding, overdue_days):
    s, _ = world
    assert s.get(Customer, cid).score == score
    t = _per_customer(s).get(cid)
    assert (t.outstanding if t else 0) == outstanding
    assert (t.verified if t else 0) == outstanding
    assert (t.oldest_overdue_days if t else 0) == overdue_days
    assert not s.exec(select(Mandate).where(Mandate.customer_id == cid)).all()


def test_story_open_entries_exact(world):
    s, _ = world

    def open_for(cid):
        return [(e.amount, e.created_at.date(), e.due_date) for e in ledger.open_entries(s, "S1", cid)]
    assert open_for("C_RAMESH") == [(1_500, date(2026, 9, 6), date(2026, 10, 6))]
    assert open_for("C_VIKRAM") == [(2_500, date(2026, 8, 12), date(2026, 9, 11))]
    assert s.get(Customer, "C_RAMESH").vpa == "ramesh.k@ptyes"


def test_background_auto_pay_sweeps_8100(world):
    s, _ = world
    mandates = s.exec(select(Mandate).where(Mandate.store_id == "S1", Mandate.status == "active")).all()
    assert {m.customer_id for m in mandates} == {"C_MEENA", "C_ARJUN", "C_KAVYA"}
    per = _per_customer(s)
    assert sum(per[m.customer_id].verified for m in mandates) == 8_100
    for m in mandates:
        assert per[m.customer_id].verified <= m.cap and per[m.customer_id].unverified == 0


def test_bill_gap_and_advance_cap(world):
    s, _ = world
    b = s.get(Bill, "B1")
    assert (b.distributor, b.amount, b.due_date) == ("Sharma Traders", 15_000, date(2026, 10, 30))
    [g] = forecast.forecast(s, "S1")["gaps"]
    assert (g["available"], g["gap"]) == (10_000, 5_000)
    assert advance.v_eligible(s, "S1") == 14_500  # cap ₹5,800 ≥ the ₹5,000 gap


def test_rule2_cannot_steal_the_kamala_payment(world):
    """No customer without a UPI ID has an open entry of exactly ₹500 (spec 7.5 rule 2)."""
    s, _ = world
    no_vpa = {c.id for c in s.exec(select(Customer).where(Customer.vpa == None)).all()}  # noqa: E711
    assert no_vpa == {"C_IMRAN"}
    assert not [e for e in ledger.open_entries(s, "S1") if e.customer_id in no_vpa and ledger.remaining(e) == 500]


def test_entry_bookkeeping_consistent(world):
    s, _ = world
    for e in s.exec(select(Entry)).all():
        assert 0 <= e.paid_amount <= e.amount
        assert e.due_date == e.created_at.date() + timedelta(days=30)
        if e.state == "settled":
            assert e.paid_amount == e.amount and e.settled_at is not None
        if e.state == "verified":
            assert e.verified_at is not None and e.paid_amount == 0
        if e.state == "unverified":
            assert e.verified_at is None and e.paid_amount == 0


def test_s2_has_a_steady_baseline(world):
    """Integrity R2 compares a day's credit with the 30-day average; it must hold all demo week."""
    s, _ = world
    for start in (date(2026, 9, 25), date(2026, 10, 2)):  # R2's window on Mon 26 Oct and on Sun 1 Nov
        lo, hi = clock.datetime_floor(start), clock.datetime_floor(start + timedelta(days=30))
        recent = sum(e.amount for e in s.exec(select(Entry).where(
            Entry.store_id == "S2", Entry.verified_at >= lo, Entry.verified_at < hi)).all())
        assert recent / 30 * 3 > 8_000  # the injected ring's ₹8,000 must not look like a burst


def test_seed_is_deterministic():
    def fingerprint():
        seed_mod.seed()
        with db.session() as s:
            return [(e.customer_id, e.amount, e.created_at, e.paid_amount, e.state)
                    for e in s.exec(select(Entry).order_by(Entry.id)).all()]
    assert fingerprint() == fingerprint()
