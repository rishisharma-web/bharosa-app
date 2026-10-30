"""Flow A end to end through the event API (spec 5.1, M2 acceptance)."""
from sqlmodel import select

from app import clock, db
from app.models import Consent, Customer, Entry, ScoreEvent


def ev(client, type_, **payload):
    return client.post("/api/events", json={"type": type_, "payload": payload})


def udhaar(client, cid, amount=340):
    r = ev(client, "udhaar_spoken", store_id="S1", customer_id=cid, amount=amount)
    assert r.status_code == 200, r.text
    return client.get("/api/snapshot").json()


def test_ramesh_amber_split(fresh):
    snap = udhaar(fresh, "C_RAMESH")
    top, front = snap["soundbox"]["top"], snap["soundbox"]["front"]
    assert (top["band"], top["safe_limit"], top["credit_now"], top["collect_now"]) == ("amber", 200, 200, 140)
    assert top["text"] == ("Caution: ₹1,800 overdue for 19 days. Safe limit today ₹200. "
                           "Give ₹200 on credit, collect ₹140 now (UPI or cash).")
    assert front["mode"] == "confirm_qr" and front["amount"] == 200
    assert front["qr_payload"] == f"bharosa://confirm/{front['token']}"
    assert front["pay_qr"] == f"upi://pay?pa=lakshmistores@ptyes&pn=Lakshmi%20Stores&am=140&cu=INR&tr=SALE-{front['entry_id']}"
    assert snap["merchant"]["udhaar"]["pending_confirm"] == 1
    assert snap["customer"]["pending_confirms"][0]["amount"] == 200
    # proposed entries are not yet part of the books
    assert snap["merchant"]["udhaar"]["outstanding"] == 45_000


def test_priya_green_vikram_red(fresh):
    top = udhaar(fresh, "C_PRIYA")["soundbox"]["top"]
    assert top["band"] == "green" and top["text"] == "Safe. Priya can take ₹340 on credit."
    snap = udhaar(fresh, "C_VIKRAM")
    top, front = snap["soundbox"]["top"], snap["soundbox"]["front"]
    assert top["band"] == "red" and top["entry_id"] is None
    assert top["text"] == "High risk: ₹2,600 overdue for 41 days. Suggest collecting full payment."
    assert front["mode"] == "pay_qr" and front["pay_amount"] == 340
    with db.session() as s:  # no ₹0 entry
        assert not s.exec(select(Entry).where(Entry.customer_id == "C_VIKRAM", Entry.state == "proposed")).all()


def test_confirm_makes_verified_receivable(fresh):
    front = udhaar(fresh, "C_RAMESH")["soundbox"]["front"]
    sheet = fresh.get(f"/api/confirm/{front['token']}").json()
    assert (sheet["amount"], sheet["store"], sheet["first_time"]) == (200, "Lakshmi Stores", False)
    r = ev(fresh, "customer_confirm", token=front["token"], device_id="dev-ramesh")
    assert r.status_code == 200
    snap = fresh.get("/api/snapshot").json()
    assert snap["customer"]["dues"][0]["amount"] == 2_000 and snap["customer"]["dues"][0]["verified"] == 2_000
    assert snap["merchant"]["udhaar"]["verified"] == 38_200
    assert snap["merchant"]["udhaar"]["pending_confirm"] == 0
    # the ₹140 is still to be collected, so the front screen keeps the pay QR
    assert snap["soundbox"]["front"]["mode"] == "pay_qr" and snap["soundbox"]["front"]["pay_amount"] == 140
    assert snap["soundbox"]["last_alert"] == "Ramesh confirmed ₹200 udhaar ✓"
    # a second scan of the same QR is rejected
    assert ev(fresh, "customer_confirm", token=front["token"], device_id="dev-ramesh").status_code == 409


def test_first_time_consent(fresh):
    front = udhaar(fresh, "C_ANITA", 300)["soundbox"]["front"]
    assert fresh.get(f"/api/confirm/{front['token']}").json()["first_time"] is True
    ev(fresh, "customer_confirm", token=front["token"], device_id="dev-anita", consents={"data_share": True})
    with db.session() as s:
        assert s.exec(select(Consent).where(Consent.customer_id == "C_ANITA", Consent.type == "data_share")).first()


