"""Flow A end to end through the event API (spec 5.1, M2 acceptance), simplified world."""
from sqlmodel import select

from app import clock, db
from app.models import Consent, Customer, Entry, ScoreEvent


def ev(client, type_, **payload):
    return client.post("/api/events", json={"type": type_, "payload": payload})


def udhaar(client, cid, amount=500):
    r = ev(client, "udhaar_spoken", store_id="S1", customer_id=cid, amount=amount)
    assert r.status_code == 200, r.text
    return r, client.get("/api/snapshot").json()


def test_ramesh_amber_split(fresh):
    r, snap = udhaar(fresh, "C_RAMESH")
    top, front = snap["soundbox"]["top"], snap["soundbox"]["front"]
    assert (top["band"], top["safe_limit"], top["credit_now"], top["collect_now"]) == ("amber", 400, 400, 100)
    assert top["text"] == ("Caution: ₹1,500 overdue for 20 days. Safe limit today ₹400. "
                           "Give ₹400 on credit, collect ₹100 now (UPI or cash).")
    assert front["mode"] == "confirm_qr" and front["amount"] == 400
    assert front["qr_payload"] == f"bharosa://confirm/{front['token']}"
    assert front["pay_qr"] == f"upi://pay?pa=lakshmistores@ptyes&pn=Lakshmi%20Stores&am=100&cu=INR&tr=SALE-{front['entry_id']}"
    assert snap["merchant"]["udhaar"]["pending_confirm"] == 1
    assert snap["merchant"]["udhaar"]["outstanding"] == 18_000  # not in the books until confirmed
    # Nothing is pushed to the customer: the entry reaches their phone only when they scan the QR.
    assert "notify" not in r.json()["effects_summary"]


def test_priya_green_vikram_red(fresh):
    _, snap = udhaar(fresh, "C_PRIYA")
    assert snap["soundbox"]["top"]["band"] == "green"
    assert snap["soundbox"]["top"]["text"] == "Safe. Priya can take ₹500 on credit."
    _, snap = udhaar(fresh, "C_VIKRAM")
    top, front = snap["soundbox"]["top"], snap["soundbox"]["front"]
    assert top["band"] == "red" and top["entry_id"] is None
    assert top["text"] == "High risk: ₹2,500 overdue for 45 days. Suggest collecting full payment."
    assert front["mode"] == "pay_qr" and front["pay_amount"] == 500
    with db.session() as s:  # no ₹0 entry
        assert not s.exec(select(Entry).where(Entry.customer_id == "C_VIKRAM", Entry.state == "proposed")).all()


def test_confirm_makes_verified_receivable(fresh):
    _, snap = udhaar(fresh, "C_RAMESH")
    front = snap["soundbox"]["front"]
    sheet = fresh.get(f"/api/confirm/{front['token']}").json()
    assert (sheet["amount"], sheet["store"], sheet["first_time"]) == (400, "Lakshmi Stores", False)
    assert ev(fresh, "customer_confirm", token=front["token"], device_id="dev-ramesh").status_code == 200
    snap = fresh.get("/api/snapshot").json()
    assert snap["customer"]["dues"][0]["amount"] == 1_900 and snap["customer"]["dues"][0]["verified"] == 1_900
    assert snap["merchant"]["udhaar"]["verified"] == 17_400
    assert snap["merchant"]["udhaar"]["pending_confirm"] == 0
    # the ₹100 is still to be collected, so the front screen keeps the pay QR
    assert snap["soundbox"]["front"]["mode"] == "pay_qr" and snap["soundbox"]["front"]["pay_amount"] == 100
    assert snap["soundbox"]["last_alert"] == "Ramesh confirmed ₹400 udhaar ✓"
    assert ev(fresh, "customer_confirm", token=front["token"], device_id="dev-ramesh").status_code == 409


def test_first_time_consent(fresh):
    ev(fresh, "new_customer", store_id="S1", name="Meera Joshi", mobile="9000011111", amount=300)
    front = fresh.get("/api/snapshot").json()["soundbox"]["front"]
    assert fresh.get(f"/api/confirm/{front['token']}").json()["first_time"] is True
    ev(fresh, "customer_confirm", token=front["token"], device_id="dev-meera", consents={"data_share": True})
    with db.session() as s:
        assert s.exec(select(Consent).where(Consent.customer_id == "C_N001", Consent.type == "data_share")).first()


