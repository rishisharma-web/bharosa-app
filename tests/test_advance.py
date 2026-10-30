"""Supplier Advance, split router, mandates and daily jobs (spec 7.7, 5.2 B4, 7.14; M5 acceptance)."""
from sqlmodel import select

from app import db
from app.models import Advance, Bill, Customer, Entry, Mandate, Repayment, ScoreEvent, Store


def ev(client, type_, expect=200, **payload):
    r = client.post("/api/events", json={"type": type_, "payload": payload})
    assert r.status_code == expect, r.text
    return r.json()


def snap(client):
    return client.get("/api/snapshot").json()


def beats_1_to_3(client):
    ev(client, "udhaar_spoken", store_id="S1", customer_id="C_PRIYA", amount=340)
    ev(client, "udhaar_spoken", store_id="S1", customer_id="C_RAMESH", amount=340)
    front = snap(client)["soundbox"]["front"]
    ev(client, "upi_payment", store_id="S1", payer_vpa="ramesh.k@ptyes", amount=140, ref=front["sale_ref"])
    ev(client, "customer_confirm", token=front["token"], device_id="dev-ramesh")
    ev(client, "mandate_created", customer_id="C_RAMESH", store_id="S1", cap=3_000, window_start_day=1,
       window_end_day=5)


def offer_and_accept(client):
    ev(client, "offer_advance", store_id="S1", bill_id="B1")
    adv = snap(client)["merchant"]["advance"]
    ev(client, "advance_accept", advance_id=adv["id"])
    return adv["id"]


def test_demo_beats_0_to_5_contract_numbers(fresh):
    beats_1_to_3(fresh)
    s = snap(fresh)
    assert s["customer"]["score"] == 685  # +5 auto-pay set up
    assert s["customer"]["mandates"][0]["window"] == "1st–5th"
    assert s["merchant"]["due_soon"][0]["gap"] == 9_200  # beats 1–3 did not move the gap

    # beat 4: offer + accept
    el = fresh.get("/api/advances/eligibility?store_id=S1&bill_id=B1").json()
    assert (el["eligible"], el["amount"], el["fee"], el["total_due"], el["cap"]) == (True, 9_200, 138, 9_338, 10_240)
    aid = offer_and_accept(fresh)
    adv = snap(fresh)["merchant"]["advance"]
    assert {k: adv[k] for k in ("state", "amount", "fee", "total_due", "repaid", "split_rate", "backstop", "paid_to")} == {
        "state": "repaying", "amount": 9_200, "fee": 138, "total_due": 9_338, "repaid": 0, "split_rate": 0.2,
        "backstop": "2026-11-29", "paid_to": "Sharma Traders"}
    assert snap(fresh)["merchant"]["due_soon"][0]["gap"] == 0  # store's own ₹8,800 is covered

    # beat 5: six days to Sun 1 Nov
    ev(fresh, "advance_day", days=6)
    s = snap(fresh)
    assert s["now"].startswith("2026-11-01T09:0")  # each of the 9 sweeps ticks the clock 30 s
    assert s["customer"]["dues"] == [] and s["customer"]["score"] == 692  # 685 + 3 + 8 − 4
    assert s["merchant"]["advance"]["repaid"] == 2_200  # 20% of ₹2,000 + ₹9,000
    with db.session() as db_s:
        sweeps = db_s.exec(select(Repayment).where(Repayment.source == "mandate",
                                                   Repayment.created_at >= "2026-11-01")).all()
        assert len(sweeps) == 9
        for r in sweeps:
            assert r.lender_share == (r.allocated * 2 + 5) // 10 and r.merchant_share == r.amount - r.lender_share
        assert db_s.get(Bill, "B1").status == "paid" and db_s.get(Bill, "B1").paid_by_store == 8_800
        priya_new = db_s.exec(select(Entry).where(Entry.customer_id == "C_PRIYA", Entry.amount == 340)).one()
        assert priya_new.state == "unverified"
    splits = fresh.get(f"/api/advances/{aid}").json()["splits"]
    assert sum(x["lender_share"] for x in splits) == 2_200 and len(splits) == 9


def test_ramesh_score_history(fresh):
    beats_1_to_3(fresh)
    ev(fresh, "advance_day", days=6)
    with db.session() as s:
        deltas = [(e.delta, e.reason) for e in s.exec(select(ScoreEvent).where(
            ScoreEvent.customer_id == "C_RAMESH").order_by(ScoreEvent.id)).all()]
    assert deltas == [(5, "auto-pay set up"), (-4, "settled late (mandate)"), (8, "settled on time (mandate)"),
                      (3, "auto-pay executed")]


