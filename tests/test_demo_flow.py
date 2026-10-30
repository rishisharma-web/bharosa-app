"""Demo Mode end to end (spec 13): the smoke script's checks, the script listing and the comparison."""
import importlib.util
from pathlib import Path

from sqlmodel import select

from app import db
from app.models import Repayment, Sale
from app.sim import compare

_spec = importlib.util.spec_from_file_location("smoke_demo", Path(__file__).parent.parent / "scripts" / "smoke_demo.py")
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)


def _ok(r):
    assert r.status_code < 400, r.text
    return r.json()


def test_demo_beats_0_to_6(client):
    smoke.check_beats(lambda p: _ok(client.get(p)), lambda p: _ok(client.post(p)), say=lambda *_: None)


def test_presenter_can_do_the_steps_themselves(fresh):
    _ok(fresh.post("/api/demo/next?fast=true"))  # beat 1
    r = _ok(fresh.post("/api/demo/next?fast=true"))  # beat 2: stops at the scan
    assert r["beat"] == 2 and r["awaiting"]
    token = _ok(fresh.get("/api/snapshot"))["customer"]["pending_confirms"][0]["token"]
    _ok(fresh.post("/api/events", json={"type": "customer_confirm",
                                        "payload": {"token": token, "device_id": "dev-ramesh"}}))
    r = _ok(fresh.post("/api/demo/next?fast=true"))  # nothing left in beat 2: goes straight to beat 3
    assert r["beat"] == 3


def test_beat_never_repeats_a_payment_the_presenter_made(fresh):
    """Paying the ₹140 split QR by hand before pressing Next must not send a second ₹140 to old dues."""
    _ok(fresh.post("/api/demo/next?fast=true"))  # beat 1
    front = _ok(fresh.get("/api/snapshot"))["soundbox"]["front"]
    _ok(fresh.post("/api/events", json={"type": "upi_payment", "payload": {
        "store_id": "S1", "payer_vpa": "ramesh.k@ptyes", "amount": 140, "ref": front["sale_ref"]}}))
    _ok(fresh.post("/api/demo/next?fast=true"))  # beat 2
    _ok(fresh.post("/api/demo/next?fast=true"))  # finish beat 2 (the scan)
    with db.session() as s:
        assert len(s.exec(select(Sale).where(Sale.ref == front["sale_ref"])).all()) == 1
        assert not s.exec(select(Repayment).where(Repayment.customer_id == "C_RAMESH",
                                                  Repayment.created_at >= "2026-10-26")).all()
    assert _ok(fresh.get("/api/snapshot"))["customer"]["dues"][0]["amount"] == 2_000


def test_script_listing(client):
    beats = _ok(client.get("/api/demo/script"))
    assert [b["beat"] for b in beats] == list(range(7))
    assert beats[1]["caption"].startswith("Same ₹340, two answers")


def test_compare_is_deterministic_and_labelled(client):
    a = _ok(client.get("/api/overview/compare"))
    assert a["label"] == "Simulation on synthetic data" and len(a["days"]) == 30
    b = compare.simulate()
    assert a["series"] == b["series"] and a["kpis"] == b["kpis"]
    k = a["kpis"]
    assert k["supplier_paid_on_time"] == {"notebook": False, "bharosa": True}
    assert k["bad_udhaar_prevented"] > 0 and k["working_capital_freed"] > 0
    assert all(bh <= nb for nb, bh in zip(a["series"]["bad_udhaar"]["notebook"], a["series"]["bad_udhaar"]["bharosa"]))
