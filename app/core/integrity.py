"""Integrity rules: fake-udhaar rings that farm loans (spec 7.8). Deterministic, graph-based.

| Rule | Condition                                                                 | Weight |
| R1   | ≥ 3 customers confirmed from the same device within 24 h                  | 0.4    |
| R2   | verified credit in the last 24 h > 3 × the store's 30-day daily average   | 0.2    |
| R3   | ≥ 80 % of the last 10 entries from new customers are ₹500 multiples      | 0.1    |
| R4   | median create→confirm < 15 s for new customers (first seen ≤ 7 days ago,  | 0.1    |
|      | no UPI repayment before confirming)                                       |        |
| R5   | a store → customer → store money cycle within 48 h                        | 0.4    |

risk = min(1, Σ weights); risk ≥ 0.6 → flag the implicated entries (out of V_eligible),
block Supplier Advance for the store, raise a risk alert.

Spec decisions made explicit here:
- R2 needs a non-zero baseline; a store with no history has no "normal" to burst from.
- "New" means a customer first seen at the store within 7 days, for both R3 and R4. R3 reads
  the spec's "last 10 new entries" as entries from new customers (min 3); counting every recent
  entry would let a store's ordinary traffic dilute four fresh fake ones.
- R4 needs at least 3 qualifying confirmations so one quick scan by a new customer is not a signal.
- R5's graph uses money edges only (P2P out, UPI/mandate repayments in). Udhaar is goods, not
  money; counting it as an edge would make every customer who ever repaid look like a cycle.
"""
import statistics
from datetime import timedelta

import networkx as nx
from sqlmodel import Session, select

from app import clock
from app.core.money import inr
from app.models import Customer, Entry, P2PTransfer, Repayment, RiskAlert, Store, StoreCustomer
from app.realtime.trace import trace

THRESHOLD = 0.6
NEW_CUSTOMER_DAYS = 7
RULES = {
    "R1": ("Shared device", 0.4),
    "R2": ("Burst of new credit", 0.2),
    "R3": ("Round amounts", 0.1),
    "R4": ("Instant confirms", 0.1),
    "R5": ("Money cycle", 0.4),
}


def _r1_shared_device(verified_24h: list[Entry]) -> tuple[str, set[int]] | None:
    by_device: dict[str, list[Entry]] = {}
    for e in verified_24h:
        if e.confirm_device_id:
            by_device.setdefault(e.confirm_device_id, []).append(e)
    for dev, es in by_device.items():
        if len({e.customer_id for e in es}) >= 3:
            return f"{len({e.customer_id for e in es})} customers confirmed from device {dev}", {e.id for e in es}
    return None


def _r2_burst(s: Session, store_id: str, verified_24h: list[Entry]) -> tuple[str, set[int]] | None:
    now = clock.now()
    recent = sum(e.amount for e in verified_24h)
    lo = now - timedelta(days=31)
    hi = now - timedelta(days=1)
    baseline = sum(s.exec(select(Entry.amount).where(Entry.store_id == store_id, Entry.verified_at >= lo,
                                                     Entry.verified_at < hi)).all()) / 30
    if baseline > 0 and recent > 3 * baseline:
        return f"{inr(recent)} verified in 24 h vs {inr(round(baseline))}/day normal", {e.id for e in verified_24h}
    return None


def _new_customer_ids(s: Session, store_id: str) -> set[str]:
    since = clock.now() - timedelta(days=NEW_CUSTOMER_DAYS)
    return set(s.exec(select(Customer.id).join(StoreCustomer, StoreCustomer.customer_id == Customer.id).where(
        StoreCustomer.store_id == store_id, Customer.created_at >= since)).all())


def _r3_round(s: Session, store_id: str) -> tuple[str, set[int]] | None:
    new = _new_customer_ids(s, store_id)
    if not new:
        return None
    last = s.exec(select(Entry).where(Entry.store_id == store_id, Entry.customer_id.in_(new),
                                      Entry.state.not_in(("proposed", "disputed")))
                  .order_by(Entry.created_at.desc()).limit(10)).all()
    if len(last) < 3:
        return None
    rounds = [e for e in last if e.amount % 500 == 0]
    if len(rounds) / len(last) >= 0.8:
        return f"{len(rounds)} of {len(last)} new entries are multiples of ₹500", {e.id for e in rounds}
    return None


