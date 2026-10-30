"""Safe limit contract table (spec §4.2) and privacy of reasons."""
import pytest

from app import db, seed
from app.config import now
from app.core import risk
from app.models import ScoreShare


@pytest.fixture(autouse=True)
def seeded():
    seed.build()


@pytest.mark.parametrize("cid,amount,base,safe,band,credit,collect", [
    ("C_PRIYA", 340, 4_100, 4_100, "green", 340, 0),
    ("C_RAMESH", 340, 3_215, 200, "amber", 200, 140),
    ("C_VIKRAM", 340, 1_535, 0, "red", 0, 340),
    ("C_ANITA", 2_000, 4_025, 500, "amber", 500, 1_500),
])
def test_contract(cid, amount, base, safe, band, credit, collect):
    with db.session() as s:
        g = risk.evaluate(s, "S1", cid, amount)
    assert (g.base, g.safe_limit, g.band, g.credit_now, g.collect_now) == (base, safe, band, credit, collect)


def test_anita_shared():
    with db.session() as s:
        s.add(ScoreShare(customer_id="C_ANITA", store_id="S1", granted_at=now()))
        s.flush()
        g = risk.evaluate(s, "S1", "C_ANITA", 2_000)
    assert (g.base, g.safe_limit, g.band, g.credit_now, g.collect_now) == (4_025, 1_500, "amber", 1_500, 500)
    assert g.tags == ["New · Paytm network"]
    text = " ".join(g.reasons)
    assert "Network exposure room ₹3,425" in text
    assert "Other Paytm shops" not in text and "NET" not in text and "₹600" not in text


def test_ramesh_reasons():
    with db.session() as s:
        g = risk.evaluate(s, "S1", "C_RAMESH", 340)
    assert g.reasons == ["Score 662 → base ₹3,215", "₹1,700 overdue for 19 days → ×0.6", "Already owes ₹1,700 here"]
    assert risk.verdict(g, "Ramesh Kumar", 500) == "Caution. Give ₹200 on credit, collect ₹140 now."
