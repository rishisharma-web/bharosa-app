"""Seeded world (spec 4 and 7.14).

Pipeline
1. Generate customers per persona mix with a private `random.Random` per store, so S2
   changes can never shift S1 numbers.
2. Generate 5 Aug – 25 Oct 2026 history: entries, then payments planned per persona,
   applied in time order with the same FIFO rule the live ledger uses.
3. Calibrate S1's generated customers so the store totals hit the contract exactly:
   verified ₹38,000, total ₹45,000, mandate customers' dues ₹9,000.
4. Add the five named customers with hand-written history (spec 4.2).
5. Top up S2's recent verified credit so its 30-day baseline is realistic; otherwise
   integrity rule R2 ("burst") would fire on any activity at a store with no history.
6. Write everything in one transaction and reset the sim clock.

Run: `python -m app.sim.seed`
"""
import random
import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from app import clock, db, state
from app.config import get_settings
from app.models import (
    Allocation, Bill, Consent, Customer, Entry, Mandate, Repayment, Sale, Store, StoreCustomer,
)
from app.realtime.trace import trace
from app.sim.personas import FIRST_NAMES, PERSONAS, RESERVED_TOKENS, S1_MIX, S2_MIX, SURNAMES

HISTORY_START = date(2026, 8, 5)
HISTORY_END = date(2026, 10, 25)
HISTORY_END_DT = datetime.combine(HISTORY_END, time(23, 59, 59))
TODAY = clock.DEMO_START.date()
DUE_DAYS = 30

# Contract targets for S1 generated customers (named customers add ₹5,300 verified on top).
# Verified split by score so V_eligible (score >= 550) = 38,000 - 2,600 (Vikram) - 10,000 = ₹25,400,
# giving an advance cap of ₹10,160 >= the ₹9,200 gap.
TARGET_MANDATE_VERIFIED = 9_000
TARGET_LOWSCORE_VERIFIED = 10_000
TARGET_OTHER_VERIFIED = 13_700
TARGET_UNVERIFIED = 7_000
ELIGIBLE_SCORE = 550
MANDATE_CAP = 3_000
N_MANDATES = 8
S2_MIN_30D_VERIFIED_CREDIT = 96_000  # ₹3,200/day → R2 threshold ₹9,600 > the ₹8,000 fraud ring

STORES = [
    dict(id="S1", name="Lakshmi Stores", area="Jayanagar, Bengaluru", vpa="lakshmistores@ptyes", lang="hi-IN",
         starter_limit=500, due_days=DUE_DAYS, cash_on_hand=3_200, daily_net_cash=1_200, avg_daily_upi_sales=10_000),
    dict(id="S2", name="Sai Kirana", area="Banashankari, Bengaluru", vpa="saikirana@ptyes", lang="kn-IN",
         starter_limit=500, due_days=DUE_DAYS, cash_on_hand=2_500, daily_net_cash=1_000, avg_daily_upi_sales=8_000),
]


# ---------------------------------------------------------------- in-memory world

@dataclass(eq=False)
class GCust:
    id: str
    store_id: str
    name: str
    persona: str | None
    score: int
    vpa: str | None
    mobile: str
    device_id: str
    lang: str
    created_at: datetime
    aliases: list = field(default_factory=list)
    is_new: bool = False
    named: bool = False
    mandate_at: datetime | None = None


@dataclass(eq=False)
class GEntry:
    store_id: str
    customer_id: str
    amount: int
    created_at: datetime
    verified_at: datetime | None
    device_id: str | None
    paid: int = 0
    settled_at: datetime | None = None
    row: Entry | None = None

    @property
    def remaining(self) -> int:
        return self.amount - self.paid


@dataclass(eq=False)
class GRep:
    store_id: str
    customer_id: str
    amount: int
    source: str
    created_at: datetime
    payer_vpa: str | None
    allocs: list = field(default_factory=list)  # [(GEntry, amount)]
    excess: int = 0


@dataclass
class World:
    customers: list[GCust] = field(default_factory=list)
    entries: list[GEntry] = field(default_factory=list)
    payments: list[GRep] = field(default_factory=list)


def _at(rng: random.Random, d: date, lo: int = 8, hi: int = 20) -> datetime:
    return datetime.combine(d, time(rng.randint(lo, hi), rng.randrange(0, 60, 5)))


