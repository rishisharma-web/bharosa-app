"""The fixed demo world (v2 spec §3). Every row is written here; reset rebuilds it in well under 3 s.

Lakshmi Stores (S1), Sat 31 Oct 2026:
    Priya   12 on time                                  → score 780, nothing owed
    Ramesh  8 on time, 2 late, ₹1,700 open (19 days)    → score 662
    Vikram  2 on time, 5 late, 1 written off, ₹2,600 open (41 days) → score 438
    Anita   (Other Paytm shops) 12 on time, 1 late, ₹600 open (not due) → score 770, new to S1
    6 regulars, 6 on time each + one open verified entry → ₹21,500
    Outstanding ₹25,800 · overdue ₹4,300
"""
import time as _time
from datetime import date, datetime, time, timedelta

from app import db
from app.config import get_settings
from app.models import (
    Allocation, CatalogueItem, Customer, Entry, FestiveProfile, Payment, SoundboxState, Store, StoreCustomer, User,
)

DUE_DAYS = 30

STORES = [
    Store(id="S1", name="Lakshmi Stores", area="Jayanagar, Bengaluru", voice_lang="kn-IN", starter_limit=500,
          due_days=DUE_DAYS, upi_sales_today=10_240, cash_available_by_bill_due=8_800, vpa="lakshmistores@ptyes"),
    Store(id="NET", name="Other Paytm shops", is_network=True, due_days=DUE_DAYS),
]

CUSTOMERS = [
    Customer(id="C_PRIYA", name="Priya Nair", phone="9000000011", vpa="priya.n@ptyes", lang="en-IN", loginable=True),
    Customer(id="C_RAMESH", name="Ramesh Kumar", phone="9000000012", vpa="ramesh.k@ptyes", lang="hi-IN", loginable=True),
    Customer(id="C_VIKRAM", name="Vikram Rao", phone="9000000013", vpa="vikram.r@ptyes", lang="hi-IN", loginable=True),
    Customer(id="C_ANITA", name="Anita Desai", phone="9000000014", vpa="anita.d@ptyes", lang="kn-IN", loginable=True),
]

# (id, name, open verified dues, created on)
REGULARS = [
    ("C_SURESH", "Suresh Gowda", 4_200, date(2026, 10, 14)),
    ("C_KAVYA", "Kavya Rao", 3_800, date(2026, 10, 18)),
    ("C_IMRAN", "Imran Sheikh", 3_600, date(2026, 10, 20)),
    ("C_MEENA", "Meena Iyer", 3_500, date(2026, 10, 22)),
    ("C_ROHIT", "Rohit Shetty", 3_400, date(2026, 10, 25)),
    ("C_LATA", "Lata Kulkarni", 3_000, date(2026, 10, 28)),
]

CATALOGUE = [
    ("ATTA10", "Wheat atta 10 kg", "staples", 480), ("RICE5", "Rice 5 kg", "staples", 450),
    ("TOOR2", "Toor dal 2 kg", "staples", 320), ("OIL1", "Sunflower oil 1 L", "oil_ghee", 150),
    ("SUG2", "Sugar 2 kg", "staples", 100), ("TEA250", "Tea 250 g", "staples", 140),
    ("SALT1", "Salt 1 kg", "staples", 28), ("DET1", "Detergent 1 kg", "household", 32),
    ("GHEE1", "Ghee 1 L", "oil_ghee", 650), ("MILK1", "Milk 1 L", "dairy", 60),
    ("BISC", "Biscuits family pack", "snacks", 90), ("SOAP4", "Bath soap ×4", "household", 180),
    ("KAJU250", "Cashews 250 g", "sweets_dryfruits", 320), ("AGAR", "Agarbatti pack", "puja_items", 60),
]