def _r4_instant(s: Session, verified_24h: list[Entry]) -> tuple[str, set[int]] | None:
    now = clock.now()
    custs = {c.id: c for c in s.exec(select(Customer).where(
        Customer.id.in_({e.customer_id for e in verified_24h} or {""}))).all()}
    qualifying = []
    for e in verified_24h:
        c = custs[e.customer_id]
        if c.created_at < now - timedelta(days=NEW_CUSTOMER_DAYS):
            continue
        paid_before = s.exec(select(Repayment.id).where(Repayment.customer_id == c.id, Repayment.source == "upi",
                                                        Repayment.created_at < e.verified_at)).first()
        if paid_before is None:
            qualifying.append(e)
    if len(qualifying) < 3:
        return None
    med = statistics.median((e.verified_at - e.created_at).total_seconds() for e in qualifying)
    if med < 15:
        return f"new customers confirmed in a median {med:.0f} s", {e.id for e in qualifying}
    return None


def _r5_money_cycle(s: Session, store_id: str) -> tuple[str, set[str]] | None:
    since = clock.now() - timedelta(hours=48)
    g = nx.DiGraph()
    for t in s.exec(select(P2PTransfer).where(P2PTransfer.store_id == store_id, P2PTransfer.created_at >= since)).all():
        g.add_edge(t.from_id, t.to_id, kind="p2p")
    for r in s.exec(select(Repayment).where(Repayment.store_id == store_id, Repayment.created_at >= since,
                                            Repayment.source.in_(("upi", "mandate")),
                                            Repayment.customer_id != None)).all():  # noqa: E711
        g.add_edge(r.customer_id, store_id, kind="repayment")
    if store_id not in g:
        return None
    cycles = [c for c in nx.simple_cycles(g) if store_id in c]
    if not cycles:
        return None
    custs = {n for c in cycles for n in c if n != store_id}
    return f"{len(custs)} customers repaid with money the shop sent them", custs


def evaluate(s: Session, store_id: str) -> dict:
    now = clock.now()
    since = now - timedelta(hours=24)
    verified_24h = list(s.exec(select(Entry).where(Entry.store_id == store_id, Entry.verified_at >= since)).all())
    hits: dict[str, tuple[str, set]] = {}
    for rid, res in (("R1", _r1_shared_device(verified_24h)), ("R2", _r2_burst(s, store_id, verified_24h)),
                     ("R3", _r3_round(s, store_id)), ("R4", _r4_instant(s, verified_24h)),
                     ("R5", _r5_money_cycle(s, store_id))):
        if res:
            hits[rid] = res
    risk = round(min(1.0, sum(RULES[r][1] for r in hits)), 2)

    entry_ids: set[int] = set()
    cycle_customers: set[str] = set()
    for rid, (_, ids) in hits.items():
        if rid == "R5":
            cycle_customers |= ids
        else:
            entry_ids |= ids
    if cycle_customers:
        entry_ids |= {e.id for e in verified_24h if e.customer_id in cycle_customers}
    return {"store_id": store_id, "risk": risk, "entry_ids": sorted(entry_ids),
            "rules": [{"id": r, "name": RULES[r][0], "detail": hits[r][0]} for r in sorted(hits)]}


def check(s: Session, store_id: str, reason: str) -> RiskAlert | None:
    """Evaluate, trace, and act if the risk crosses the threshold. Returns a new alert, if any."""
    res = evaluate(s, store_id)
    ids = [r["id"] for r in res["rules"]]
    trace("integrity", f"{store_id} risk {res['risk']:.1f}" + (f" ({', '.join(ids)})" if ids else ""),
          {"reason": reason, **res})
    if res["risk"] < THRESHOLD:
        return None

    for e in s.exec(select(Entry).where(Entry.id.in_(res["entry_ids"] or [-1]))).all():
        if not e.integrity_flag:
            e.integrity_flag = True
            s.add(e)
    store = s.get(Store, store_id)
    store.advance_blocked = True
    s.add(store)

    last = s.exec(select(RiskAlert).where(RiskAlert.store_id == store_id)
                  .order_by(RiskAlert.created_at.desc())).first()
    if last and {r["id"] for r in last.rules} == set(ids) and last.created_at >= clock.now() - timedelta(hours=24):
        return None
    alert = RiskAlert(store_id=store_id, rules=res["rules"], risk=res["risk"], entry_ids=res["entry_ids"],
                      created_at=clock.now())
    s.add(alert)
    s.flush()
    trace("integrity", f"{store.name}: entries flagged, Supplier Advance blocked", {"alert_id": alert.id})
    return alert


def summary(rules: list[dict]) -> str:
    names = ", ".join(r["name"].lower() for r in rules)
    return f"possible fake-udhaar ring ({names})"
