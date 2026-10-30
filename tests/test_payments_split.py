"""Sale vs repayment, FIFO, credit balance and the 20% lender split (spec §4.5)."""
from conftest import counter, ok

from app import db
from app.models import Entry, Payment, StoreCustomer


def _accept_advance(w):
    ok(w["merchant"].post("/api/merchant/growth/A_DIWALI/approve"))
    ok(w["merchant"].post("/api/merchant/advance/A1/accept"))


def test_sale_never_touches_dues(world):
    counter(world, "C_RAMESH", 340)
    token = ok(world["soundbox"].get("/api/soundbox/state"))["front"]["token"]
    ok(world["C_RAMESH"].post(f"/api/requests/{token}/confirm", json={"pay_method": "upi", "device_id": "d"}))
    with db.session() as s:
        sale = s.query(Payment).filter(Payment.purpose == "sale").one()
        assert (sale.amount, sale.method) == (140, "upi")
        old = s.query(Entry).filter(Entry.customer_id == "C_RAMESH", Entry.amount == 1_700).one()
        assert (old.paid, old.state) == (0, "verified")


def test_repayment_split_400_100(world):
    _accept_advance(world)
    out = ok(world["C_RAMESH"].post("/api/customer/pay", json={"store_id": "S1", "amount": 500, "method": "upi"}))
    assert (out["merchant_share"], out["lender_share"]) == (400, 100)
    with db.session() as s:
        e = s.query(Entry).filter(Entry.customer_id == "C_RAMESH", Entry.amount == 1_700).one()
        assert (e.state, e.amount - e.paid) == ("partly_paid", 1_200)
    assert ok(world["merchant"].get("/api/merchant/home"))["stock"]["advance"]["repaid"] == 100


def test_no_split_without_advance_and_fifo_excess(world):
    counter(world, "C_RAMESH", 340)
    token = ok(world["soundbox"].get("/api/soundbox/state"))["front"]["token"]
    ok(world["C_RAMESH"].post(f"/api/requests/{token}/confirm", json={"pay_method": "upi", "device_id": "d"}))
    out = ok(world["C_RAMESH"].post("/api/customer/pay", json={"store_id": "S1", "amount": 2_000, "method": "upi"}))
    assert out["lender_share"] == 0
    with db.session() as s:
        states = sorted((e.amount, e.state) for e in s.query(Entry).filter(
            Entry.customer_id == "C_RAMESH", Entry.created_at >= "2026-09-01").all())
        assert states == [(200, "settled"), (1_700, "settled")]  # oldest first, both cleared
        assert s.get(StoreCustomer, ("S1", "C_RAMESH")).credit_balance == 100
