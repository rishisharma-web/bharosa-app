"""Notebook vs Bharosa (spec 11.5): the same customers and the same random draws, two policies,
30 simulated days from Mon 26 Oct. Labelled in the UI as a simulation on synthetic data.

Starting book: Lakshmi Stores' seeded customers and open udhaar (identical for both).
Each day every customer may buy on credit; every draw (purchase, amount, how late they pay,
never-pays, partial pays, reaction to a reminder) is made once per customer and shared by both
policies, so the only difference is the policy:

  Notebook  credit always given in full; no reminders, no auto-pay, no advance.
  Bharosa   guardrail (the real risk formula): only the safe limit goes on credit, the rest is
            paid at the counter; reminders for overdue ≥ 7 days make late payers pay 10 days
            earlier with 60 % probability (ASSUMPTION); salary-day auto-pay for ~50 % of
            salary-day customers; a Supplier Advance when the forecast shows a gap.

"Bad udhaar" = credit given during the 30 days that the customer will never repay.
"""
import json
import random
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from app.config import get_settings
from app.core import risk
from app.sim import seed as seed_mod
from app.sim.personas import PERSONAS

DAYS = 30
START = date(2026, 10, 26)
CACHE = Path(__file__).resolve().parent.parent.parent / "fixtures" / "compare.json"
BILL_DAY, BILL_AMOUNT = 4, 18_000  # Sharma Traders, Fri 30 Oct
NUDGE_SHIFT_DAYS, NUDGE_EFFECT_P = 10, 0.6
DUE_DAYS = 30
VERSION = 1  # bump when the simulation changes so the cached JSON is rebuilt


@dataclass
class Draws:
    """Everything random about one credit, drawn once and shared by both policies."""
    delay: int
    never: bool
    partial: bool
    nudge_works: bool
    jitter: int


@dataclass
class Credit:
    customer_id: str
    created: date
    amount: int
    pays: list[tuple[date, int]] = field(default_factory=list)
    paid: int = 0
    settled: date | None = None

    @property
    def remaining(self) -> int:
        return self.amount - self.paid


@dataclass
class Cust:
    id: str
    persona: str
    score: int
    mandate: bool


def _draws(rng: random.Random, persona: str) -> Draws:
    lo, hi = {"punctual": (3, 10), "salary_day": (0, 2), "late_payer": (25, 50),
              "chronic_defaulter": (30, 70), "cash_only": (5, 15)}[persona]
    return Draws(delay=rng.randint(lo, hi), never=persona == "chronic_defaulter" and rng.random() < 0.4,
                 partial=persona in ("late_payer", "chronic_defaulter") and rng.random() < 0.3,
                 nudge_works=rng.random() < NUDGE_EFFECT_P, jitter=rng.randint(0, 20))


def _next_first(d: date) -> date:
    return (d.replace(day=1) + timedelta(days=32)).replace(day=1)


def _schedule(c: Cust, created: date, amount: int, dr: Draws, bharosa: bool) -> list[tuple[date, int]]:
    if dr.never:
        return []
    if c.persona == "salary_day":
        when = _next_first(created) + timedelta(days=0 if (bharosa and c.mandate) else dr.delay)
    else:
        when = created + timedelta(days=dr.delay)
    if when < START:  # already late against habit when the simulation starts
        when = START + timedelta(days=dr.jitter)
    if bharosa and c.persona == "late_payer" and dr.nudge_works:
        overdue_from = created + timedelta(days=DUE_DAYS + 7)  # reminders start at 7 days overdue
        when = max(min(when, max(when - timedelta(days=NUDGE_SHIFT_DAYS), overdue_from)), START)
    if dr.partial:
        half = amount // 20 * 10
        return [(when, half)]
    return [(when, amount)]


def _features(c: Cust, credits: list[Credit], today: date) -> risk.Features:
    mine = [x for x in credits if x.customer_id == c.id]
    open_ = [x for x in mine if x.remaining > 0]
    owed = sum(x.remaining for x in open_)
    ods = [(today - (x.created + timedelta(days=DUE_DAYS))).days for x in open_]
    od_amt = sum(x.remaining for x, d in zip(open_, ods) if d > 0)
    return risk.Features(c.id, "S1", c.score, owed, max([0, *ods]), od_amt, is_new=not mine, starter_limit=500)


