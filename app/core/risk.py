"""Safe limit / Udhaar Guardrail (v2 spec §4.2). Deterministic; no AI decides a limit.

The merchant only ever sees this store's numbers. Network figures (other shops) enter the
formula through the score and the exposure cap, and the reasons never name another store or
show its amounts.
"""
import math
import time
from dataclasses import asdict, dataclass, field
from fractions import Fraction

from sqlmodel import Session, select

from app.core import score as score_mod
from app.core.money import inr
from app.models import Entry, ScoreShare, Store

MAX_LIMIT = 5_000
NEW_SHOP_SHARE = Fraction(2, 5)  # 40 % of the network limit for a shop the customer is new to
NEW_SHOP_MAX = 1_500


def floor50(x) -> int:
    return math.floor(Fraction(x) / 50) * 50


def multiplier(d: int) -> Fraction:
    if d == 0:
        return Fraction(1)
    if d <= 14:
        return Fraction(3, 4)
    if d <= 30:
        return Fraction(3, 5)
    return Fraction(0)


def base_limit(s: int) -> Fraction:
    return 500 + Fraction(s - 300, 600) * 4500


@dataclass
class Guardrail:
    customer_id: str
    store_id: str
    amount: int
    score: int
    base: int
    safe_limit: int
    band: str  # green | amber | red
    credit_now: int
    collect_now: int
    kind: str  # existing | new_starter | new_shared | brand_new
    needs_share: bool = False  # new to this shop, known to the network, nothing shared yet
    reasons: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def has_active_share(s: Session, customer_id: str, store_id: str) -> bool:
    return s.exec(select(ScoreShare.id).where(ScoreShare.customer_id == customer_id, ScoreShare.store_id == store_id,
                                              ScoreShare.revoked_at == None)).first() is not None  # noqa: E711


def evaluate(s: Session, store_id: str, customer_id: str, amount: int) -> Guardrail:
    t0 = time.perf_counter()
    store = s.get(Store, store_id)
    entries = score_mod.customer_entries(s, customer_id)
    sc = score_mod.compute(entries)
    base = base_limit(sc.value)
    open_all = [e for e in entries if e.state in score_mod.OPEN_STATES]
    net_out = sum(e.amount - e.paid for e in open_all)
    exposure_room = max(Fraction(0), base - net_out)
    here = [e for e in entries if e.store_id == store_id and e.state not in ("proposed", "expired", "cancelled")]
    reasons, tags = [], []

    if not here and not entries:
        kind, safe = "brand_new", Fraction(store.starter_limit)
        reasons.append(f"New customer: starter limit {inr(store.starter_limit)}")
    elif not here and not has_active_share(s, customer_id, store_id):
        kind, safe = "new_starter", Fraction(store.starter_limit)
        reasons.append(f"New to this shop, score not shared: starter limit {inr(store.starter_limit)}")
    elif not here:
        kind = "new_shared"
        safe = min(Fraction(floor50(base * NEW_SHOP_SHARE)), Fraction(NEW_SHOP_MAX), exposure_room)
        reasons += [f"Bharosa Score {sc.value} ({sc.band}), shared by the customer",
                    f"New to this shop: 40% of network limit, max {inr(NEW_SHOP_MAX)}",
                    f"Network exposure room {inr(math.floor(exposure_room))}"]
        tags.append("New · Paytm network")
    else:
        kind = "existing"
        open_here = [e for e in here if e.state in score_mod.OPEN_STATES]
        d = max((score_mod.overdue_days(e) for e in open_here), default=0)
        o = sum(e.amount - e.paid for e in open_here)
        m = multiplier(d)
        safe = min(base * m - o, exposure_room)
        reasons.append(f"Score {sc.value} → base {inr(math.floor(base))}")
        if d:
            overdue_amt = sum(e.amount - e.paid for e in open_here if score_mod.overdue_days(e) > 0)
            reasons.append(f"{inr(overdue_amt)} overdue for {d} days → ×{float(m):g}")
        if o:
            reasons.append(f"Already owes {inr(o)} here")
        if exposure_room < base * m - o:
            reasons.append("Capped by what they owe across Paytm shops")

    safe_i = max(0, min(MAX_LIMIT, floor50(max(safe, 0))))
    band_ = "green" if amount <= safe_i else ("red" if safe_i == 0 else "amber")
    credit = min(amount, safe_i)
    return Guardrail(customer_id=customer_id, store_id=store_id, amount=amount, score=sc.value,
                     base=math.floor(base), safe_limit=safe_i, band=band_, credit_now=credit, collect_now=amount - credit,
                     kind=kind, needs_share=(kind == "new_starter"), reasons=reasons, tags=tags,
                     ms=round((time.perf_counter() - t0) * 1000, 2))


def verdict(g: Guardrail, name: str, starter: int) -> str:
    """Merchant-facing verdict text (spec §4.2)."""
    first = name.split()[0]
    if g.needs_share:
        return f"New customer. Ask them to scan to share their Bharosa Score. Starter limit {inr(starter)}."
    if g.band == "green":
        return f"Safe. {first} can take up to {inr(g.safe_limit)}."
    if g.band == "amber":
        lead = "Network-trusted new customer. " if g.kind == "new_shared" else "Caution. "
        return f"{lead}Give {inr(g.credit_now)} on credit, collect {inr(g.collect_now)} now."
    return f"High risk. Collect full payment ({inr(g.amount)})."

