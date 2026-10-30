"""Diwali plan and Stock Advance sizing (spec §4.6)."""
from conftest import ok

from app import db
from app.core import advance, festive
from app.models import Bill


def test_plan_numbers(world):
    with db.session() as s:
        p = festive.for_store(s, "S1")
        assert (p["expected_extra"], p["order_total"], p["overall_uplift"]) == (27_400, 18_000, 1.6)
        assert [c["category"] for c in p["categories"]] == ["sweets_dryfruits", "oil_ghee", "snacks", "puja_items"]
        assert advance.v_eligible(s, "S1") == 23_200


def test_approve_creates_bill_and_offer(world):
    ok(world["merchant"].post("/api/merchant/growth/A_DIWALI/approve"))
    stock = ok(world["merchant"].get("/api/merchant/home"))["stock"]
    assert (stock["bill"]["amount"], stock["bill"]["due"], stock["bill"]["gap"]) == (18_000, "2026-11-06", 9_200)
    a = stock["advance"]
    assert (a["state"], a["amount"], a["fee"], a["total_due"], a["split_rate"]) == ("offered", 9_200, 138, 9_338, 0.2)
    with db.session() as s:
        z = advance.sizing(s, "S1", s.get(Bill, "B1"))
    assert (z["gap"], z["v_eligible"], z["cap"], z["amount"]) == (9_200, 23_200, 9_280, 9_200)


def test_accept_pays_the_distributor(world):
    ok(world["merchant"].post("/api/merchant/growth/A_DIWALI/approve"))
    ok(world["merchant"].post("/api/merchant/advance/A1/accept"))
    stock = ok(world["merchant"].get("/api/merchant/home"))["stock"]
    assert (stock["advance"]["state"], stock["advance"]["backstop"]) == ("repaying", "2026-11-30")
    assert (stock["bill"]["status"], stock["bill"]["paid_by_lender"], stock["bill"]["paid_by_store"]) == ("paid", 9_200, 8_800)
    assert world["merchant"].post("/api/merchant/advance/A1/accept").status_code == 409
