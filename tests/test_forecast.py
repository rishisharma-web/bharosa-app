"""Forecaster (spec 7.6): the B1 gap contract and the projection rules."""
from datetime import date

from app import db
from app.core import forecast
from app.core.forecast import BillDue, Collection, History, expected_collections, project

MON = date(2026, 10, 26)


def test_b1_gap_contract(fresh):
    with db.session() as s:
        fc = forecast.forecast(s, "S1")
    [g] = fc["gaps"]
    assert (g["bill_id"], g["available"], g["gap"], g["flagged_on"]) == ("B1", 8_800, 9_200, "2026-10-29")
    before_fri = [c for c in fc["collections"] if c["date"] < "2026-10-30"]
    assert [(c["customer_id"], c["date"], c["amount"]) for c in before_fri] == [("C_SURESH", "2026-10-27", 800)]
    assert fc["days"][0] == {"date": "2026-10-26", "cash": 4_400, "inflow": 1_200, "outflow": 0, "collections": 0}


def test_snapshot_due_soon_shows_gap(fresh):
    [d] = fresh.get("/api/snapshot").json()["merchant"]["due_soon"]
    assert (d["bill_id"], d["amount"], d["gap"], d["due"]) == ("B1", 18_000, 9_200, "2026-10-30")


def test_briefing_ready_at_reset(fresh):
    b = fresh.get("/api/snapshot").json()["merchant"]["briefing"]
    assert b["lang"] == "hi-IN" and "₹9,200" in b["text"] and "Sharma Traders" in b["text"]
    assert b["text_en"].endswith("Sharma Traders ₹18,000 due Fri: ₹9,200 short.")
    assert b["summary"]["yesterday_sales"] > 0


def test_mandate_collection_on_next_salary_day():
    h = History("C", "C", open_remaining=1_000, verified_dues=900, mandate_cap=500, mandate_day=1)
    [c] = expected_collections([h], MON)
    assert (c.date, c.amount, c.basis) == (date(2026, 11, 1), 500, "mandate")


def test_promise_overrides_history():
    h = History("C", "C", open_remaining=2_000, last_entry=MON, days_to_pay=[2], settled_on_time=1,
                settled_total=1, promises=[(date(2026, 11, 1), 2_000)])
    [c] = expected_collections([h], MON)
    assert (c.date, c.amount, c.basis) == (date(2026, 11, 1), 2_000, "promise")


def test_history_rate_and_stale_pay_day():
    fresh_h = History("A", "A", open_remaining=600, last_entry=date(2026, 10, 24), days_to_pay=[3, 5, 4],
                      settled_on_time=3, settled_total=3, open_overdue=1)
    stale = History("B", "B", open_remaining=600, last_entry=date(2026, 10, 1), days_to_pay=[5],
                    settled_on_time=1, settled_total=1)
    never = History("C", "C", open_remaining=600, last_entry=date(2026, 10, 24))
    [c] = expected_collections([fresh_h, stale, never], MON)
    assert (c.customer_id, c.date, c.amount) == ("A", date(2026, 10, 28), 450)  # 600 × 3/4


def test_bill_is_paid_before_that_days_inflow():
    out = project(MON, 1_000, 500, [Collection("A", "A", date(2026, 10, 27), 300, 1.0, "history")],
                  [BillDue("B", "D", date(2026, 10, 27), 2_000)])
    [g] = out["gaps"]
    assert (g["available"], g["gap"]) == (1_500, 500)  # Mon only: 1,000 + 500
    assert out["days"][1]["cash"] == 1_500 - 2_000 + 800