def _rand_day(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randrange((end - start).days + 1))


def _amount(rng: random.Random, lo: int, hi: int, avoid_500: bool = False) -> int:
    while True:
        a = rng.randrange(lo, hi + 1, 10)
        if not (avoid_500 and a == 500):
            return a


# ---------------------------------------------------------------- customers

def _make_customers(rng: random.Random, store_id: str, mix: dict[str, int], id_base: int,
                    used_names: set, used_mobiles: set) -> list[GCust]:
    personas = [p for p, n in mix.items() for _ in range(n)]
    rng.shuffle(personas)
    out = []
    for i, persona in enumerate(personas, start=1):
        while True:
            first, last = rng.choice(FIRST_NAMES), rng.choice(SURNAMES)
            name = f"{first} {last}"
            if name not in used_names and not ({first.lower(), last.lower()} & RESERVED_TOKENS):
                break
        used_names.add(name)
        while True:
            mobile = str(rng.choice([6, 7, 8, 9])) + "".join(str(rng.randrange(10)) for _ in range(9))
            if mobile not in used_mobiles and mobile != "9876500000":
                break
        used_mobiles.add(mobile)
        cid = f"C_{id_base + i}"
        p = PERSONAS[persona]
        out.append(GCust(
            id=cid, store_id=store_id, name=name, persona=persona,
            score=rng.randint(*p.score),
            vpa=None if persona == "cash_only" else f"{first.lower()}.{last.lower()}{id_base + i}@ptyes",
            mobile=mobile, device_id=f"dev-{cid.lower()}",
            lang="kn-IN" if rng.random() < 0.3 else "hi-IN",
            created_at=datetime.combine(HISTORY_START - timedelta(days=rng.randint(30, 400)), time(10, 0)),
            aliases=[first],
        ))
    return out


# ---------------------------------------------------------------- history

def _gen_entries(rng: random.Random, c: GCust) -> list[GEntry]:
    p = PERSONAS[c.persona]
    days = (HISTORY_END - HISTORY_START).days + 1
    n = max(1, round(rng.randint(*p.takes_per_month) * days / 30))
    out = []
    for _ in range(n):
        created = _at(rng, _rand_day(rng, HISTORY_START, HISTORY_END))
        verified = c.mandate_at is not None or rng.random() < p.verify_rate
        out.append(GEntry(
            store_id=c.store_id, customer_id=c.id,
            amount=_amount(rng, *p.amount, avoid_500=c.vpa is None),
            created_at=created,
            verified_at=created + timedelta(seconds=rng.randint(40, 400)) if verified else None,
            device_id=c.device_id if verified else None,
        ))
    return sorted(out, key=lambda e: e.created_at)


