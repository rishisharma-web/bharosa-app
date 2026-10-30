"""Pending requests: identity, expiry, share and decline (spec §4.4, §5.1–5.2)."""
from datetime import timedelta

from conftest import counter, ok

from app import db
from app.models import Entry, PendingRequest


def _front(w):
    return ok(w["soundbox"].get("/api/soundbox/state"))["front"]


def test_confirm_only_by_its_customer(world):
    counter(world, "C_RAMESH", 340)
    f = _front(world)
    assert f["mode"] == "confirm_qr" and f["qr_url"].endswith(f"/c/r/{f['token']}") and len(f["token"]) == 22
    r = world["C_PRIYA"].get(f"/api/requests/{f['token']}")
    assert r.status_code == 403 and r.json()["detail"] == "This request is for another customer."
    assert world["C_PRIYA"].post(f"/api/requests/{f['token']}/confirm", json={"pay_method": "upi"}).status_code == 403
    assert world["C_RAMESH"].post(f"/api/requests/{f['token']}/confirm", json={}).status_code == 422  # pay-now method needed
    ok(world["C_RAMESH"].post(f"/api/requests/{f['token']}/confirm", json={"pay_method": "upi", "device_id": "d1"}))
    assert _front(world)["message"] == "✓ Confirmed by Ramesh"
    home = ok(world["C_RAMESH"].get("/api/customer/home"))
    assert home["dues"][0]["amount"] == 1_900


def test_request_expires_after_15_minutes(world):
    counter(world, "C_RAMESH", 340)
    token = _front(world)["token"]
    with db.session() as s:
        r = s.get(PendingRequest, token)
        r.expires_at = r.created_at - timedelta(seconds=1)
        s.add(r)
        s.commit()
    assert ok(world["C_RAMESH"].get(f"/api/requests/{token}"))["status"] == "expired"
    assert world["C_RAMESH"].post(f"/api/requests/{token}/confirm", json={"pay_method": "upi"}).status_code == 410
    with db.session() as s:
        assert s.get(Entry, s.get(PendingRequest, token).entry_id).state == "expired"
    assert _front(world)["mode"] == "idle"


def test_share_gives_1500_and_creates_the_confirm_step(world):
    top, _ = counter(world, "C_ANITA", 2_000, accept=False)
    assert top["band"] == "waiting"
    f = _front(world)
    assert f["mode"] == "share_qr"
    out = ok(world["C_ANITA"].post(f"/api/requests/{f['token']}/share", json={"decision": "share"}))
    req = ok(world["C_ANITA"].get(f"/api/requests/{out['next_token']}"))
    assert (req["kind"], req["credit_now"], req["collect_now"]) == ("confirm", 1_500, 500)
    ok(world["C_ANITA"].post(f"/api/requests/{out['next_token']}/confirm", json={"pay_method": "credit_line", "device_id": "d9"}))
    home = ok(world["merchant"].get("/api/merchant/home"))
    assert home["counter_feed"][0]["tags"] == ["New · Paytm network"] and home["summary"]["new_customers_won"] == 1


def test_decline_share_gives_starter_limit(world):
    counter(world, "C_ANITA", 2_000, accept=False)
    out = ok(world["C_ANITA"].post(f"/api/requests/{_front(world)['token']}/share", json={"decision": "decline"}))
    req = ok(world["C_ANITA"].get(f"/api/requests/{out['next_token']}"))
    assert (req["credit_now"], req["collect_now"]) == (500, 1_500)


def test_red_creates_no_entry(world):
    counter(world, "C_VIKRAM", 340)
    f = _front(world)
    assert f["mode"] == "pay_full"
    with db.session() as s:
        assert not s.query(Entry).filter(Entry.customer_id == "C_VIKRAM", Entry.state == "proposed").all()


def test_dispute_then_merchant_cancels(world):
    counter(world, "C_RAMESH", 340)
    token = _front(world)["token"]
    ok(world["C_RAMESH"].post(f"/api/requests/{token}/dispute", json={"reason": "Wrong amount"}))
    entry_id = world["merchant"].get("/api/merchant/customers/C_RAMESH").json()["entries"][0]["id"]
    ok(world["merchant"].post(f"/api/merchant/entries/{entry_id}/cancel"))
    with db.session() as s:
        assert s.get(Entry, entry_id).state == "cancelled"


def test_shared_device_is_flagged(world):
    counter(world, "C_RAMESH", 340)
    ok(world["C_RAMESH"].post(f"/api/requests/{_front(world)['token']}/confirm", json={"pay_method": "upi", "device_id": "same"}))
    counter(world, "C_PRIYA", 340)
    ok(world["C_PRIYA"].post(f"/api/requests/{_front(world)['token']}/confirm", json={"device_id": "same"}))
    with db.session() as s:
        e = s.query(Entry).filter(Entry.customer_id == "C_PRIYA", Entry.source == "counter").one()
        assert e.integrity_flag
