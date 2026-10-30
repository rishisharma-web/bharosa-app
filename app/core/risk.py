"""Risk engine / Udhaar Guardrail (spec 7.3). Deterministic; no AI decides a limit.

`compute()` is a pure function of a `Features` row. `load_features()` reads one row,
`load_features_bulk()` reads a whole store at once (Udhaar Book, snapshot).

Spec decisions made explicit here:
- O (already owed) counts every open entry at this store, plus `proposed` and
  `disputed` ones: the goods have already left the shop, so a second sale while
  the first is waiting for a scan must not get a fresh full limit.
- A customer is new when they have no ledger history anywhere except pending
  (proposed/disputed) entries. A new customer's limit is the starter limit minus
  what is pending, so repeated sales cannot each claim the full starter limit.
"""
import time
from dataclasses import asdict, dataclass, field
from fractions import Fraction

from sqlmodel import Session, select

from app import clock
from app.core import ledger
from app.core.money import floor_to, inr
from app.models import Customer, Entry, Store

MAX_LIMIT = 5_000
PENDING_STATES = ("proposed", "disputed")


@dataclass
class Features:
    customer_id: str
    store_id: str
    score: int  # S
    owed: int  # O
    max_overdue_days: int  # D
    overdue_amount: int
    is_new: bool
    starter_limit: int


@dataclass
class RiskResult:
    customer_id: str
    store_id: str
    amount: int
    safe_limit: int
    band: str  # green | amber | red
    credit_now: int
    collect_now: int
    base: int | None
    multiplier: float | None
    reasons: list[str] = field(default_factory=list)
    features: dict = field(default_factory=dict)
    ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def multiplier(d: int) -> Fraction:
    if d == 0:
        return Fraction(1)
    if d <= 14:
        return Fraction(3, 4)
    if d <= 30:
        return Fraction(3, 5)
    return Fraction(0)


def base_limit(score: int) -> Fraction:
    """S=300 → ₹500, S=900 → ₹5,000 (linear)."""
    return 500 + Fraction(score - 300, 600) * 4500


def safe_limit(f: Features) -> tuple[int, Fraction | None, Fraction | None]:
    if f.is_new:
        return max(0, floor_to(f.starter_limit - f.owed, 50)), None, None
    base, m = base_limit(f.score), multiplier(f.max_overdue_days)
    return min(max(0, floor_to(base * m - f.owed, 50)), MAX_LIMIT), base, m


def compute(f: Features, amount: int) -> RiskResult:
    limit, base, m = safe_limit(f)
    band = "green" if amount <= limit else "red" if limit == 0 else "amber"
    credit = min(amount, limit)
    return RiskResult(
        customer_id=f.customer_id, store_id=f.store_id, amount=amount, safe_limit=limit, band=band,
        credit_now=credit, collect_now=amount - credit,
        base=None if base is None else floor_to(base, 1),
        multiplier=None if m is None else float(m),
        reasons=_reasons(f, limit, base, m),
        features=asdict(f),
    )


def _reasons(f: Features, limit: int, base: Fraction | None, m: Fraction | None) -> list[str]:
    if f.is_new:
        out = [f"New customer → starter limit {inr(f.starter_limit)}"]
        if f.owed:
            out.append(f"Waiting for confirmation on {inr(f.owed)}")
        return out
    out = []
    if f.max_overdue_days > 0:
        out.append(f"{inr(f.overdue_amount)} overdue for {f.max_overdue_days} days → limit ×{_fmt_m(m)}")
    else:
        out.append("Nothing overdue → limit ×1")
    out.append(f"Score {f.score} → base {inr(floor_to(base, 1))}")
    if f.owed:
        out.append(f"Already owes {inr(f.owed)}")
    if limit == MAX_LIMIT:
        out.append(f"Capped at {inr(MAX_LIMIT)}")
    return out


def _fmt_m(m: Fraction) -> str:
    return f"{float(m):g}"


# ---------------------------------------------------------------- feature loading

def _features_from(c: Customer, store: Store, entries: list[Entry], has_history: bool) -> Features:
    today = clock.today()
    owed = overdue = max_d = 0
    for e in entries:
        if e.state in ledger.OPEN_STATES or e.state in PENDING_STATES:
            r = ledger.remaining(e)
            owed += r
            d = ledger.overdue_days(e, today)
            if d > 0:
                overdue += r
                max_d = max(max_d, d)
    return Features(customer_id=c.id, store_id=store.id, score=c.score, owed=owed, max_overdue_days=max_d,
                    overdue_amount=overdue, is_new=not has_history, starter_limit=store.starter_limit)


def load_features(s: Session, store_id: str, customer_id: str) -> Features:
    store, c = s.get(Store, store_id), s.get(Customer, customer_id)
    entries = s.exec(select(Entry).where(
        Entry.store_id == store_id, Entry.customer_id == customer_id,
        Entry.state.in_(ledger.OPEN_STATES + PENDING_STATES))).all()
    has_history = s.exec(select(Entry.id).where(
        Entry.customer_id == customer_id, Entry.state.not_in(PENDING_STATES)).limit(1)).first() is not None
    return _features_from(c, store, list(entries), has_history)


def load_features_bulk(s: Session, store_id: str, customer_ids: list[str]) -> dict[str, Features]:
    store = s.get(Store, store_id)
    custs = s.exec(select(Customer).where(Customer.id.in_(customer_ids))).all()
    entries = s.exec(select(Entry).where(
        Entry.store_id == store_id, Entry.customer_id.in_(customer_ids),
        Entry.state.in_(ledger.OPEN_STATES + PENDING_STATES))).all()
    with_history = set(s.exec(select(Entry.customer_id).where(
        Entry.customer_id.in_(customer_ids), Entry.state.not_in(PENDING_STATES)).distinct()).all())
    by_c: dict[str, list[Entry]] = {}
    for e in entries:
        by_c.setdefault(e.customer_id, []).append(e)
    return {c.id: _features_from(c, store, by_c.get(c.id, []), c.id in with_history) for c in custs}


def evaluate(s: Session, store_id: str, customer_id: str, amount: int) -> RiskResult:
    """Load features and compute, with the measured latency the UI shows."""
    t0 = time.perf_counter()
    res = compute(load_features(s, store_id, customer_id), amount)
    res.ms = round((time.perf_counter() - t0) * 1000, 2)
    return res
