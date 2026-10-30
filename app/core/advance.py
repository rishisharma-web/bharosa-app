"""Supplier Advance and split router (spec 7.7).

    V_eligible = Σ remaining on verified/partly_paid entries at the store
                 from customers with score ≥ 550, not integrity-flagged
    cap        = 0.4 × V_eligible
    amount     = min(gap, cap, bill remaining, 50,000)
    fee        = 1.5 % (half-up)          total_due = amount + fee
    split      = 20 % of every UPI/mandate repayment's *allocated* part until total_due is repaid

Spec decisions made explicit here:
- The split takes 20 % of the part of a repayment that actually paid down udhaar (`allocated`),
  never of an overpayment parked on the customer's credit balance. Cash is never split.
- Backstop = bill due date + 30 days (spec 5.4 and the snapshot example both show 29 Nov for
  the 30 Oct bill), i.e. 30 days from when the store would otherwise have had to pay.
"""
from datetime import timedelta

from sqlmodel import Session, select

from app import clock
from app.adapters.payments import LENDER_NAME, DistributorAdapter, LenderAdapter
from app.core import forecast
from app.core.money import floor_to, inr, round_half_up
from app.errors import EventError
from app.models import Advance, Bill, Customer, Entry, Repayment, Store
from app.realtime.trace import trace

FEE_RATE = 0.015
SPLIT_RATE = 0.20
CAP_SHARE = 0.4
MAX_ADVANCE = 50_000
ELIGIBLE_SCORE = 550
BACKSTOP_DAYS = 30
LIVE_STATES = ("accepted", "disbursed", "repaying", "backstop_due")


def v_eligible(s: Session, store_id: str) -> int:
    rows = s.exec(select(Entry, Customer.score).join(Customer, Customer.id == Entry.customer_id).where(
        Entry.store_id == store_id, Entry.state.in_(("verified", "partly_paid")), Entry.verified_at != None,  # noqa: E711
        Entry.integrity_flag == False, Customer.score >= ELIGIBLE_SCORE)).all()  # noqa: E712
    return sum(e.amount - e.paid_amount for e, _ in rows)


def live_advance(s: Session, store_id: str) -> Advance | None:
    return s.exec(select(Advance).where(Advance.store_id == store_id, Advance.state.in_(LIVE_STATES))).first()


def eligibility(s: Session, store_id: str, bill_id: str) -> dict:
    """What Munim's check_advance_eligibility tool returns, and what offer/accept enforce."""
    store, bill = s.get(Store, store_id), s.get(Bill, bill_id)
    if bill is None or bill.store_id != store_id:
        raise EventError(f"unknown bill {bill_id}", 404)
    fc = forecast.forecast(s, store_id)
    g = forecast.gap_for_bill(fc, bill_id)
    gap = g["gap"] if g else 0
    v = v_eligible(s, store_id)
    cap = floor_to(v * CAP_SHARE, 1)
    bill_left = bill.amount - bill.paid_by_lender - bill.paid_by_store
    amount = max(0, min(gap, cap, bill_left, MAX_ADVANCE))
    reasons = [f"Cash short by {inr(gap)} before {bill.distributor}'s bill" if gap > 0 else "No cash gap before the bill",
               f"Verified udhaar from good customers {inr(v)} → cap {inr(cap)}"]
    eligible = True
    if store.advance_blocked:
        eligible = False
        reasons.append("Blocked by integrity check")
    if live_advance(s, store_id):
        eligible = False
        reasons.append("Another advance is still being repaid")
    if amount <= 0:
        eligible = False
    fee = round_half_up(amount * FEE_RATE)
    return {
        "eligible": eligible, "bill_id": bill_id, "distributor": bill.distributor, "due": bill.due_date.isoformat(),
        "gap": gap, "v_eligible": v, "cap": cap, "amount": amount if eligible else 0,
        "fee": fee if eligible else 0, "total_due": amount + fee if eligible else 0,
        "split_rate": SPLIT_RATE, "lender": LENDER_NAME,
        "backstop": (bill.due_date + timedelta(days=BACKSTOP_DAYS)).isoformat(), "reasons": reasons,
    }


