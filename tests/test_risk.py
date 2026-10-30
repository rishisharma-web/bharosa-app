"""Risk engine contract values (spec 7.3) and formula edges."""
import statistics
import time

import pytest

from app import db
from app.core import risk
from app.core.money import floor_to, inr, round_half_up
from app.core.risk import Features


def feats(score=680, owed=0, d=0, new=False, starter=500, overdue=None):
    return Features("C_X", "S1", score, owed, d, owed if overdue is None else overdue, new, starter)


@pytest.mark.parametrize("cid,limit,band,credit,collect", [
    ("C_RAMESH", 200, "amber", 200, 140),
    ("C_PRIYA", 4_100, "green", 340, 0),
    ("C_VIKRAM", 0, "red", 0, 340),
    ("C_ANITA", 500, "green", 340, 0),
])
def test_contract_values(fresh, cid, limit, band, credit, collect):
    with db.session() as s:
        r = risk.evaluate(s, "S1", cid, 340)
    assert (r.safe_limit, r.band, r.credit_now, r.collect_now) == (limit, band, credit, collect)


def test_ramesh_reasons(fresh):
    with db.session() as s:
        r = risk.evaluate(s, "S1", "C_RAMESH", 340)
    assert r.reasons == ["₹1,800 overdue for 19 days → limit ×0.6", "Score 680 → base ₹3,350", "Already owes ₹1,800"]
    assert r.features["is_new"] is False


def test_anita_is_new(fresh):
    with db.session() as s:
        r = risk.evaluate(s, "S1", "C_ANITA", 300)
    assert r.features["is_new"] and r.safe_limit == 500 and r.band == "green"


@pytest.mark.parametrize("d,m", [(0, 1.0), (1, 0.75), (14, 0.75), (15, 0.6), (30, 0.6), (31, 0.0)])
def test_overdue_multiplier_buckets(d, m):
    assert float(risk.multiplier(d)) == m


def test_base_line_endpoints():
    assert risk.base_limit(300) == 500
    assert risk.base_limit(900) == 5_000


def test_limit_capped_and_floored():
    assert risk.compute(feats(score=900), 100).safe_limit == 5_000
    assert risk.compute(feats(score=900, owed=10), 100).safe_limit == 4_950  # floor50(4,990)
    assert risk.compute(feats(score=300, owed=600), 100).safe_limit == 0  # never negative


def test_band_rules():
    assert risk.compute(feats(score=900), 5_000).band == "green"  # amount == limit is green
    assert risk.compute(feats(score=900), 5_001).band == "amber"
    assert risk.compute(feats(d=40, owed=100), 10).band == "red"


def test_new_customer_pending_reduces_starter():
    r = risk.compute(feats(new=True, owed=300), 300)
    assert r.safe_limit == 200 and r.band == "amber"


def test_pending_entries_count_as_owed(fresh):
    """A second sale while the first ₹200 waits for a scan must not get a fresh ₹200."""
    fresh.post("/api/events", json={"type": "udhaar_spoken",
                                    "payload": {"store_id": "S1", "customer_id": "C_RAMESH", "amount": 340}})
    with db.session() as s:
        r = risk.evaluate(s, "S1", "C_RAMESH", 340)
    assert r.safe_limit == 0 and r.band == "red"


def test_latency_p95_under_50ms(fresh):
    samples = []
    with db.session() as s:
        for cid in ["C_RAMESH", "C_PRIYA", "C_VIKRAM", "C_ANITA"] * 25:
            t0 = time.perf_counter()
            risk.evaluate(s, "S1", cid, 340)
            samples.append((time.perf_counter() - t0) * 1000)
    assert statistics.quantiles(samples, n=20)[-1] < 50


def test_money_helpers():
    assert floor_to(2010, 50) == 2_000
    assert round_half_up(2.5) == 3 and round_half_up(137.5) == 138
    assert inr(1_800) == "₹1,800" and inr(150_000) == "₹1,50,000" and inr(45_000) == "₹45,000"
