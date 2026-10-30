"""Priya's monthly basket (spec §4.8)."""
from conftest import ok

from app import db
from app.core import basket
from app.models import Entry


def test_prediction(world):
    with db.session() as s:
        p = basket.predict(s, "S1", "C_PRIYA")
    assert p["value"] == 1_850 and len(p["items"]) == 8
    assert {i["sku"]: i["qty"] for i in p["items"]} == {"ATTA10": 1, "RICE5": 1, "TOOR2": 1, "OIL1": 2, "SUG2": 1,
                                                        "TEA250": 1, "SALT1": 1, "DET1": 1}


def test_accept_creates_verified_entry_and_delivery(world):
    ok(world["merchant"].post("/api/merchant/growth/A_BASKET/approve"))
    offer = ok(world["C_PRIYA"].get("/api/customer/home"))["action_needed"]
    ok(world["C_PRIYA"].post(f"/api/customer/baskets/{offer['basket_id']}/accept"))
    with db.session() as s:
        e = s.query(Entry).filter(Entry.customer_id == "C_PRIYA", Entry.source == "basket").one()
        assert (e.state, e.amount, len(e.items)) == ("verified", 1_850, 8)
    [o] = ok(world["merchant"].get("/api/merchant/orders"))
    ok(world["merchant"].post(f"/api/merchant/baskets/{o['id']}/delivered"))
    assert ok(world["merchant"].get("/api/merchant/orders"))[0]["state"] == "delivered"