def _plan_payments(rng: random.Random, c: GCust, entries: list[GEntry]) -> list[GRep]:
    plan: list[GRep] = []

    def pay(when: datetime, amount: int, source: str = "upi"):
        if amount > 0 and when <= HISTORY_END_DT:
            plan.append(GRep(c.store_id, c.id, amount, source, when, c.vpa if source != "cash" else None))

    if c.persona == "salary_day":
        covered = 0
        for boundary in (date(2026, 9, 1), date(2026, 10, 1)):
            due = [e for e in entries[covered:] if e.created_at.date() < boundary]
            covered += len(due)
            amount = sum(e.amount for e in due)
            if c.mandate_at and c.mandate_at.date() < boundary:
                pay(datetime.combine(boundary, time(10, 0)), amount, "mandate")
            else:
                pay(_at(rng, boundary + timedelta(days=rng.randint(0, 2)), 10, 20), amount)
        return plan

    for e in entries:
        d = e.created_at.date()
        if c.persona == "punctual":
            pay(_at(rng, d + timedelta(days=rng.randint(3, 10))), e.amount)
        elif c.persona == "late_payer":
            first = d + timedelta(days=rng.randint(25, 50))
            if rng.random() < 0.3:
                half = e.amount // 20 * 10
                pay(_at(rng, first), half)
                pay(_at(rng, first + timedelta(days=rng.randint(15, 30))), e.amount - half)
            else:
                pay(_at(rng, first), e.amount)
        elif c.persona == "chronic_defaulter":
            if rng.random() < 0.4:
                continue
            when = _at(rng, d + timedelta(days=rng.randint(30, 70)))
            pay(when, e.amount // 20 * 10 if rng.random() < 0.5 else e.amount)
        elif c.persona == "cash_only":
            pay(_at(rng, d + timedelta(days=rng.randint(5, 15))), e.amount, "cash")
    return plan


def _fifo_order(entries: list[GEntry]) -> list[GEntry]:
    """Same order as the live ledger: verified receivables oldest-first, then unverified."""
    return sorted(entries, key=lambda e: (e.verified_at is None, e.created_at))


def _apply_payments(w: World) -> None:
    by_cust: dict[str, list[GEntry]] = {}
    for e in w.entries:
        by_cust.setdefault(e.customer_id, []).append(e)
    for rep in sorted(w.payments, key=lambda r: r.created_at):
        left = rep.amount
        open_ = [e for e in by_cust.get(rep.customer_id, []) if e.remaining > 0 and e.created_at <= rep.created_at]
        for e in _fifo_order(open_):
            if left == 0:
                break
            take = min(left, e.remaining)
            e.paid += take
            left -= take
            rep.allocs.append((e, take))
            if e.remaining == 0:
                e.settled_at = rep.created_at
        rep.excess = left


# ---------------------------------------------------------------- calibration

def _calibrate(rng: random.Random, w: World, in_pool, target: int, recipients: list[GCust],
               verified: bool, cap: int | None = None) -> None:
    """Remove untouched newest entries / add recent ones until the pool's open total == target."""
    def pool() -> list[GEntry]:
        return [e for e in w.entries if in_pool(e) and e.remaining > 0]

    def dues(cid: str) -> int:
        return sum(e.remaining for e in pool() if e.customer_id == cid)

    total = sum(e.remaining for e in pool())
    for e in sorted(pool(), key=lambda e: e.created_at, reverse=True):
        if total <= target:
            break
        if e.paid == 0:
            w.entries.remove(e)
            total -= e.amount

    diff = target - total
    while diff > 0:
        if diff < 150:
            bumpable = [e for e in pool() if e.paid == 0 and e.amount + diff <= 900
                        and (cap is None or dues(e.customer_id) + diff <= cap)
                        and not (_cust(w, e.customer_id).vpa is None and e.amount + diff == 500)]
            if bumpable:
                bumpable[-1].amount += diff
                return
        amt = diff if diff <= 700 else rng.randrange(300, 701, 10)
        if 0 < diff - amt < 150:
            amt = diff - 150
        options = [c for c in recipients if cap is None or dues(c.id) + amt <= cap]
        c = rng.choice(options)
        created = _at(rng, _rand_day(rng, date(2026, 10, 12), HISTORY_END))
        w.entries.append(GEntry(
            store_id=c.store_id, customer_id=c.id, amount=amt, created_at=created,
            verified_at=created + timedelta(seconds=rng.randint(40, 400)) if verified else None,
            device_id=c.device_id if verified else None,
        ))
        diff -= amt


def _cust(w: World, cid: str) -> GCust:
    return next(c for c in w.customers if c.id == cid)


def _generate_store(rng: random.Random, w: World, store_id: str, mix: dict, id_base: int,
                    used_names: set, used_mobiles: set, n_mandates: int = 0) -> list[GCust]:
    custs = _make_customers(rng, store_id, mix, id_base, used_names, used_mobiles)
    salary = [c for c in custs if c.persona == "salary_day"]
    for c in rng.sample(salary, n_mandates):
        c.mandate_at = _at(rng, _rand_day(rng, date(2026, 8, 20), date(2026, 9, 20)))
    for c in custs:
        es = _gen_entries(rng, c)
        w.entries.extend(es)
        w.payments.extend(_plan_payments(rng, c, es))
    w.customers.extend(custs)
    return custs


# ---------------------------------------------------------------- named customers (spec 4.2)

def _dt(m: int, d: int, hh: int = 10, mm: int = 0) -> datetime:
    return datetime(2026, m, d, hh, mm)


def _named(w: World) -> None:
    named = [
        GCust("C_RAMESH", "S1", "Ramesh Kumar", "salary_day", 680, "ramesh.k@ptyes", "9845012345",
              "dev-ramesh", "hi-IN", _dt(3, 2), aliases=["Ramesh", "Ramesh bhai", "रमेश"], named=True),
        GCust("C_PRIYA", "S1", "Priya Nair", "punctual", 780, "priya.nair@ptyes", "9845023456",
              "dev-priya", "hi-IN", _dt(1, 15), aliases=["Priya", "Priya madam", "प्रिया"], named=True),
        GCust("C_VIKRAM", "S1", "Vikram Rao", "chronic_defaulter", 420, "vikram.rao@ptyes", "9845034567",
              "dev-vikram", "hi-IN", _dt(4, 9), aliases=["Vikram", "विक्रम"], named=True),
        GCust("C_SURESH", "S1", "Suresh Gowda", "cash_only", 610, None, "9845045678",
              "dev-suresh", "kn-IN", _dt(5, 20), aliases=["Suresh", "सुरेश"], named=True),
        GCust("C_ANITA", "S1", "Anita Desai", None, 600, "anita.d@ptyes", "9845056789",
              "dev-anita", "hi-IN", _dt(10, 25, 18), aliases=["Anita", "अनीता"], is_new=True, named=True),
    ]
    w.customers.extend(named)

    def entry(cid: str, when: datetime, amount: int) -> None:
        c = next(x for x in named if x.id == cid)
        w.entries.append(GEntry("S1", cid, amount, when, when + timedelta(minutes=3), c.device_id))

    def paid(cid: str, when: datetime, amount: int, source: str = "upi") -> None:
        c = next(x for x in named if x.id == cid)
        w.payments.append(GRep("S1", cid, amount, source, when, c.vpa if source != "cash" else None))

    # Ramesh: settled August history; one open ₹1,800 from Mon 7 Sep (due 7 Oct → 19 days overdue on 26 Oct).
    entry("C_RAMESH", _dt(8, 10, 11, 20), 450)
    entry("C_RAMESH", _dt(8, 22, 18, 5), 380)
    paid("C_RAMESH", _dt(9, 2, 19, 10), 830)
    entry("C_RAMESH", _dt(9, 7, 10, 30), 1_800)
    # Priya: always repays within a week; nothing open.
    for (m, d, amt) in [(8, 8, 320), (8, 24, 260), (9, 9, 410), (9, 21, 180), (10, 3, 350), (10, 12, 290)]:
        entry("C_PRIYA", _dt(m, d, 17, 40), amt)
        paid("C_PRIYA", _dt(m, d, 17, 40) + timedelta(days=5), amt)
    # Vikram: one late repayment, then ₹2,600 from Sun 16 Aug (due 15 Sep → 41 days overdue).
    entry("C_VIKRAM", _dt(8, 6, 12), 600)
    paid("C_VIKRAM", _dt(9, 20, 20), 600)
    entry("C_VIKRAM", _dt(8, 16, 9, 45), 2_600)
    # Suresh: pays cash; ₹900 from 20 Oct, not yet due.
    entry("C_SURESH", _dt(9, 10, 18), 350)
    paid("C_SURESH", _dt(9, 18, 19), 350, "cash")
    entry("C_SURESH", _dt(10, 20, 17, 30), 900)
    # Anita: brand new, no history.


def _s2_top_up(rng: random.Random, w: World, s2: list[GCust]) -> None:
    lo = HISTORY_END - timedelta(days=29)

    def recent_verified() -> int:
        return sum(e.amount for e in w.entries
                   if e.store_id == "S2" and e.verified_at and e.created_at.date() >= lo)

    payers = [c for c in s2 if c.vpa and c.persona in ("punctual", "salary_day")]
    total = recent_verified()
    while total < S2_MIN_30D_VERIFIED_CREDIT:
        c = rng.choice(payers)
        created = _at(rng, _rand_day(rng, lo, HISTORY_END - timedelta(days=8)))
        e = GEntry("S2", c.id, rng.randrange(300, 701, 10), created,
                   created + timedelta(seconds=rng.randint(40, 400)), c.device_id)
        w.entries.append(e)
        when = _at(rng, created.date() + timedelta(days=rng.randint(3, 7)))
        e.paid, e.settled_at = e.amount, when
        w.payments.append(GRep("S2", c.id, e.amount, "upi", when, c.vpa, allocs=[(e, e.amount)]))
        total += e.amount


# ---------------------------------------------------------------- build

def build_world(seed: int) -> World:
    rng1, rng2 = random.Random(seed), random.Random(seed + 1)
    w = World()
    used_names = {"Ramesh Kumar", "Priya Nair", "Vikram Rao", "Suresh Gowda", "Anita Desai", "Kamala Kumar"}
    used_mobiles = {"9845012345", "9845023456", "9845034567", "9845045678", "9845056789", "9876500000"}

    s1 = _generate_store(rng1, w, "S1", S1_MIX, 1000, used_names, used_mobiles, n_mandates=N_MANDATES)
    s2 = _generate_store(rng2, w, "S2", S2_MIX, 2000, used_names, used_mobiles)
    _apply_payments(w)

    # --- S1 calibration (generated customers only) ---
    mandate_ids = {c.id for c in s1 if c.mandate_at}
    gen_ids = {c.id for c in s1}
    is_mandate = lambda e: e.customer_id in mandate_ids  # noqa: E731
    # Keep each mandate customer's dues under the cap before pooling.
    for cid in mandate_ids:
        mine = sorted([e for e in w.entries if e.customer_id == cid and e.remaining > 0],
                      key=lambda e: e.created_at, reverse=True)
        while sum(e.remaining for e in mine) > MANDATE_CAP - 400 and mine and mine[0].paid == 0:
            w.entries.remove(mine.pop(0))
    _calibrate(rng1, w, lambda e: is_mandate(e) and e.verified_at is not None,
               TARGET_MANDATE_VERIFIED, [c for c in s1 if c.mandate_at], verified=True, cap=MANDATE_CAP)
    low_ids = {c.id for c in s1 if c.score < ELIGIBLE_SCORE}
    _calibrate(rng1, w, lambda e: e.customer_id in low_ids and e.verified_at is not None,
               TARGET_LOWSCORE_VERIFIED, [c for c in s1 if c.id in low_ids], verified=True)
    _calibrate(rng1, w, lambda e: (e.customer_id in gen_ids and e.customer_id not in low_ids
                                   and not is_mandate(e) and e.verified_at is not None),
               TARGET_OTHER_VERIFIED,
               [c for c in s1 if not c.mandate_at and c.id not in low_ids
                and c.persona in ("punctual", "salary_day", "late_payer")],
               verified=True)
    _calibrate(rng1, w, lambda e: e.customer_id in gen_ids and e.verified_at is None,
               TARGET_UNVERIFIED,
               [c for c in s1 if not c.mandate_at and c.vpa is not None and c.persona != "chronic_defaulter"],
               verified=False)

    _named(w)
    _apply_payments_named(w)
    _s2_top_up(rng2, w, s2)
    _check_rule2_safety(w)
    return w


def _apply_payments_named(w: World) -> None:
    named = {c.id for c in w.customers if c.named}
    sub = World(entries=[e for e in w.entries if e.customer_id in named],
                payments=[p for p in w.payments if p.customer_id in named])
    _apply_payments(sub)


def _check_rule2_safety(w: World) -> None:
    """Reconciliation rule 2 links a payment to the only no-VPA customer with an open entry
    of exactly that amount. The ₹500 'Kamala Kumar' demo payment must fall through to the agent."""
    no_vpa = {c.id for c in w.customers if c.vpa is None}
    bad = [e for e in w.entries if e.store_id == "S1" and e.customer_id in no_vpa and e.remaining == 500]
    if bad:
        raise AssertionError(f"seed produced a ₹500 open entry for a no-VPA customer: {bad[0].customer_id}")


def _state(e: GEntry) -> str:
    if e.remaining == 0:
        return "settled"
    if e.paid > 0:
        st = "partly_paid"
    else:
        st = "verified" if e.verified_at else "unverified"
    if e.verified_at and (TODAY - (e.created_at.date() + timedelta(days=DUE_DAYS))).days > 60:
        st = "defaulted"
    return st


def _write(w: World) -> dict:
    with db.session() as s:
        for st in STORES:
            s.add(Store(**st))
        for c in w.customers:
            s.add(Customer(id=c.id, name=c.name, aliases=c.aliases, mobile=c.mobile, vpa=c.vpa,
                           device_id=c.device_id, persona=c.persona, score=c.score, is_new=c.is_new,
                           lang=c.lang, created_at=c.created_at))
        s.flush()
        for c in w.customers:
            s.add(StoreCustomer(store_id=c.store_id, customer_id=c.id))

        for e in sorted(w.entries, key=lambda e: e.created_at):
            e.row = Entry(store_id=e.store_id, customer_id=e.customer_id, amount=e.amount, requested_amount=e.amount,
                          paid_amount=e.paid, state=_state(e), created_at=e.created_at,
                          due_date=e.created_at.date() + timedelta(days=DUE_DAYS),
                          verified_at=e.verified_at, confirm_device_id=e.device_id, settled_at=e.settled_at)
            s.add(e.row)
        s.flush()

        reps = sorted((p for p in w.payments if p.allocs), key=lambda p: p.created_at)
        rep_rows = []
        for p in reps:
            allocated = sum(a for _, a in p.allocs)
            r = Repayment(store_id=p.store_id, customer_id=p.customer_id, amount=allocated, source=p.source,
                          payer_vpa=p.payer_vpa, matched_by="mandate" if p.source == "mandate" else
                          ("merchant" if p.source == "cash" else "rule"),
                          allocated=allocated, lender_share=0, merchant_share=allocated, created_at=p.created_at)
            s.add(r)
            rep_rows.append((p, r))
        s.flush()
        for p, r in rep_rows:
            for e, amt in p.allocs:
                s.add(Allocation(repayment_id=r.id, entry_id=e.row.id, amount=amt))

        # Consents: data sharing from each customer's first confirmation; mandates for S1's mandate customers.
        first_verified: dict[str, datetime] = {}
        for e in w.entries:
            if e.verified_at and (e.customer_id not in first_verified or e.verified_at < first_verified[e.customer_id]):
                first_verified[e.customer_id] = e.verified_at
        for cid, at in first_verified.items():
            s.add(Consent(customer_id=cid, type="data_share", granted_at=at))
        for c in w.customers:
            if c.mandate_at:
                s.add(Mandate(customer_id=c.id, store_id=c.store_id, cap=MANDATE_CAP, window_start_day=1,
                              window_end_day=5, status="active", created_at=c.mandate_at))
                s.add(Consent(customer_id=c.id, store_id=c.store_id, type="payment_mandate", granted_at=c.mandate_at))

        s.add(Bill(id="B1", store_id="S1", distributor="Sharma Traders", amount=18_000, due_date=date(2026, 10, 30)))

        _write_sales(s)

        clock.set(clock.DEMO_START)
        clock.persist(s)
        for k in ("lang", "focus_customer", "demo_beat", "demo_caption", "soundbox", "briefing"):
            state.put(s, k, state.DEFAULTS[k])
        s.commit()
    return {"customers": len(w.customers), "entries": len(w.entries), "repayments": len(reps)}


def _write_sales(s) -> None:
    rng = random.Random(get_settings().seed + 7)
    for st in STORES:
        d = HISTORY_START
        while d <= HISTORY_END:
            amt = round(st["avg_daily_upi_sales"] * rng.uniform(0.85, 1.15) / 10) * 10
            s.add(Sale(store_id=st["id"], amount=amt, note="walk-in UPI (daily total)",
                       created_at=datetime.combine(d, time(21, 0))))
            d += timedelta(days=1)
        # A few early-morning sales on demo day so "Today's collection" is alive at 09:00.
        for hh, mm, amt in [(7, 40, 260), (8, 15, 540), (8, 50, 180)]:
            s.add(Sale(store_id=st["id"], amount=amt, note="walk-in UPI",
                       created_at=datetime.combine(TODAY, time(hh, mm))))


def seed() -> dict:
    t0 = _time.perf_counter()
    db.rebuild()
    world = build_world(get_settings().seed)
    stats = _write(world)
    stats["seconds"] = round(_time.perf_counter() - t0, 2)
    trace("db", "World seeded", stats, ms=stats["seconds"] * 1000)
    return stats


if __name__ == "__main__":
    print(seed())