def test_cash_is_never_split_and_overpayment_is_not_split(fresh):
    offer_and_accept(fresh)
    ev(fresh, "cash_reported", store_id="S1", customer_id="C_SURESH", amount=900)
    ev(fresh, "upi_payment", store_id="S1", payer_vpa="vikram.rao@ptyes", amount=3_000)  # owes 2,600
    with db.session() as s:
        cash = s.exec(select(Repayment).where(Repayment.customer_id == "C_SURESH").order_by(Repayment.id.desc())).first()
        assert cash.lender_share == 0
        upi = s.exec(select(Repayment).where(Repayment.customer_id == "C_VIKRAM").order_by(Repayment.id.desc())).first()
        assert (upi.allocated, upi.lender_share, upi.merchant_share) == (2_600, 520, 2_480)


def test_split_stops_at_total_due_and_closes(fresh):
    offer_and_accept(fresh)
    with db.session() as s:
        a = s.exec(select(Advance)).one()
        a.repaid = 9_300
        s.add(a)
        s.commit()
    ev(fresh, "upi_payment", store_id="S1", payer_vpa="ramesh.k@ptyes", amount=1_000)
    with db.session() as s:
        a = s.exec(select(Advance)).one()
        assert (a.repaid, a.state) == (9_338, "closed")
        r = s.exec(select(Repayment).where(Repayment.customer_id == "C_RAMESH").order_by(Repayment.id.desc())).first()
        assert r.lender_share == 38


def test_only_one_live_advance_and_blocked_store(fresh):
    offer_and_accept(fresh)
    ev(fresh, "bill_added", store_id="S1", distributor="Gupta Agencies", amount=30_000, due_date="2026-10-28")
    ev(fresh, "offer_advance", expect=409, store_id="S1", bill_id="B2")
    with db.session() as s:
        st = s.get(Store, "S1")
        st.advance_blocked = True
        s.add(st)
        s.commit()
    el = fresh.get("/api/advances/eligibility?store_id=S1&bill_id=B2").json()
    assert el["eligible"] is False and "Blocked by integrity check" in el["reasons"]


def test_decline(fresh):
    ev(fresh, "offer_advance", store_id="S1", bill_id="B1")
    aid = snap(fresh)["merchant"]["advance"]["id"]
    ev(fresh, "advance_decline", advance_id=aid)
    assert snap(fresh)["merchant"]["advance"] is None
    ev(fresh, "advance_accept", expect=409, advance_id=aid)


def test_mandate_sweeps_only_verified_dues_and_once_per_store_bonus(fresh):
    ev(fresh, "mandate_created", customer_id="C_RAMESH", store_id="S1", cap=1_000, window_start_day=1, window_end_day=5)
    ev(fresh, "mandate_created", expect=409, customer_id="C_RAMESH", store_id="S1", cap=1_000,
       window_start_day=1, window_end_day=5)
    ev(fresh, "salary_credited", customer_id="C_RAMESH")  # 26 Oct: outside the window, nothing happens
    with db.session() as s:
        assert not s.exec(select(Repayment).where(Repayment.source == "mandate",
                                                  Repayment.customer_id == "C_RAMESH")).all()
    ev(fresh, "advance_day", days=6)
    with db.session() as s:
        [r] = s.exec(select(Repayment).where(Repayment.source == "mandate", Repayment.customer_id == "C_RAMESH")).all()
        assert r.amount == 1_000  # capped
        assert s.get(Customer, "C_RAMESH").score == 680 + 5 + 3
        assert s.exec(select(Mandate).where(Mandate.customer_id == "C_RAMESH")).one().status == "active"


def test_default_after_60_days_once(fresh):
    ev(fresh, "advance_day", days=20)  # Vikram: 41 → 61 days overdue
    with db.session() as s:
        e = s.exec(select(Entry).where(Entry.customer_id == "C_VIKRAM", Entry.amount == 2_600)).one()
        assert e.state == "defaulted"
        assert s.get(Customer, "C_VIKRAM").score == 380
    ev(fresh, "advance_day", days=1)
    with db.session() as s:
        assert s.get(Customer, "C_VIKRAM").score == 380
