"""FIFO allocation, credit balance and settlement scoring (spec 7.2, 7.4; M3 acceptance)."""
from datetime import date

import pytest
from sqlmodel import select

from app import clock, db
from app.core import ledger
from app.models import Customer, Entry, Repayment, ScoreEvent, StoreCustomer


def ev(client, type_, **payload):
    r = client.post("/api/events", json={"type": type_, "payload": payload})
    assert r.status_code == 200, r.text
    return r.json()


def snap(client):
    return client.get("/api/snapshot").json()


def entries_of(cid):
    with db.session() as s:
        return s.exec(select(Entry).where(Entry.customer_id == cid).order_by(Entry.created_at)).all()


def score_of(cid):
    with db.session() as s:
        return s.get(Customer, cid).score


def confirm_ramesh_400(client):
    ev(client, "udhaar_spoken", store_id="S1", customer_id="C_RAMESH", amount=500)
    ev(client, "customer_confirm", token=snap(client)["soundbox"]["front"]["token"], device_id="dev-ramesh")


def test_ramesh_pays_500_oldest_first(fresh):
    confirm_ramesh_400(fresh)
    before = snap(fresh)["merchant"]["today_collection"]
    ev(fresh, "upi_payment", store_id="S1", payer_vpa="ramesh.k@ptyes", payer_name="Ramesh Kumar", amount=500)
    old, new = [e for e in entries_of("C_RAMESH") if e.state != "settled"]
    assert (old.amount, old.paid_amount, old.state) == (1_500, 500, "partly_paid")
    assert (new.amount, new.paid_amount, new.state) == (400, 0, "verified")
    s = snap(fresh)
    assert s["customer"]["dues"][0]["amount"] == 1_400
    assert s["merchant"]["today_collection"] == before + 500
    assert s["soundbox"]["last_alert"] == "₹500 received from Ramesh"
    assert score_of("C_RAMESH") == 660  # nothing settled yet


def test_full_payment_settles_both_and_scores(fresh):
    confirm_ramesh_400(fresh)
    ev(fresh, "upi_payment", store_id="S1", payer_vpa="ramesh.k@ptyes", amount=2_000)
    assert all(e.state == "settled" for e in entries_of("C_RAMESH"))
    assert score_of("C_RAMESH") == 660 - 4 + 8  # ₹1,500 20 days late, ₹400 on time
    with db.session() as s:
        assert s.get(StoreCustomer, ("S1", "C_RAMESH")).credit_balance == 100
        rep = s.exec(select(Repayment).where(Repayment.customer_id == "C_RAMESH")
                     .order_by(Repayment.id.desc())).first()
        assert (rep.amount, rep.allocated, rep.matched_by) == (2_000, 1_900, "rule")
    s_ = snap(fresh)
    assert s_["customer"]["dues"] == []
    assert s_["customer"]["credit_balance"] == [{"store": "Lakshmi Stores", "store_id": "S1", "amount": 100}]


def test_verified_before_unverified(fresh):
    """A newer verified entry is paid before an older unverified one."""
    ev(fresh, "udhaar_spoken", store_id="S1", customer_id="C_PRIYA", amount=500)
    clock.tick(600)
    ev(fresh, "udhaar_spoken", store_id="S1", customer_id="C_PRIYA", amount=200)  # first one expires here
    ev(fresh, "customer_confirm", token=snap(fresh)["soundbox"]["front"]["token"], device_id="dev-priya")
    ev(fresh, "upi_payment", store_id="S1", payer_vpa="priya.nair@ptyes", amount=200)
    unverified, verified = [e for e in entries_of("C_PRIYA") if e.created_at.date() == date(2026, 10, 26)]
    assert (unverified.state, unverified.paid_amount) == ("unverified", 0)
    assert verified.state == "settled"
    assert score_of("C_PRIYA") == 788


def test_unverified_settlement_never_scores(fresh):
    ev(fresh, "udhaar_spoken", store_id="S1", customer_id="C_PRIYA", amount=500)
    clock.tick(600)
    ev(fresh, "upi_payment", store_id="S1", payer_vpa="priya.nair@ptyes", amount=500)
    assert [e.state for e in entries_of("C_PRIYA")][-1] == "settled"
    assert score_of("C_PRIYA") == 780


def test_cash_counts_half(fresh):
    ev(fresh, "cash_reported", store_id="S1", customer_id="C_DEEPAK", amount=3_000)
    assert entries_of("C_DEEPAK")[-1].state == "settled"
    assert score_of("C_DEEPAK") == 641  # 10 days late: +2 halved
    with db.session() as s:
        rep = s.exec(select(Repayment).where(Repayment.customer_id == "C_DEEPAK")
                     .order_by(Repayment.id.desc())).first()
        assert (rep.source, rep.matched_by, rep.lender_share) == ("cash", "merchant", 0)
        assert s.exec(select(ScoreEvent).where(ScoreEvent.customer_id == "C_DEEPAK")).one().reason == "settled late (cash)"


def test_defaulted_entry_stays_defaulted_until_paid(fresh):
    with db.session() as s:
        e = s.exec(select(Entry).where(Entry.customer_id == "C_VIKRAM", Entry.state == "verified")).one()
        e.state = "defaulted"
        s.add(e)
        s.commit()
    ev(fresh, "upi_payment", store_id="S1", payer_vpa="vikram.rao@ptyes", amount=600)
    e = [x for x in entries_of("C_VIKRAM") if x.amount == 2_500][0]
    assert (e.state, e.paid_amount) == ("defaulted", 600)
    ev(fresh, "upi_payment", store_id="S1", payer_vpa="vikram.rao@ptyes", amount=1_900)
    e = [x for x in entries_of("C_VIKRAM") if x.amount == 2_500][0]
    assert e.state == "settled"
    assert score_of("C_VIKRAM") == 416


@pytest.mark.parametrize("days_late,source,delta", [
    (-3, "upi", 8), (0, "upi", 8), (1, "upi", 2), (15, "upi", 2), (16, "upi", -4),
    (0, "mandate", 8), (0, "cash", 4), (5, "cash", 1), (20, "cash", -2),
])
def test_settlement_delta(days_late, source, delta):
    from datetime import timedelta
    e = Entry(store_id="S1", customer_id="C", amount=1, state="verified", created_at=clock.DEMO_START,
              due_date=date(2026, 10, 1))
    assert ledger.settlement_delta(e, date(2026, 10, 1) + timedelta(days=days_late), source) == delta
