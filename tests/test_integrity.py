"""Integrity rules and the fraud-ring beat (spec 7.8, 5.5; M7 acceptance for the backend)."""
from sqlmodel import select

from app import db
from app.core import advance, integrity
from app.models import Entry, RiskAlert, Store


def ev(client, type_, expect=200, **payload):
    r = client.post("/api/events", json={"type": type_, "payload": payload})
    assert r.status_code == expect, r.text
    return r.json()


def test_fraud_ring_contract(fresh):
    with db.session() as s:
        v_before = advance.v_eligible(s, "S2")
    ev(fresh, "inject_fraud_ring", store_id="S2")
    [a] = fresh.get("/api/snapshot").json()["risk_console"]["alerts"]
    assert a["store"] == "Sai Kirana" and a["risk"] == 1.0
    assert a["rules"] == ["R1", "R3", "R4", "R5"]  # R2 does not fire: S2 has a normal baseline
    assert a["summary"] == "possible fake-udhaar ring (shared device, round amounts, instant confirms, money cycle)"
    assert a["advance_blocked"] is True and a["entry_count"] == 4
    with db.session() as s:
        assert s.get(Store, "S2").advance_blocked
        flagged = s.exec(select(Entry).where(Entry.integrity_flag == True)).all()  # noqa: E712
        assert {e.customer_id for e in flagged} == {"C_F01", "C_F02", "C_F03", "C_F04"}
        assert advance.v_eligible(s, "S2") == v_before  # fake receivables never count toward the cap
        assert not s.get(Store, "S1").advance_blocked


def test_fraud_ring_on_demo_day_6(fresh):
    """In the demo the ring lands on Sun 1 Nov, after beat 5; the rule set must not change."""
    ev(fresh, "advance_day", days=6)
    ev(fresh, "inject_fraud_ring", store_id="S2")
    [a] = fresh.get("/api/snapshot").json()["risk_console"]["alerts"]
    assert a["rules"] == ["R1", "R3", "R4", "R5"] and a["risk"] == 1.0


def test_injection_is_once_per_reset(fresh):
    ev(fresh, "inject_fraud_ring", store_id="S2")
    ev(fresh, "inject_fraud_ring", expect=409, store_id="S2")


def test_nightly_rerun_does_not_duplicate_alert(fresh):
    ev(fresh, "inject_fraud_ring", store_id="S2")
    ev(fresh, "advance_day", days=1)
    with db.session() as s:
        assert len(s.exec(select(RiskAlert)).all()) == 1


def test_normal_demo_never_trips_integrity(fresh):
    ev(fresh, "udhaar_spoken", store_id="S1", customer_id="C_RAMESH", amount=340)
    token = fresh.get("/api/snapshot").json()["soundbox"]["front"]["token"]
    ev(fresh, "customer_confirm", token=token, device_id="dev-ramesh")
    ev(fresh, "new_customer", store_id="S1", name="Meera Joshi", mobile="9000011111", amount=300)
    token = fresh.get("/api/snapshot").json()["soundbox"]["front"]["token"]
    ev(fresh, "customer_confirm", token=token, device_id="dev-meera")
    ev(fresh, "advance_day", days=6)
    with db.session() as s:
        assert integrity.evaluate(s, "S1")["risk"] < integrity.THRESHOLD
        assert not s.exec(select(RiskAlert)).all()
        assert not s.get(Store, "S1").advance_blocked


def test_shared_device_alone_is_below_threshold(fresh):
    """Three family members confirming from one phone is R1 only (0.4): noted, not blocked."""
    for i, (name, mobile) in enumerate([("Meera Joshi", "9000011111"), ("Kunal Joshi", "9000011112"),
                                        ("Tara Joshi", "9000011113")]):
        ev(fresh, "new_customer", store_id="S1", name=name, mobile=mobile, amount=150 + 10 * i)
        token = fresh.get("/api/snapshot").json()["soundbox"]["front"]["token"]
        ev(fresh, "customer_confirm", token=token, device_id="dev-family")
    with db.session() as s:
        res = integrity.evaluate(s, "S1")
    assert [r["id"] for r in res["rules"]] == ["R1"] and res["risk"] == 0.4
    assert fresh.get("/api/snapshot").json()["risk_console"]["alerts"] == []
