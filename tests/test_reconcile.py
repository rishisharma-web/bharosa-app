"""Reconciliation rules 0–4 (spec 7.5, flows B1/B2)."""
from sqlmodel import select

from app import db
from app.models import Customer, Entry, PendingMatch, Repayment, Sale


def ev(client, type_, expect=200, **payload):
    r = client.post("/api/events", json={"type": type_, "payload": payload})
    assert r.status_code == expect, r.text
    return r.json()


def snap(client):
    return client.get("/api/snapshot").json()


def ramesh_open():
    with db.session() as s:
        return sorted((e.amount, e.paid_amount, e.state) for e in s.exec(select(Entry).where(
            Entry.customer_id == "C_RAMESH", Entry.state.in_(("verified", "partly_paid", "proposed")))).all())


def repayments(cid):
    with db.session() as s:
        return s.exec(select(Repayment).where(Repayment.customer_id == cid, Repayment.created_at >= "2026-10-26")).all()


def test_rule0_split_payment_is_a_sale_not_a_repayment(fresh):
    """The ₹140 'pay now' from Ramesh's own VPA must not touch his ₹1,800 overdue entry."""
    ev(fresh, "udhaar_spoken", store_id="S1", customer_id="C_RAMESH", amount=340)
    front = snap(fresh)["soundbox"]["front"]
    ev(fresh, "upi_payment", store_id="S1", payer_vpa="ramesh.k@ptyes", payer_name="Ramesh Kumar",
       amount=140, ref=front["sale_ref"])
    assert ramesh_open() == [(200, 0, "proposed"), (1_800, 0, "verified")]
    assert repayments("C_RAMESH") == []
    with db.session() as s:
        sale = s.exec(select(Sale).where(Sale.ref == front["sale_ref"])).one()
        assert (sale.amount, sale.customer_id) == (140, "C_RAMESH")
    after = snap(fresh)["soundbox"]["front"]
    assert after["mode"] == "confirm_qr" and after["pay_paid"] is True and after["pay_qr"] is None
    # once confirmed with the sale already paid, the front screen goes idle
    ev(fresh, "customer_confirm", token=front["token"], device_id="dev-ramesh")
    assert snap(fresh)["soundbox"]["front"] == {"mode": "idle"}
    assert snap(fresh)["customer"]["dues"][0]["amount"] == 2_000


def test_rule1_known_customer_without_dues_is_a_sale(fresh):
    ev(fresh, "upi_payment", store_id="S1", payer_vpa="priya.nair@ptyes", amount=250)
    assert repayments("C_PRIYA") == []
    with db.session() as s:
        assert s.exec(select(Sale).where(Sale.customer_id == "C_PRIYA")).one().amount == 250


def test_rule2_exact_amount_links_vpa(fresh):
    ev(fresh, "upi_payment", store_id="S1", payer_vpa="9845045678@ybl", amount=900)
    [rep] = repayments("C_SURESH")
    assert (rep.matched_by, rep.amount) == ("rule_amount", 900)
    with db.session() as s:
        assert s.get(Customer, "C_SURESH").vpa == "9845045678@ybl"


def test_rule2_needs_exactly_one_match(fresh):
    with db.session() as s:  # make a second no-VPA customer owe exactly ₹900
        v = s.get(Customer, "C_VIKRAM")
        v.vpa = None
        e = s.exec(select(Entry).where(Entry.customer_id == "C_VIKRAM", Entry.state == "verified")).one()
        e.amount = 900
        s.add_all([v, e])
        s.commit()
    ev(fresh, "upi_payment", store_id="S1", payer_vpa="unknown@ybl", amount=900)
    assert repayments("C_SURESH") == [] and repayments("C_VIKRAM") == []


def test_unclear_payer_goes_to_merchant_with_ramesh_first(fresh):
    ev(fresh, "upi_payment", store_id="S1", payer_vpa="9876500000@ptyes", payer_name="Kamala Kumar",
       amount=500, remark="Ramesh ka udhaar")
    [pm] = snap(fresh)["merchant"]["pending_matches"]
    assert pm["candidates"][0]["id"] == "C_RAMESH" and len(pm["candidates"]) <= 5
    assert pm["agent"]["source"] == "template" and pm["agent"]["confidence"] < 0.85
    assert repayments("C_RAMESH") == []
    assert snap(fresh)["soundbox"]["last_alert"] == "₹500 received"

    ev(fresh, "match_resolved", pending_id=pm["pending_id"], customer_id="C_RAMESH")
    [rep] = repayments("C_RAMESH")
    assert (rep.matched_by, rep.payer_vpa, rep.amount) == ("human", "9876500000@ptyes", 500)
    assert ramesh_open() == [(1_800, 500, "partly_paid")]
    with db.session() as s:  # mother's account is not linked to Ramesh
        assert s.get(Customer, "C_RAMESH").vpa == "ramesh.k@ptyes"
    assert snap(fresh)["merchant"]["pending_matches"] == []
    ev(fresh, "match_resolved", expect=409, pending_id=pm["pending_id"], customer_id="C_RAMESH")


def test_merchant_can_mark_unclear_payment_as_sale(fresh):
    ev(fresh, "upi_payment", store_id="S1", payer_vpa="x@ybl", payer_name="Kamala Kumar", amount=500,
       remark="Ramesh ka udhaar")
    pid = snap(fresh)["merchant"]["pending_matches"][0]["pending_id"]
    ev(fresh, "match_resolved", pending_id=pid, customer_id=None)
    with db.session() as s:
        assert s.get(PendingMatch, pid).resolved
        assert s.exec(select(Sale).where(Sale.payer_vpa == "x@ybl")).one().amount == 500


def test_rule4_anonymous_payment_is_a_sale(fresh):
    ev(fresh, "upi_payment", store_id="S1", payer_vpa="walkin@okaxis", amount=75)
    assert snap(fresh)["merchant"]["pending_matches"] == []
    with db.session() as s:
        assert s.exec(select(Sale).where(Sale.payer_vpa == "walkin@okaxis")).one()


def test_customer_of_another_store_paying_here_is_not_allocated(fresh):
    with db.session() as s:
        vpa = s.get(Customer, "C_2001").vpa
    ev(fresh, "upi_payment", store_id="S1", payer_vpa=vpa, amount=300)
    assert repayments("C_2001") == []
