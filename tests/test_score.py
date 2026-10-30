"""Bharosa Score computed from history (spec §4.1)."""
import pytest

from app import db, seed
from app.core import score


@pytest.fixture(scope="module", autouse=True)
def seeded():
    seed.build()


@pytest.mark.parametrize("cid,expected,band", [
    ("C_PRIYA", 780, "Strong"), ("C_RAMESH", 662, "Good"), ("C_VIKRAM", 438, "Building"), ("C_ANITA", 770, "Strong"),
    ("C_SURESH", 690, "Good"), ("C_KAVYA", 690, "Good"), ("C_IMRAN", 690, "Good"), ("C_MEENA", 690, "Good"),
    ("C_ROHIT", 690, "Good"), ("C_LATA", 690, "Good"),
])
def test_scores(cid, expected, band):
    with db.session() as s:
        sc = score.for_customer(s, cid)
    assert (sc.value, sc.band) == (expected, band)
    assert sum(line["points"] for line in sc.breakdown) == sc.value


def test_ramesh_breakdown_lines():
    with db.session() as s:
        lines = [(x["label"], x["points"]) for x in score.for_customer(s, "C_RAMESH").breakdown]
    assert lines == [("Starting score", 600), ("8 on-time repayments", 120), ("2 late repayments", -20),
                     ("Overdue for 19 days now", -38)]


def test_store_totals_at_reset():
    from app.core import payments
    with db.session() as s:
        opens = [e for cid in ("C_RAMESH", "C_VIKRAM", "C_SURESH", "C_KAVYA", "C_IMRAN", "C_MEENA", "C_ROHIT", "C_LATA")
                 for e in payments.open_entries(s, "S1", cid)]
        assert sum(e.amount - e.paid for e in opens) == 25_800
        assert sum(e.amount - e.paid for e in opens if score.overdue_days(e)) == 4_300
