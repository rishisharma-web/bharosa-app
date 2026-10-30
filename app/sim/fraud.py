"""Fraud-ring injector for the integrity beat (spec 5.5).

Story: Sai Kirana invents four "customers", records round ₹2,000 udhaar for each and has
them all confirmed from one phone within seconds. To give the fakes an on-time history
it sends each one ₹500 by P2P, which they "repay" straight back. The inflated verified
receivables would raise the store's Supplier Advance cap — the loan being farmed.

Rows are written with explicit timestamps over the last two hours (this is the simulator
playing the past), then the integrity rules run on the store.
"""
from datetime import timedelta

from sqlmodel import Session

from app import clock
from app.errors import EventError
from app.models import Allocation, Consent, Customer, Entry, P2PTransfer, Repayment, Store, StoreCustomer
from app.realtime.trace import trace

RING = [("C_F01", "Manoj Kale"), ("C_F02", "Sunil Patra"), ("C_F03", "Deepak Rane"), ("C_F04", "Vijay Ghosh")]
SHARED_DEVICE = "dev-7f3a91"
FAKE_AMOUNT = 2_000
CYCLE_AMOUNT = 500


def inject(s: Session, store_id: str) -> list[str]:
    store = s.get(Store, store_id)
    if store is None:
        raise EventError(f"unknown store {store_id}", 404)
    if s.get(Customer, RING[0][0]) is not None:
        raise EventError("the fraud ring was already injected; reset the demo to run it again", 409)
    now = clock.now()
    t0 = now - timedelta(minutes=100)
    for i, (cid, name) in enumerate(RING):
        s.add(Customer(id=cid, name=name, aliases=[name.split()[0]], mobile=f"70000000{i + 1:02d}",
                       vpa=f"{name.split()[0].lower()}{i + 1}@ptyes", device_id=SHARED_DEVICE, persona=None,
                       score=600, is_new=False, lang=store.lang, created_at=t0 - timedelta(minutes=30)))
    s.flush()
    for i, (cid, _) in enumerate(RING):
        created = t0 + timedelta(seconds=25 * i)
        verified = created + timedelta(seconds=6 + i)
        s.add(StoreCustomer(store_id=store_id, customer_id=cid))
        e = Entry(store_id=store_id, customer_id=cid, amount=FAKE_AMOUNT, requested_amount=FAKE_AMOUNT,
                  paid_amount=CYCLE_AMOUNT, state="partly_paid", created_at=created,
                  due_date=created.date() + timedelta(days=store.due_days), verified_at=verified,
                  confirm_device_id=SHARED_DEVICE)
        s.add(e)
        s.add(Consent(customer_id=cid, type="data_share", granted_at=verified))
        s.flush()
        s.add(P2PTransfer(store_id=store_id, from_id=store_id, to_id=cid, amount=CYCLE_AMOUNT,
                          created_at=t0 + timedelta(minutes=40, seconds=60 * i)))
        r = Repayment(store_id=store_id, customer_id=cid, amount=CYCLE_AMOUNT, source="upi",
                      payer_vpa=f"{RING[i][1].split()[0].lower()}{i + 1}@ptyes", matched_by="rule",
                      match_confidence=1.0, allocated=CYCLE_AMOUNT, merchant_share=CYCLE_AMOUNT,
                      created_at=t0 + timedelta(minutes=70, seconds=60 * i))
        s.add(r)
        s.flush()
        s.add(Allocation(repayment_id=r.id, entry_id=e.id, amount=CYCLE_AMOUNT))
    trace("upi", f"{store.name}: {len(RING)} new customers, ₹{FAKE_AMOUNT:,} each, P2P out and back",
          {"customers": [c for c, _ in RING]})
    return [c for c, _ in RING]