def _run(custs: list[Cust], opening: list[tuple[str, date, int]], purchases: dict, credit_draws: dict,
         bharosa: bool) -> dict:
    by_id = {c.id: c for c in custs}
    credits: list[Credit] = []
    for i, (cid, created, amount) in enumerate(opening):
        cr = Credit(cid, created, amount)
        cr.pays = _schedule(by_id[cid], created, amount, credit_draws[("open", i)], bharosa)
        credits.append(cr)
    stuck, bad, collected_on_counter, bad_total = [], [], 0, 0
    cash = 3_200
    supplier_on_time = None
    for d in range(DAYS):
        today = START + timedelta(days=d)
        if d == BILL_DAY:
            supplier_on_time = cash >= BILL_AMOUNT or bharosa  # Bharosa: the advance covers the gap
        for cid, amount in purchases.get(d, []):
            c = by_id[cid]
            give = amount
            if bharosa:
                give = risk.compute(_features(c, credits, today), amount).credit_now
                collected_on_counter += amount - give
            if give <= 0:
                continue
            dr = credit_draws[("new", d, cid)]
            cr = Credit(cid, today, give)
            cr.pays = _schedule(c, today, give, dr, bharosa)
            credits.append(cr)
            if dr.never:
                bad_total += give
        inflow = 0
        for cr in credits:
            for when, amt in cr.pays:
                if when == today and cr.remaining > 0:
                    take = min(amt, cr.remaining)
                    cr.paid += take
                    inflow += take
                    if cr.remaining == 0:
                        cr.settled = today
        cash += 1_200 + inflow
        stuck.append(sum(cr.remaining for cr in credits))
        bad.append(bad_total)
    # Days each new credit stayed out; unpaid ones count as outstanding until the last day
    # (censored), so slow and never-paid udhaar weighs against the policy that gave it.
    last = START + timedelta(days=DAYS - 1)
    days_out = [((cr.settled or last) - cr.created).days for cr in credits if cr.created >= START]
    return {
        "stuck": stuck, "bad": bad,
        "median_days_to_collect": statistics.median(days_out) if days_out else None,
        "collected_at_counter": collected_on_counter, "supplier_on_time": bool(supplier_on_time),
    }


def simulate(seed: int | None = None) -> dict:
    seed = get_settings().seed if seed is None else seed
    w = seed_mod.build_world(seed)
    s1 = [c for c in w.customers if c.store_id == "S1"]
    custs = [Cust(c.id, c.persona or "punctual", c.score, bool(c.mandate_at) or c.id == "C_RAMESH") for c in s1]
    opening = [(e.customer_id, e.created_at.date(), e.remaining) for e in w.entries
               if e.store_id == "S1" and e.remaining > 0]

    purchases: dict[int, list[tuple[str, int]]] = {}
    credit_draws: dict = {}
    for c in custs:
        rng = random.Random(f"{seed}:compare:{c.id}")
        p = PERSONAS[c.persona]
        rate = sum(p.takes_per_month) / 2 / 30
        for d in range(DAYS):
            if rng.random() < rate:
                purchases.setdefault(d, []).append((c.id, rng.randrange(p.amount[0], p.amount[1] + 1, 10)))
                credit_draws[("new", d, c.id)] = _draws(rng, c.persona)
    for i, (cid, _, _) in enumerate(opening):
        persona = next(c.persona for c in custs if c.id == cid)
        credit_draws[("open", i)] = _draws(random.Random(f"{seed}:compare:open:{i}"), persona)

    nb = _run(custs, opening, purchases, credit_draws, bharosa=False)
    bh = _run(custs, opening, purchases, credit_draws, bharosa=True)
    days = [(START + timedelta(days=d)).isoformat() for d in range(DAYS)]
    return {
        "label": "Simulation on synthetic data",
        "days": days,
        "series": {
            "money_stuck": {"notebook": nb["stuck"], "bharosa": bh["stuck"]},
            "bad_udhaar": {"notebook": nb["bad"], "bharosa": bh["bad"]},
        },
        "kpis": {
            "median_days_to_collect": {"notebook": nb["median_days_to_collect"], "bharosa": bh["median_days_to_collect"]},
            "bad_udhaar_prevented": nb["bad"][-1] - bh["bad"][-1],
            "working_capital_freed": nb["stuck"][-1] - bh["stuck"][-1],
            "collected_at_counter": bh["collected_at_counter"],
            "supplier_paid_on_time": {"notebook": nb["supplier_on_time"], "bharosa": bh["supplier_on_time"]},
        },
        "assumptions": [
            "Same customers, purchases and repayment behaviour in both columns; only the policy differs.",
            "Reminders make late payers pay 10 days earlier with 60% probability (assumption).",
            "Salary-day auto-pay for about half of salary-day customers.",
            "Bad udhaar = credit given in these 30 days that is never repaid.",
            "Days to collect: median days a new credit stays unpaid; unpaid at day 30 counts as 30 minus its age.",
        ],
    }


def cached() -> dict:
    """Spec 7.14: computed once, then served from fixtures/compare.json (rebuilt if seed/version differ)."""
    seed = get_settings().seed
    if CACHE.exists():
        data = json.loads(CACHE.read_text(encoding="utf-8"))
        if data.get("seed") == seed and data.get("version") == VERSION:
            return data
    out = {**simulate(seed), "seed": seed, "version": VERSION}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
