"""Roles and privacy (spec §6.2)."""
import json

from conftest import counter, ok

from fastapi.testclient import TestClient


def test_merchant_never_sees_network_data(world):
    counter(world, "C_ANITA", 2_000, accept=False)
    m = world["merchant"]
    blobs = [m.get(p).text for p in ("/api/merchant/home", "/api/merchant/udhaar-book", "/api/merchant/collect")]
    for b in blobs:
        assert "Other Paytm shops" not in b and '"NET"' not in b
    book = ok(m.get("/api/merchant/udhaar-book"))
    assert "C_ANITA" not in {r["id"] for r in book}  # not a customer here until she confirms
    assert m.get("/api/merchant/customers/C_ANITA").status_code == 404


def test_customer_isolation(world):
    priya = world["C_PRIYA"]
    home = ok(priya.get("/api/customer/home"))
    assert home["customer"]["id"] == "C_PRIYA"
    assert "Ramesh" not in json.dumps(home)
    counter(world, "C_RAMESH", 340)
    token = ok(world["soundbox"].get("/api/soundbox/state"))["front"]["token"]
    assert priya.get(f"/api/requests/{token}").status_code == 403


def test_roles_and_anonymous(world):
    from app.main import app
    anon = TestClient(app)
    assert anon.get("/api/customer/home").status_code == 401
    assert anon.get("/api/merchant/home").status_code == 401
    assert world["C_RAMESH"].get("/api/merchant/home").status_code == 401
    assert world["merchant"].get("/api/customer/home").status_code == 401
    assert anon.post("/api/admin/reset").status_code == 401
    assert anon.post("/api/auth/otp/verify", json={"phone": "9000000012", "otp": "000000", "app": "customer"}).status_code == 401
    state = ok(anon.get("/api/soundbox/state"))  # the counter shows only its own display
    assert set(state) == {"store", "vpa", "top", "front", "ai_enabled", "voice_lang"}


def test_magic_link_is_one_time(world):
    from tests.conftest import ADMIN
    from app.main import app
    url = ok(world["soundbox"].post("/api/admin/magic", headers=ADMIN, json={"customer_id": "C_ANITA"}))["url"]
    path = url.replace("http://testserver", "")
    phone = TestClient(app)
    r = phone.get(path, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/customer"
    assert ok(phone.get("/api/me/customer"))["customer_id"] == "C_ANITA"
    assert TestClient(app).get(path, follow_redirects=False).status_code == 410
