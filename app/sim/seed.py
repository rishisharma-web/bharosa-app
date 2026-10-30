"""Seeded world (spec 4, simplified): one shop, three story customers, six background customers,
round numbers everywhere. Every row is written out here so the demo numbers can be read off
this file.

Lakshmi Stores (S1) on Mon 26 Oct 2026, 09:00
    Story:      Priya (pays on time), Ramesh (hero, ₹1,500 20 days overdue), Vikram (₹2,500, 45 days)
    Background: Meena, Arjun, Kavya (salary-day auto-pay), Deepak, Sunita, Imran (pays cash, unscanned)
    Outstanding ₹18,000 · verified ₹17,000 · overdue ₹7,000
    Sharma Traders ₹15,000 due Fri 30 Oct; cash ₹4,000 + ₹1,500/day → ₹10,000 by Friday → ₹5,000 short
    Salary day (Sun 1 Nov): auto-pay collects ₹10,000 (Ramesh ₹1,900 after beat 2 + ₹8,100) → ₹2,000 to lender

Sai Kirana (S2) exists only for the fraud beat; it gets 30 days of steady ₹5,000/day verified
credit so its normal level is known. Integrity rule R2 flags a day above 3× the 30-day average; at
₹5,000/day even "yesterday's normal ₹5,000 + the ring's ₹8,000" stays under that line all demo week.

Run: `python -m app.sim.seed`
"""
import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from app import clock, db, state
from app.core import briefing
from app.models import (
    Allocation, Bill, Consent, Customer, Entry, Mandate, Repayment, Sale, Store, StoreCustomer,
)
from app.realtime.trace import trace

TODAY = clock.DEMO_START.date()
DUE_DAYS = 30

STORES = [
    dict(id="S1", name="Lakshmi Stores", area="Jayanagar, Bengaluru", vpa="lakshmistores@ptyes", lang="hi-IN",
         starter_limit=500, due_days=DUE_DAYS, cash_on_hand=4_000, daily_net_cash=1_500, avg_daily_upi_sales=10_000),
    dict(id="S2", name="Sai Kirana", area="Banashankari, Bengaluru", vpa="saikirana@ptyes", lang="kn-IN",
         starter_limit=500, due_days=DUE_DAYS, cash_on_hand=3_000, daily_net_cash=1_200, avg_daily_upi_sales=8_000),
]


def _d(m: int, d: int, hh: int = 10, mm: int = 0) -> datetime:
    return datetime(2026, m, d, hh, mm)


@dataclass
class C:
    id: str
    store_id: str
    name: str
    score: int
    vpa: str | None
    mobile: str
    persona: str | None
    aliases: list[str]
    lang: str = "hi-IN"
    mandate_cap: int | None = None
    since: datetime = field(default_factory=lambda: _d(1, 15))


@dataclass
class E:
    """One udhaar entry and the payments that settled it (each payment pays only this entry)."""
    customer_id: str
    created: datetime
    amount: int
    verified: bool = True
    paid: list[tuple[datetime, int, str]] = field(default_factory=list)  # (when, amount, upi|cash|mandate)


CUSTOMERS = [
    # ---- story customers
    C("C_PRIYA", "S1", "Priya Nair", 780, "priya.nair@ptyes", "9845023456", "punctual", ["Priya", "प्रिया"],
      since=_d(1, 15)),
    C("C_RAMESH", "S1", "Ramesh Kumar", 660, "ramesh.k@ptyes", "9845012345", "salary_day",
      ["Ramesh", "Ramesh bhai", "रमेश"], since=_d(3, 2)),
    C("C_VIKRAM", "S1", "Vikram Rao", 420, "vikram.rao@ptyes", "9845034567", "chronic_defaulter",
      ["Vikram", "विक्रम"], since=_d(4, 9)),
    # ---- background customers (salary-day auto-pay)
    C("C_MEENA", "S1", "Meena Iyer", 720, "meena.iyer@ptyes", "9845045671", "salary_day", ["Meena"],
      mandate_cap=5_000),
    C("C_ARJUN", "S1", "Arjun Shetty", 690, "arjun.shetty@ptyes", "9845045672", "salary_day", ["Arjun"],
      lang="kn-IN", mandate_cap=5_000),
    C("C_KAVYA", "S1", "Kavya Menon", 700, "kavya.menon@ptyes", "9845045673", "salary_day", ["Kavya"],
      mandate_cap=5_000),
    # ---- background customers (no auto-pay)
    C("C_DEEPAK", "S1", "Deepak Joshi", 640, "deepak.joshi@ptyes", "9845045674", "late_payer", ["Deepak"]),
    C("C_SUNITA", "S1", "Sunita Reddy", 610, "sunita.reddy@ptyes", "9845045675", "punctual", ["Sunita"],
      lang="kn-IN"),
    C("C_IMRAN", "S1", "Imran Khan", 600, None, "9845045676", "cash_only", ["Imran"]),  # no UPI ID on file
    # ---- Sai Kirana's regulars
    C("C_S2_1", "S2", "Basavaraj Patil", 650, "basavaraj.p@ptyes", "9845055551", "punctual", ["Basavaraj"], "kn-IN"),
    C("C_S2_2", "S2", "Lalitha Hegde", 650, "lalitha.h@ptyes", "9845055552", "punctual", ["Lalitha"], "kn-IN"),
    C("C_S2_3", "S2", "Girish Naik", 650, "girish.n@ptyes", "9845055553", "punctual", ["Girish"], "kn-IN"),
    C("C_S2_4", "S2", "Rekha Bhat", 650, "rekha.b@ptyes", "9845055554", "punctual", ["Rekha"], "kn-IN"),
]


