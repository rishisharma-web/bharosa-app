"""Stock Advance (v2 spec §4.6): a partner lender pays the distributor directly; repaid from
20 % of incoming UPI / auto-pay repayments (the split lives in payments.py).

    V_eligible = verified open receivables at the store from customers scoring ≥ 550, not flagged
    amount     = min(gap, 40 % of V_eligible, bill)       fee 1.5 %      backstop accept + 30 days
"""
from datetime import timedelta
from fractions import Fraction

from sqlmodel import Session, select

from app.config import now, today
from app.core import activity, festive, score as score_mod
from app.core.money import floor_to, inr, round_half_up
from app.errors import EventError
from app.models import Advance, Bill, Entry, Store

LENDER = "Partner NBFC"
FEE_RATE = Fraction(15, 1000)
SPLIT_RATE = 0.20
CAP_SHARE = Fraction(2, 5)
ELIGIBLE_SCORE = 550
BACKSTOP_DAYS = 30


def v_eligible(s: Session, store_id: str) -> int:
    rows = s.exec(select(Entry).where(Entry.store_id == store_id, Entry.state.in_(("verified", "partly_paid")),
                                      Entry.integrity_flag == False)).all()  # noqa: E712
    scores: dict[str, int] = {}
    total = 0
    for e in rows:
        if e.customer_id not in scores:
            scores[e.customer_id] = score_mod.for_customer(s, e.customer_id).value
        if scores[e.customer_id] >= ELIGIBLE_SCORE:
            total += e.amount - e.paid
    return total


def sizing(s: Session, store_id: str, bill: Bill) -> dict:
    store = s.get(Store, store_id)
    gap = max(0, bill.amount - store.cash_available_by_bill_due)
    v = v_eligible(s, store_id)
    cap = floor_to(v * CAP_SHARE, 1)
    amount = max(0, min(gap, cap, bill.amount))
    fee = round_half_up(amount * FEE_RATE)
    return {"gap": gap, "v_eligible": v, "cap": cap, "amount": amount, "fee": fee, "total_due": amount + fee}


def create_bill_and_offer(s: Session, store_id: str) -> Advance | None:
    """Approving the Diwali action places the order (bill B1) and, if there's a gap, offers an advance."""
    p = festive.for_store(s, store_id)
    bill = s.get(Bill, "B1")
    if bill is None:
        bill = Bill(id="B1", store_id=store_id, distributor=p["supplier"], amount=p["order_total"],
                    due_date=festive.bill_due(p))
        s.add(bill)
        s.flush()
        activity.log(s, store_id, "growth", f"Order placed with {bill.distributor}: {inr(bill.amount)}, "
                                            f"due {bill.due_date:%a %d %b}")
    z = sizing(s, store_id, bill)
    if z["amount"] <= 0:
        return None
    a = Advance(id="A1", store_id=store_id, bill_id=bill.id, lender=LENDER, amount=z["amount"], fee=z["fee"],
                total_due=z["total_due"], split_rate=SPLIT_RATE, state="offered", created_at=now())
    s.merge(a)
    activity.log(s, store_id, "advance", f"Stock Advance offered: {inr(a.amount)} (fee {inr(a.fee)}), "
                                         f"cash short by {inr(z['gap'])}")
    return a


def accept(s: Session, store_id: str, advance_id: str) -> Advance:
    a = _get(s, store_id, advance_id)
    if a.state != "offered":
        raise EventError(f"This advance is already {a.state}", 409)
    bill = s.get(Bill, a.bill_id)
    a.state, a.backstop_date = "repaying", today() + timedelta(days=BACKSTOP_DAYS)
    bill.paid_by_lender, bill.paid_by_store, bill.status = a.amount, bill.amount - a.amount, "paid"
    s.add_all([a, bill])
    activity.log(s, store_id, "advance", f"{a.lender} paid {bill.distributor} {inr(a.amount)} ✓")
    return a


def decline(s: Session, store_id: str, advance_id: str) -> Advance:
    a = _get(s, store_id, advance_id)
    if a.state != "offered":
        raise EventError(f"This advance is already {a.state}", 409)
    a.state = "declined"
    s.add(a)
    activity.log(s, store_id, "advance", "Stock Advance declined")
    return a


def _get(s: Session, store_id: str, advance_id: str) -> Advance:
    a = s.get(Advance, advance_id)
    if a is None or a.store_id != store_id:
        raise EventError("advance not found", 404)
    return a
