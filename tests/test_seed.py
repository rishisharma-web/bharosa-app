"""Seed contracts (spec 4.2 and the M1 acceptance check)."""
import time
from datetime import date, timedelta

import pytest
from sqlmodel import select

from app import clock, db
from app.core import ledger
from app.models import Bill, Customer, Entry, Mandate, StoreCustomer
from app.sim import seed as seed_mod
from app.sim.personas import RESERVED_TOKENS


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
    _, elapsed = world
    assert elapsed < 5


def test_clock_starts_monday_morning(world):
    assert clock.now().isoformat() == "2026-10-26T09:00:00"
    assert clock.today().weekday() == 0


def test_store_totals(world):
    s, _ = world
    t = ledger.totals(ledger.open_entries(s, "S1"), clock.today())
    assert abs(t.outstanding - 45_000) <= 500
    assert abs(t.verified - 38_000) <= 500


def test_v_eligible_supports_the_advance(world):
    s, _ = world
    scores = {c.id: c.score for c in s.exec(select(Customer)).all()}
    v_eligible = sum(
        ledger.remaining(e) for e in ledger.open_entries(s, "S1")
        if e.verified_at and e.state in ("verified", "partly_paid") and scores[e.customer_id] >= 550
    )
    assert v_eligible >= 23_000
    assert 0.4 * v_eligible >= 9_200


@pytest.mark.parametrize("cid,score,outstanding,overdue_days", [
    ("C_RAMESH", 680, 1_800, 19),
    ("C_PRIYA", 780, 0, 0),
    ("C_VIKRAM", 420, 2_600, 41),
    ("C_SURESH", 610, 900, 0),
    ("C_ANITA", 600, 0, 0),
])
def test_named_customers(world, cid, score, outstanding, overdue_days):
    s, _ = world
    c = s.get(Customer, cid)
    assert c.score == score
    t = _per_customer(s).get(cid)
    assert (t.outstanding if t else 0) == outstanding
    assert (t.verified if t else 0) == outstanding  # all named dues are verified
    assert (t.oldest_overdue_days if t else 0) == overdue_days
    assert s.get(StoreCustomer, ("S1", cid)) is not None
    assert not s.exec(select(Mandate).where(Mandate.customer_id == cid)).all()


def test_named_open_entries_exact(world):
    s, _ = world
    def open_for(cid):
        return [(e.amount, e.created_at.date(), e.due_date) for e in ledger.open_entries(s, "S1", cid)]
    assert open_for("C_RAMESH") == [(1_800, date(2026, 9, 7), date(2026, 10, 7))]
    assert open_for("C_VIKRAM") == [(2_600, date(2026, 8, 16), date(2026, 9, 15))]
    assert open_for("C_SURESH") == [(900, date(2026, 10, 20), date(2026, 11, 19))]
    assert s.get(Customer, "C_RAMESH").vpa == "ramesh.k@ptyes"
    assert s.get(Customer, "C_SURESH").vpa is None


def test_anita_is_new(world):
    s, _ = world
    assert s.get(Customer, "C_ANITA").is_new
    assert not s.exec(select(Entry).where(Entry.customer_id == "C_ANITA")).all()


def test_eight_mandates_sweep_about_9000(world):
    s, _ = world
    mandates = s.exec(select(Mandate).where(Mandate.store_id == "S1", Mandate.status == "active")).all()
    assert len(mandates) == 8
    per = _per_customer(s)
    dues = [per[m.customer_id].verified if m.customer_id in per else 0 for m in mandates]
    assert abs(sum(dues) - 9_000) <= 500
    for m, d in zip(mandates, dues):
        assert d <= m.cap
        assert per[m.customer_id].unverified == 0  # mandates only sweep verified dues
        assert s.get(Customer, m.customer_id).persona == "salary_day"


def test_bill_b1(world):
    s, _ = world
    b = s.get(Bill, "B1")
    assert (b.distributor, b.amount, b.due_date, b.status) == ("Sharma Traders", 18_000, date(2026, 10, 30), "due")


def test_rule2_cannot_steal_the_kamala_payment(world):
    """No no-VPA customer at S1 may have an open entry of exactly ₹500 (spec 7.5 rule 2)."""
    s, _ = world
    no_vpa = {c.id for c in s.exec(select(Customer).where(Customer.vpa == None)).all()}  # noqa: E711
    assert not [e for e in ledger.open_entries(s, "S1") if e.customer_id in no_vpa and ledger.remaining(e) == 500]


def test_no_lookalike_names(world):
    s, _ = world
    for c in s.exec(select(Customer)).all():
        if c.id.startswith("C_") and c.id[2:].isdigit():
            assert not {t.lower() for t in c.name.split()} & RESERVED_TOKENS, c.name


def test_entry_bookkeeping_consistent(world):
    s, _ = world
    for e in s.exec(select(Entry)).all():
        assert 0 <= e.paid_amount <= e.amount
        assert e.due_date == e.created_at.date() + timedelta(days=30)
        if e.state == "settled":
            assert e.paid_amount == e.amount and e.settled_at is not None
        if e.state == "partly_paid":
            assert 0 < e.paid_amount < e.amount
        if e.state in ("verified", "defaulted"):
            assert e.verified_at is not None
        if e.state == "unverified":
            assert e.verified_at is None and e.paid_amount == 0


def test_s2_has_a_realistic_baseline(world):
    """Integrity R2 compares a day's credit with the 30-day average; S2 needs real history."""
    s, _ = world
    for start in (date(2026, 9, 25), date(2026, 10, 2)):  # R2's window on Mon 26 Oct and on Sun 1 Nov
        lo, hi = clock.datetime_floor(start), clock.datetime_floor(start + timedelta(days=30))
        recent = sum(e.amount for e in s.exec(select(Entry).where(
            Entry.store_id == "S2", Entry.verified_at >= lo, Entry.verified_at < hi)).all())
        assert recent / 30 * 3 > 8_000  # the injected ring's ₹8,000 must not look like a burst


def test_world_is_deterministic():
    a, b = seed_mod.build_world(42), seed_mod.build_world(42)
    fp = lambda w: [(e.customer_id, e.amount, e.created_at, e.paid) for e in w.entries]  # noqa: E731
    assert fp(a) == fp(b)
    assert [c.name for c in a.customers] == [c.name for c in b.customers]