def offer(s: Session, store_id: str, bill_id: str) -> Advance:
    el = eligibility(s, store_id, bill_id)
    if not el["eligible"]:
        raise EventError("Supplier Advance not available: " + "; ".join(el["reasons"]), 409)
    for old in s.exec(select(Advance).where(Advance.store_id == store_id, Advance.state == "offered")).all():
        old.state = "declined"  # a fresh offer replaces any stale one
        s.add(old)
    n = len(s.exec(select(Advance.id)).all()) + 1
    a = Advance(id=f"A{n}", store_id=store_id, bill_id=bill_id, lender=LENDER_NAME, amount=el["amount"],
                fee=el["fee"], total_due=el["total_due"], split_rate=SPLIT_RATE, state="offered",
                created_at=clock.now())
    s.add(a)
    s.flush()
    LenderAdapter.offer(store_id, a.amount)
    trace("advance", f"Offer {inr(a.amount)} + fee {inr(a.fee)} = {inr(a.total_due)}, split 20%",
          {"advance_id": a.id, **{k: el[k] for k in ("gap", "cap", "v_eligible")}})
    return a


def _get(s: Session, advance_id: str) -> Advance:
    a = s.get(Advance, advance_id)
    if a is None:
        raise EventError(f"unknown advance {advance_id}", 404)
    return a


def accept(s: Session, advance_id: str) -> Advance:
    """offered → accepted → disbursed (lender pays the distributor directly) → repaying."""

    a = _get(s, advance_id)
    if a.state != "offered":
        raise EventError(f"advance {a.id} is {a.state}", 409)
    store = s.get(Store, a.store_id)
    if store.advance_blocked or live_advance(s, a.store_id):
        raise EventError("Supplier Advance is no longer available for this store", 409)
    bill = s.get(Bill, a.bill_id)
    a.state, a.accepted_at = "accepted", clock.now()
    a.backstop_date = bill.due_date + timedelta(days=BACKSTOP_DAYS)
    trace("advance", f"{a.id} offered → accepted")
    LenderAdapter.disburse(a, bill.distributor, a.amount)
    a.state = "disbursed"
    bill.paid_by_lender += a.amount
    DistributorAdapter.mark_paid(bill, LENDER_NAME, a.amount)
    a.state = "repaying"
    trace("advance", f"{a.id} disbursed → repaying; store pays the remaining "
                     f"{inr(bill.amount - bill.paid_by_lender)} on {bill.due_date:%d %b}")
    s.add_all([a, bill])
    return a


def decline(s: Session, advance_id: str) -> Advance:
    a = _get(s, advance_id)
    if a.state != "offered":
        raise EventError(f"advance {a.id} is {a.state}", 409)
    a.state = "declined"
    s.add(a)
    return a


def route_split(s: Session, rep: Repayment) -> int:
    """Called on every repayment. Returns the lender share (0 when nothing is routed)."""
    if rep.source not in ("upi", "mandate") or rep.allocated <= 0:
        return 0
    a = s.exec(select(Advance).where(Advance.store_id == rep.store_id, Advance.state == "repaying")).first()
    if a is None:
        return 0

    share = min(round_half_up(rep.allocated * a.split_rate), a.total_due - a.repaid)
    rep.lender_share, rep.merchant_share = share, rep.amount - share
    a.repaid += share
    LenderAdapter.repay(a, share)
    trace("advance", f"Split {inr(rep.allocated)}: {inr(share)} to lender, {inr(rep.amount - share)} to shop "
                     f"({inr(a.repaid)}/{inr(a.total_due)})", {"repayment_id": rep.id, "advance_id": a.id})
    if a.repaid >= a.total_due:
        a.state = "closed"
        trace("advance", f"{a.id} fully repaid → closed")
    s.add_all([rep, a])
    return share


def splits(s: Session, advance_id: str) -> list[dict]:
    """Repayment ledger for the advance detail screen."""
    a = _get(s, advance_id)
    rows = s.exec(select(Repayment).where(Repayment.store_id == a.store_id, Repayment.lender_share > 0,
                                          Repayment.created_at >= a.accepted_at).order_by(Repayment.created_at)).all()
    names = {c.id: c.name for c in s.exec(select(Customer).where(
        Customer.id.in_({r.customer_id for r in rows} or {""}))).all()}
    return [{"repayment_id": r.id, "customer": names.get(r.customer_id), "amount": r.amount, "source": r.source,
             "lender_share": r.lender_share, "merchant_share": r.merchant_share, "ts": clock.iso(r.created_at)}
            for r in rows]
