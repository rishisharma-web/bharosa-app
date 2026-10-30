"""Demo Mode end to end (spec 13): step mode, presenter steps, the script listing and the comparison."""
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


def _snap(client):
    return _ok(client.get("/api/snapshot"))


def test_demo_beats_0_to_6(client):
    smoke.check_beats(lambda p: _ok(client.get(p)), lambda p: _ok(client.post(p)), say=lambda *_: None)


def test_presenter_can_do_the_steps_themselves(fresh):
    """Doing a step on screen completes it and shows its explanation; Next never repeats it."""
    _ok(fresh.post("/api/demo/goto/2"))
    _ok(fresh.post("/api/demo/next?fast=true"))  # enter beat 2
    front = _snap(fresh)["soundbox"]["front"]
    _ok(fresh.post("/api/events", json={"type": "upi_payment", "payload": {
        "store_id": "S1", "payer_vpa": "ramesh.k@ptyes", "amount": 100, "ref": front["sale_ref"]}}))
    d = _snap(fresh)["demo"]
    assert (d["beat"], d["step"]) == (2, 1) and d["last"]["label"].startswith("Ramesh pays the ₹100")
    _ok(fresh.post("/api/events", json={"type": "customer_confirm",
                                        "payload": {"token": front["token"], "device_id": "dev-ramesh"}}))
    d = _snap(fresh)["demo"]
    assert d["step"] == d["steps"] and d["last"]["kind"] == "customer"
    assert _ok(fresh.post("/api/demo/next?fast=true"))["beat"] == 3
    with db.session() as s:  # the ₹100 was paid once, as a sale; nothing went to old dues
        assert len(s.exec(select(Sale).where(Sale.ref == front["sale_ref"])).all()) == 1
        assert not s.exec(select(Repayment).where(Repayment.customer_id == "C_RAMESH",
                                                  Repayment.created_at >= "2026-10-26")).all()
    assert _snap(fresh)["customer"]["dues"][0]["amount"] == 1_900


def test_entering_a_beat_runs_nothing(fresh):
    _ok(fresh.post("/api/demo/goto/1"))
    before = _snap(fresh)
    r = _ok(fresh.post("/api/demo/next?fast=true"))
    assert (r["beat"], r["step"], r["last"]) == (1, 0, None)
    assert _snap(fresh)["soundbox"] == before["soundbox"]


def test_run_beat_finishes_the_beat(fresh):
    _ok(fresh.post("/api/demo/goto/1"))
    r = _ok(fresh.post("/api/demo/run_beat?fast=true"))
    assert (r["beat"], r["step"], r["steps"]) == (1, 3, 3)
    assert _snap(fresh)["soundbox"]["top"]["customer_id"] == "C_RAMESH"


def test_script_listing(client):
    beats = _ok(client.get("/api/demo/script"))
    assert [b["beat"] for b in beats] == list(range(7))
    assert beats[1]["caption"].startswith("Same ₹500, three answers")
    assert all(st["what"] and st["who"] and st["why"] for b in beats for st in b["steps"])


def test_compare_is_deterministic_and_labelled(client):
    a = _ok(client.get("/api/overview/compare"))
    assert a["label"] == "Simulation on synthetic data" and len(a["days"]) == 30
    b = compare.simulate()
    assert a["series"] == b["series"] and a["kpis"] == b["kpis"]
    k = a["kpis"]
    assert k["supplier_paid_on_time"] == {"notebook": False, "bharosa": True}
    assert k["bad_udhaar_prevented"] > 0 and k["working_capital_freed"] > 0
    assert all(bh <= nb for nb, bh in zip(a["series"]["bad_udhaar"]["notebook"], a["series"]["bad_udhaar"]["bharosa"]))