def _s1_entries() -> list[E]:
    upi = "upi"
    out = [
        # Priya: always pays within five days; owes nothing today.
        *[E("C_PRIYA", _d(m, d, 17, 40), amt, paid=[(_d(m, d, 17, 40) + timedelta(days=5), amt, upi)])
          for m, d, amt in [(8, 8, 500), (8, 24, 300), (9, 9, 400), (9, 21, 200), (10, 3, 300), (10, 12, 300)]],
        # Ramesh: August paid on salary day; ₹1,500 from Sun 6 Sep still open (due 6 Oct → 20 days overdue).
        E("C_RAMESH", _d(8, 10, 11, 20), 500, paid=[(_d(9, 2, 19, 10), 500, upi)]),
        E("C_RAMESH", _d(8, 22, 18, 5), 400, paid=[(_d(9, 2, 19, 10), 400, upi)]),
        E("C_RAMESH", _d(9, 6, 10, 30), 1_500),
        # Vikram: one late payment, then ₹2,500 from Wed 12 Aug (due 11 Sep → 45 days overdue).
        E("C_VIKRAM", _d(8, 5, 12), 500, paid=[(_d(9, 20, 20), 500, upi)]),
        E("C_VIKRAM", _d(8, 12, 9, 45), 2_500),
        # Background, all verified except Imran's (he never scanned the QR).
        E("C_MEENA", _d(10, 10, 18), 1_500), E("C_MEENA", _d(10, 20, 18), 1_500),
        E("C_ARJUN", _d(10, 14, 19), 2_500),
        E("C_KAVYA", _d(10, 8, 17), 1_600), E("C_KAVYA", _d(10, 18, 17), 1_000),
        E("C_DEEPAK", _d(9, 16, 18), 3_000),  # due 16 Oct → 10 days overdue
        E("C_SUNITA", _d(10, 15, 11), 1_900),
        E("C_IMRAN", _d(10, 22, 20), 1_000, verified=False),
    ]
    return out


def _s2_entries() -> list[E]:
    """₹5,000 of verified credit every day for 30 days, settled three days later."""
    out = []
    for i in range(30):
        created = datetime.combine(TODAY - timedelta(days=30 - i), time(11, 0))
        pay_at = created + timedelta(days=3)
        cid = f"C_S2_{i % 4 + 1}"
        out.append(E(cid, created, 5_000, paid=[(pay_at, 5_000, "upi")] if pay_at.date() < TODAY else []))
    return out


def _state(e: E) -> str:
    paid = sum(a for _, a, _ in e.paid)
    if paid >= e.amount:
        return "settled"
    if paid > 0:
        return "partly_paid"
    return "verified" if e.verified else "unverified"