# Soundbox preset chips (served by the API so no names live in frontend code).
PRESETS = [
    {"label": "Priya 340", "customer_id": "C_PRIYA", "amount": 340},
    {"label": "Ramesh 340", "customer_id": "C_RAMESH", "amount": 340},
    {"label": "Vikram 340", "customer_id": "C_VIKRAM", "amount": 340},
    {"label": "Anita 2000", "customer_id": "C_ANITA", "amount": 2000},
]

# Priya's monthly basket (spec §3.6): ₹1,850, bought in the first week of Aug, Sep and Oct.
BASKET = [("ATTA10", 1), ("RICE5", 1), ("TOOR2", 1), ("OIL1", 2), ("SUG2", 1), ("TEA250", 1), ("SALT1", 1), ("DET1", 1)]

FESTIVE = {
    "festival": "Diwali", "date": "2026-11-08", "supplier": "Sharma Traders", "bill_due": "2026-11-06",
    "weekly_baseline": {"sweets_dryfruits": 4000, "oil_ghee": 9000, "snacks": 8000, "puja_items": 4500, "staples": 30000},
    "festive_week": {"sweets_dryfruits": 9600, "oil_ghee": 16200, "snacks": 13600, "puja_items": 13500, "staples": 36000},
}


def _d(m: int, d: int, hh: int = 11) -> datetime:
    return datetime(2026, m, d, hh, 0)


def _items(spec: list[tuple[str, int]]) -> list[dict]:
    prices = {sku: price for sku, _, _, price in CATALOGUE}
    return [{"sku": sku, "qty": qty, "price": prices[sku]} for sku, qty in spec]


def _amount(items: list[dict]) -> int:
    return sum(i["qty"] * i["price"] for i in items)


class _Writer:
    def __init__(self, s):
        self.s = s

    def entry(self, store, cid, created: datetime, amount: int | None = None, *, paid_after: int | None = None,
              items=None, state: str | None = None) -> Entry:
        """paid_after = days after creation it was repaid in full (None = still open)."""
        items_ = _items(items) if items else None
        amount = amount if amount is not None else _amount(items_)
        e = Entry(store_id=store, customer_id=cid, amount=amount, state=state or "verified", source="seed",
                  created_at=created, due_date=created.date() + timedelta(days=DUE_DAYS), items=items_)
        if paid_after is not None:
            when = created + timedelta(days=paid_after)
            e.paid, e.state, e.settled_at = amount, "settled", when
        self.s.add(e)
        self.s.flush()
        if paid_after is not None:
            p = Payment(store_id=store, customer_id=cid, amount=amount, method="upi", purpose="repayment",
                        merchant_share=amount, created_at=e.settled_at)
            self.s.add(p)
            self.s.flush()
            self.s.add(Allocation(payment_id=p.id, entry_id=e.id, amount=amount))
        return e