def test_dispute_correct_confirm_original_costs_15(fresh):
    _, snap = udhaar(fresh, "C_RAMESH")
    front = snap["soundbox"]["front"]
    assert ev(fresh, "customer_dispute", token=front["token"], reason="Only took ₹300 of goods",
              claimed_amount=300).status_code == 200
    snap = fresh.get("/api/snapshot").json()
    assert snap["merchant"]["disputes"][0]["claimed_amount"] == 300
    assert snap["soundbox"]["last_alert"] == "Ramesh disputes: says ₹300"
    assert ev(fresh, "entry_corrected", entry_id=front["entry_id"], amount=400).status_code == 200  # shop stands firm
    new_token = fresh.get("/api/snapshot").json()["soundbox"]["front"]["token"]
    assert new_token != front["token"]
    assert ev(fresh, "customer_confirm", token=new_token, device_id="dev-ramesh").status_code == 200
    with db.session() as s:
        assert s.get(Customer, "C_RAMESH").score == 645
        assert s.exec(select(ScoreEvent).where(ScoreEvent.customer_id == "C_RAMESH")).one().delta == -15


def test_dispute_corrected_down_has_no_penalty(fresh):
    _, snap = udhaar(fresh, "C_RAMESH")
    front = snap["soundbox"]["front"]
    ev(fresh, "customer_dispute", token=front["token"], reason="wrong", claimed_amount=300)
    ev(fresh, "entry_corrected", entry_id=front["entry_id"], amount=300)
    token = fresh.get("/api/snapshot").json()["soundbox"]["front"]["token"]
    ev(fresh, "customer_confirm", token=token, device_id="dev-ramesh")
    with db.session() as s:
        assert s.get(Customer, "C_RAMESH").score == 660


def test_override_amber_and_red(fresh):
    _, snap = udhaar(fresh, "C_RAMESH")
    assert ev(fresh, "guardrail_override", entry_id=snap["soundbox"]["front"]["entry_id"]).status_code == 200
    snap = fresh.get("/api/snapshot").json()
    assert snap["soundbox"]["front"]["amount"] == 500 and snap["soundbox"]["front"]["pay_qr"] is None
    assert snap["soundbox"]["top"]["override"] is True
    udhaar(fresh, "C_VIKRAM")
    assert ev(fresh, "guardrail_override", store_id="S1", customer_id="C_VIKRAM", amount=500).status_code == 200
    with db.session() as s:
        e = s.exec(select(Entry).where(Entry.customer_id == "C_VIKRAM", Entry.state == "proposed")).one()
        assert (e.amount, e.override) == (500, True)


def test_unscanned_entry_expires_after_10_sim_minutes(fresh):
    _, snap = udhaar(fresh, "C_PRIYA")
    front = snap["soundbox"]["front"]
    clock.tick(600)  # the next event's own +30 s tick takes it past the window
    udhaar(fresh, "C_RAMESH")
    with db.session() as s:
        assert s.get(Entry, front["entry_id"]).state == "unverified"
    snap = fresh.get("/api/snapshot").json()
    assert snap["merchant"]["udhaar"]["unverified"] == 1_500  # Imran's ₹1,000 + Priya's ₹500: collectable, never lendable
    assert ev(fresh, "customer_confirm", token=front["token"], device_id="dev-priya").status_code == 410


def test_new_customer_gets_starter_limit(fresh):
    r = ev(fresh, "new_customer", store_id="S1", name="Meera Joshi", mobile="9000011111", amount=600)
    assert r.status_code == 200 and len(r.json()["child_event_ids"]) == 1
    top = fresh.get("/api/snapshot").json()["soundbox"]["top"]
    assert (top["customer"], top["safe_limit"], top["credit_now"], top["collect_now"]) == ("Meera Joshi", 500, 500, 100)
    # the same mobile at another store links the same identity instead of duplicating it
    ev(fresh, "new_customer", store_id="S2", name="Meera J", mobile="9000011111")
    with db.session() as s:
        assert len(s.exec(select(Customer).where(Customer.mobile == "9000011111")).all()) == 1


def test_unknown_or_foreign_customer_rejected(fresh):
    assert ev(fresh, "udhaar_spoken", store_id="S1", customer_id="C_S2_1", amount=100).status_code == 404
    assert ev(fresh, "udhaar_spoken", store_id="S1", text="Ramesh 500 udhaar").status_code == 200  # Counter Agent


def test_customer_detail_privacy_and_reasons(fresh):
    d = fresh.get("/api/customers/C_RAMESH?store_id=S1").json()
    assert d["risk"]["safe_limit"] == 400 and len(d["risk"]["reasons"]) == 3
    assert all(e["state"] in ("settled", "verified") for e in d["entries"])
    assert fresh.get("/api/customers/C_S2_1?store_id=S1").status_code == 404
