"""Payments, FIFO allocation and the lender split (v2 spec §4.5).

- purpose "sale": the "collect now" part of a purchase. Never allocated to dues.
- purpose "repayment": FIFO over the customer's open entries at the store (oldest first);
  any excess becomes credit balance. If the store has an advance being repaid, 20 % of a UPI
  or auto-pay repayment goes to the lender, capped at what is still owed.
"""
from sqlmodel import Session, select

from app.config import now
from app.core import activity
from app.core.money import inr, round_half_up
from app.errors import EventError
from app.models import Advance, Allocation, Customer, Entry, Payment, StoreCustomer

SPLIT_METHODS = ("upi", "autopay")


def open_entries(s: Session, store_id: str, customer_id: str) -> list[Entry]:
    return list(s.exec(select(Entry).where(Entry.store_id == store_id, Entry.customer_id == customer_id,
                                           Entry.state.in_(("verified", "partly_paid")))
                       .order_by(Entry.created_at, Entry.id)).all())


def record_sale(s: Session, store_id: str, customer_id: str, amount: int, method: str) -> Payment:
    p = Payment(store_id=store_id, customer_id=customer_id, amount=amount, method=method, purpose="sale",
                merchant_share=amount, created_at=now())
    s.add(p)
    s.flush()
    return p


def repay(s: Session, store_id: str, customer_id: str, amount: int, method: str) -> Payment:
    if amount < 1:
        raise EventError("amount must be at least ₹1", 422)
    p = Payment(store_id=store_id, customer_id=customer_id, amount=amount, method=method, purpose="repayment",
                merchant_share=amount, created_at=now())
    s.add(p)
    s.flush()
    left = amount
    for e in open_entries(s, store_id, customer_id):
        if left == 0:
            break
        take = min(left, e.amount - e.paid)
        s.add(Allocation(payment_id=p.id, entry_id=e.id, amount=take))
        e.paid += take
        left -= take
        if e.paid == e.amount:
            e.state, e.settled_at = "settled", now()
        else:
            e.state = "partly_paid"
        s.add(e)
    if left:
        link = s.get(StoreCustomer, (store_id, customer_id))
        link.credit_balance += left
        s.add(link)
    _split(s, p)
    name = s.get(Customer, customer_id).name
    text = f"{inr(amount)} received from {name}"
    if p.lender_share:
        text += f" · {inr(p.merchant_share)} to shop, {inr(p.lender_share)} to Partner NBFC"
    activity.log(s, store_id, "payment", text)
    return p


def _split(s: Session, p: Payment) -> None:
    if p.method not in SPLIT_METHODS:
        return
    a = s.exec(select(Advance).where(Advance.store_id == p.store_id, Advance.state == "repaying")).first()
    if a is None:
        return
    share = min(round_half_up(p.amount * a.split_rate), a.total_due - a.repaid)
    p.lender_share, p.merchant_share = share, p.amount - share
    a.repaid += share
    if a.repaid >= a.total_due:
        a.state = "closed"
        activity.log(s, p.store_id, "advance", "Stock Advance fully repaid")
    s.add_all([p, a])