def _history(w: _Writer) -> None:
    # Priya: 12 on time (Apr–Oct, ₹300–1,900, paid after 3–10 days); the basket in the first week of Aug, Sep, Oct.
    misc = [
        (_d(4, 12), [("GHEE1", 1)]), (_d(4, 26), [("ATTA10", 1), ("SUG2", 1), ("MILK1", 5)]),
        (_d(5, 14), [("RICE5", 1), ("TOOR2", 1), ("OIL1", 1)]), (_d(5, 28), [("BISC", 4), ("TEA250", 1)]),
        (_d(6, 15), [("KAJU250", 2), ("SOAP4", 1)]), (_d(7, 10), [("ATTA10", 1), ("RICE5", 1), ("GHEE1", 1)]),
        (_d(7, 24), [("MILK1", 6), ("BISC", 2)]), (_d(8, 20), [("SOAP4", 2), ("DET1", 2)]),
        (_d(9, 22), [("GHEE1", 1), ("KAJU250", 1)]),
    ]
    for when, items in misc:
        w.entry("S1", "C_PRIYA", when, items=items, paid_after=5)
    for when in (_d(8, 3), _d(9, 4), _d(10, 2)):
        w.entry("S1", "C_PRIYA", when, items=BASKET, paid_after=5)

    # Ramesh: 8 on time, 2 settled 20–30 days late, ₹1,700 open from 12 Sep (due 12 Oct → 19 days overdue).
    for m, d, amt in [(4, 3, 600), (4, 18, 450), (5, 2, 800), (5, 20, 350), (6, 6, 700), (6, 22, 500),
                      (7, 3, 900), (7, 19, 400)]:
        w.entry("S1", "C_RAMESH", _d(m, d), amt, paid_after=20)
    w.entry("S1", "C_RAMESH", _d(8, 1), 1_200, paid_after=30 + 22)   # 22 days late
    w.entry("S1", "C_RAMESH", _d(8, 10), 900, paid_after=30 + 27)    # 27 days late
    w.entry("S1", "C_RAMESH", _d(9, 12, 18), 1_700)

    # Vikram: 2 on time, 5 late, 1 written off (₹800), ₹2,600 open from 21 Aug (due 20 Sep → 41 days overdue).
    w.entry("S1", "C_VIKRAM", _d(3, 5), 500, paid_after=12)
    w.entry("S1", "C_VIKRAM", _d(3, 20), 400, paid_after=25)
    for m, d, amt, late in [(4, 2, 700, 15), (4, 25, 600, 22), (5, 15, 900, 35), (6, 1, 500, 18), (6, 20, 650, 40)]:
        w.entry("S1", "C_VIKRAM", _d(m, d), amt, paid_after=30 + late)
    w.entry("S1", "C_VIKRAM", _d(2, 10), 800, state="written_off")  # written off in Jul 2026
    w.entry("S1", "C_VIKRAM", _d(8, 21, 19), 2_600)

    # Anita at other Paytm shops: 12 on time, 1 late, ₹600 open from 20 Oct (due 19 Nov).
    for i in range(12):
        w.entry("NET", "C_ANITA", _d(4, 1) + timedelta(days=14 * i), 400 + 50 * (i % 5), paid_after=7)
    w.entry("NET", "C_ANITA", _d(9, 25), 700, paid_after=30 + 6)
    w.entry("NET", "C_ANITA", _d(10, 20), 600)

    # Regulars: 6 on time each, plus one open verified entry from the last 20 days.
    for cid, _, open_amt, opened in REGULARS:
        for i in range(6):
            w.entry("S1", cid, _d(4, 5) + timedelta(days=21 * i), 500 + 100 * i, paid_after=6)
        w.entry("S1", cid, datetime.combine(opened, time(18, 30)), open_amt)


def build() -> dict:
    t0 = _time.perf_counter()
    db.rebuild()
    with db.session() as s:
        for st in STORES:
            s.add(Store(**st.model_dump()))
        for c in CUSTOMERS:
            s.add(Customer(**c.model_dump()))
        for cid, name, _, _ in REGULARS:
            s.add(Customer(id=cid, name=name, lang="kn-IN"))
        s.flush()
        for cid in [c.id for c in CUSTOMERS if c.id != "C_ANITA"] + [r[0] for r in REGULARS]:
            s.add(StoreCustomer(store_id="S1", customer_id=cid))
        s.add(StoreCustomer(store_id="NET", customer_id="C_ANITA"))
        s.add(User(role="merchant", phone="9000000001", store_id="S1"))
        for c in CUSTOMERS:
            s.add(User(role="customer", phone=c.phone, customer_id=c.id))
        for sku, name, cat, price in CATALOGUE:
            s.add(CatalogueItem(sku=sku, name=name, category=cat, price=price))
        s.add(FestiveProfile(store_id="S1", profile=FESTIVE))
        s.add(SoundboxState(store_id="S1", state={}))
        s.flush()
        _history(_Writer(s))
        s.commit()

        from app.core import growth  # local: growth imports the scoring modules, which import models only

        growth.generate(s, "S1")
        s.commit()
    return {"ok": True, "seconds": round(_time.perf_counter() - t0, 2), "demo_date": get_settings().demo_date.isoformat()}


if __name__ == "__main__":
    print(build())