def test_dispute_correct_confirm_original_costs_15(fresh):
    front = udhaar(fresh, "C_RAMESH")["soundbox"]["front"]
    entry_id = front["entry_id"]
    assert ev(fresh, "customer_dispute", token=front["token"], reason="Only took ₹140 of goods",
              claimed_amount=140).status_code == 200
    snap = fresh.get("/api/snapshot").json()
    assert snap["merchant"]["disputes"][0]["claimed_amount"] == 140
    assert snap["soundbox"]["last_alert"] == "Ramesh disputes: says ₹140"
    assert ev(fresh, "entry_corrected", entry_id=entry_id, amount=200).status_code == 200  # shop stands firm
    new_token = fresh.get("/api/snapshot").json()["soundbox"]["front"]["token"]
    assert new_token != front["token"]
    assert ev(fresh, "customer_confirm", token=new_token, device_id="dev-ramesh").status_code == 200
    with db.session() as s:
        assert s.get(Customer, "C_RAMESH").score == 665
        assert s.exec(select(ScoreEvent).where(ScoreEvent.customer_id == "C_RAMESH")).one().delta == -15


def test_dispute_corrected_down_has_no_penalty(fresh):
    front = udhaar(fresh, "C_RAMESH")["soundbox"]["front"]
    ev(fresh, "customer_dispute", token=front["token"], reason="wrong", claimed_amount=150)
    ev(fresh, "entry_corrected", entry_id=front["entry_id"], amount=150)
    token = fresh.get("/api/snapshot").json()["soundbox"]["front"]["token"]
    ev(fresh, "customer_confirm", token=token, device_id="dev-ramesh")
    with db.session() as s:
        assert s.get(Customer, "C_RAMESH").score == 680


def test_override_amber_and_red(fresh):
    entry_id = udhaar(fresh, "C_RAMESH")["soundbox"]["front"]["entry_id"]
    assert ev(fresh, "guardrail_override", entry_id=entry_id).status_code == 200
    snap = fresh.get("/api/snapshot").json()
    assert snap["soundbox"]["front"]["amount"] == 340 and snap["soundbox"]["front"]["pay_qr"] is None
    assert snap["soundbox"]["top"]["override"] is True
    udhaar(fresh, "C_VIKRAM")
    assert ev(fresh, "guardrail_override", store_id="S1", customer_id="C_VIKRAM", amount=340).status_code == 200
    with db.session() as s:
        e = s.exec(select(Entry).where(Entry.customer_id == "C_VIKRAM", Entry.state == "proposed")).one()
        assert (e.amount, e.override) == (340, True)


def test_unscanned_entry_expires_after_10_sim_minutes(fresh):
    front = udhaar(fresh, "C_PRIYA")["soundbox"]["front"]
    clock.tick(600)  # the next event's own +30 s tick takes it past the window
    udhaar(fresh, "C_RAMESH")
    with db.session() as s:
        assert s.get(Entry, front["entry_id"]).state == "unverified"
    snap = fresh.get("/api/snapshot").json()
    assert snap["merchant"]["udhaar"]["unverified"] == 7_340  # collectable, but never lendable
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
    assert ev(fresh, "udhaar_spoken", store_id="S1", customer_id="C_2001", amount=100).status_code == 404
    assert ev(fresh, "udhaar_spoken", store_id="S1", text="Ramesh 340 udhaar").status_code == 200  # Counter Agent


def test_customer_detail_privacy_and_reasons(fresh):
    d = fresh.get("/api/customers/C_RAMESH?store_id=S1").json()
    assert d["risk"]["safe_limit"] == 200 and len(d["risk"]["reasons"]) == 3
    assert all(e["state"] in ("settled", "verified") for e in d["entries"])
    assert fresh.get("/api/customers/C_2001?store_id=S1").status_code == 404
