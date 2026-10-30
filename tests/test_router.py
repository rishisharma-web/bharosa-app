"""Event router, snapshot and health endpoints (spec 7.1, 10)."""
from sqlmodel import select

from app import db
from app.models import Event


def test_health(client):
    r = client.get("/api/health").json()
    assert r["ok"] is True
    assert r["sim_now"] == "2026-10-26T09:00:00+05:30" or r["sim_now"].startswith("2026-10-26")


def test_snapshot_shape(fresh):
    snap = fresh.get("/api/snapshot").json()
    for key in ("now", "lang", "demo", "soundbox", "merchant", "customer", "risk_console", "trace_tail"):
        assert key in snap
    m = snap["merchant"]
    assert m["store"] == {"id": "S1", "name": "Lakshmi Stores", "area": "Jayanagar, Bengaluru",
                          "vpa": "lakshmistores@ptyes", "advance_blocked": False}
    assert m["udhaar"]["outstanding"] == 45_000
    assert m["udhaar"]["verified"] == 38_000
    assert m["udhaar"]["pending_confirm"] == 0
    assert m["today_collection"] == 980  # early-morning walk-in sales on demo day
    assert m["due_soon"][0]["bill_id"] == "B1"
    assert snap["now"] == "2026-10-26T09:00:00+05:30"
    c = snap["customer"]
    assert c["id"] == "C_RAMESH" and c["score"] == 680 and c["score_band"] == "Good"
    assert c["dues"] == [{"store": "Lakshmi Stores", "store_id": "S1", "amount": 1800, "verified": 1800,
                          "oldest_overdue_days": 19}]
    assert c["mandates"] == [] and c["pending_confirms"] == []


def test_unknown_event_is_400(client):
    r = client.post("/api/events", json={"type": "nope", "payload": {}})
    assert r.status_code == 400


def test_invalid_payload_is_422(client):
    r = client.post("/api/events", json={"type": "set_language", "payload": {"lang": "fr-FR"}})
    assert r.status_code == 422
    r = client.post("/api/events", json={"type": "set_language", "payload": {"lang": "hi-IN", "extra": 1}})
    assert r.status_code == 422
    r = client.post("/api/events", json={"type": "udhaar_spoken", "payload": {"store_id": "S1"}})
    assert r.status_code == 422


def test_set_language_persists_without_moving_the_clock(fresh):
    before = fresh.get("/api/snapshot").json()["now"]
    r = fresh.post("/api/events", json={"type": "set_language", "payload": {"lang": "kn-IN"}})
    assert r.status_code == 200 and r.json()["ok"]
    snap = fresh.get("/api/snapshot").json()
    assert snap["lang"] == "kn-IN"
    assert snap["now"] == before
    assert snap["merchant"]["briefing"]["lang"] == "kn-IN" and snap["merchant"]["briefing"]["text"].startswith("ಶುಭೋದಯ")
    with db.session() as s:
        ev = s.get(Event, r.json()["event_id"])
        assert ev.type == "set_language" and ev.payload == {"lang": "kn-IN"}


def test_failed_event_rolls_back(fresh):
    r = fresh.post("/api/events", json={"type": "set_focus_customer", "payload": {"customer_id": "C_NOBODY"}})
    assert r.status_code == 404
    with db.session() as s:
        assert not s.exec(select(Event).where(Event.type == "set_focus_customer")).all()
    assert fresh.get("/api/snapshot").json()["customer"]["id"] == "C_RAMESH"


def test_focus_customer_switches_customer_view(fresh):
    r = fresh.post("/api/events", json={"type": "set_focus_customer", "payload": {"customer_id": "C_VIKRAM"}})
    assert r.status_code == 200
    c = fresh.get("/api/snapshot").json()["customer"]
    assert c["name"] == "Vikram Rao" and c["dues"][0]["oldest_overdue_days"] == 41


def test_customers_list(client):
    rows = client.get("/api/customers?store_id=S1").json()
    assert len(rows) == 60
    ramesh = next(r for r in rows if r["id"] == "C_RAMESH")
    assert ramesh["outstanding"] == 1800 and ramesh["overdue_days"] == 19
