"""Bharosa Score (v2 spec §4.1): computed live from repayment history across all stores. Never stored.

    score = clamp(300, 900, 600 + 15 × on-time − 10 × late − 2 × max overdue days − 60 × written off)
"""
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.config import today
from app.models import Entry

OPEN_STATES = ("verified", "partly_paid")


def band(score: int) -> str:
    if score >= 800:
        return "Excellent"
    if score >= 700:
        return "Strong"
    if score >= 550:
        return "Good"
    return "Building"


def overdue_days(e: Entry) -> int:
    if e.state not in OPEN_STATES:
        return 0
    return max(0, (today() - e.due_date).days)


@dataclass
class Score:
    value: int
    band: str
    breakdown: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"score": self.value, "band": self.band, "breakdown": self.breakdown}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def compute(entries: list[Entry]) -> Score:
    on_time = sum(1 for e in entries if e.state == "settled" and e.settled_at.date() <= e.due_date)
    late = sum(1 for e in entries if e.state == "settled" and e.settled_at.date() > e.due_date)
    written_off = sum(1 for e in entries if e.state == "written_off")
    max_od = max((overdue_days(e) for e in entries), default=0)
    lines = [{"label": "Starting score", "points": 600}]
    if on_time:
        lines.append({"label": f"{_plural(on_time, 'on-time repayment')}", "points": 15 * on_time})
    if late:
        lines.append({"label": f"{_plural(late, 'late repayment')}", "points": -10 * late})
    if max_od:
        lines.append({"label": f"Overdue for {max_od} days now", "points": -2 * max_od})
    if written_off:
        lines.append({"label": f"{_plural(written_off, 'unpaid udhaar written off')}", "points": -60 * written_off})
    raw = sum(x["points"] for x in lines)
    value = max(300, min(900, raw))
    if value != raw:
        lines.append({"label": "Kept within 300–900", "points": value - raw})
    return Score(value, band(value), lines)


def customer_entries(s: Session, customer_id: str) -> list[Entry]:
    return list(s.exec(select(Entry).where(Entry.customer_id == customer_id)).all())


def for_customer(s: Session, customer_id: str) -> Score:
    return compute(customer_entries(s, customer_id))