def _write() -> dict:
    custs = {c.id: c for c in CUSTOMERS}
    entries = sorted(_s1_entries() + _s2_entries(), key=lambda e: e.created)
    n_reps = 0
    with db.session() as s:
        for st in STORES:
            s.add(Store(**st))
        for c in CUSTOMERS:
            s.add(Customer(id=c.id, name=c.name, aliases=c.aliases, mobile=c.mobile, vpa=c.vpa,
                           device_id=f"dev-{c.id[2:].lower()}", persona=c.persona, score=c.score, is_new=False,
                           lang=c.lang, created_at=c.since))
        s.flush()
        for c in CUSTOMERS:
            s.add(StoreCustomer(store_id=c.store_id, customer_id=c.id))

        reps: dict[tuple[str, datetime, str], Repayment] = {}
        first_verified: dict[str, datetime] = {}
        for e in entries:
            c = custs[e.customer_id]
            paid = sum(a for _, a, _ in e.paid)
            verified_at = e.created + timedelta(minutes=3) if e.verified else None
            row = Entry(store_id=c.store_id, customer_id=c.id, amount=e.amount, requested_amount=e.amount,
                        paid_amount=paid, state=_state(e), created_at=e.created,
                        due_date=e.created.date() + timedelta(days=DUE_DAYS), verified_at=verified_at,
                        confirm_device_id=f"dev-{c.id[2:].lower()}" if e.verified else None,
                        settled_at=max(w for w, _, _ in e.paid) if paid >= e.amount else None)
            s.add(row)
            s.flush()
            if verified_at and (c.id not in first_verified or verified_at < first_verified[c.id]):
                first_verified[c.id] = verified_at
            for when, amt, source in e.paid:
                key = (c.id, when, source)  # one payment can settle several entries (Ramesh on 2 Sep)
                if key not in reps:
                    reps[key] = Repayment(store_id=c.store_id, customer_id=c.id, amount=0, source=source,
                                          payer_vpa=c.vpa if source != "cash" else None,
                                          matched_by={"cash": "merchant", "mandate": "mandate"}.get(source, "rule"),
                                          allocated=0, merchant_share=0, created_at=when)
                    s.add(reps[key])
                    s.flush()
                    n_reps += 1
                r = reps[key]
                r.amount += amt
                r.allocated += amt
                r.merchant_share += amt
                s.add(Allocation(repayment_id=r.id, entry_id=row.id, amount=amt))

        for cid, at in first_verified.items():
            s.add(Consent(customer_id=cid, type="data_share", granted_at=at))
        for c in CUSTOMERS:
            if c.mandate_cap:
                at = _d(9, 15, 12)
                s.add(Mandate(customer_id=c.id, store_id=c.store_id, cap=c.mandate_cap, window_start_day=1,
                              window_end_day=5, status="active", created_at=at))
                s.add(Consent(customer_id=c.id, store_id=c.store_id, type="payment_mandate", granted_at=at))

        s.add(Bill(id="B1", store_id="S1", distributor="Sharma Traders", amount=15_000, due_date=date(2026, 10, 30)))
        _write_sales(s)

        clock.set(clock.DEMO_START)
        clock.persist(s)
        for k, v in state.DEFAULTS.items():
            state.put(s, k, v)
        s.commit()
    return {"customers": len(CUSTOMERS), "entries": len(entries), "repayments": n_reps}


# Walk-in UPI sales per day (the shop's normal takings, not udhaar), in round hundreds.
SALES_PATTERN = [9_800, 10_400, 9_600, 10_200, 11_000, 12_400, 8_600]


def _write_sales(s) -> None:
    for st in STORES:
        scale = st["avg_daily_upi_sales"] / 10_000
        d = TODAY - timedelta(days=60)
        while d < TODAY:
            amt = round(SALES_PATTERN[d.weekday()] * scale / 100) * 100
            s.add(Sale(store_id=st["id"], amount=amt, note="walk-in UPI (daily total)",
                       created_at=datetime.combine(d, time(21, 0))))
            d += timedelta(days=1)
        # Early-morning sales on demo day so "Today's collection" is alive at 09:00.
        for hh, mm, amt in [(7, 40, 300), (8, 15, 500), (8, 50, 200)]:
            s.add(Sale(store_id=st["id"], amount=amt, note="walk-in UPI", created_at=datetime.combine(TODAY, time(hh, mm))))


def seed() -> dict:
    t0 = _time.perf_counter()
    db.rebuild()
    stats = _write()
    with db.session() as s:  # beat 0: a template briefing exists even before Munim rephrases it
        briefing.refresh(s, "S1")
        s.commit()
    stats["seconds"] = round(_time.perf_counter() - t0, 2)
    trace("db", "World seeded", stats, ms=stats["seconds"] * 1000)
    return stats


if __name__ == "__main__":
    print(seed())
