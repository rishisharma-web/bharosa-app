"""Bharosa Score (spec 7.4): range 300–900, start 600, network-wide.

Every change goes through `apply_delta`, which clamps, writes a ScoreEvent (the
audit trail behind "recent changes" and score_delta_7d) and traces it.
"""
from sqlmodel import Session, select

from app import clock
from app.models import Customer, ScoreEvent
from app.realtime.trace import trace

MIN_SCORE, MAX_SCORE, START_SCORE = 300, 900, 600


def clamp(score: int) -> int:
    return max(MIN_SCORE, min(MAX_SCORE, score))


def band(score: int) -> str:
    if score >= 800:
        return "Excellent"
    if score >= 700:
        return "Strong"
    if score >= 550:
        return "Good"
    return "Building"


def rewards(score: int) -> list[str]:
    out = []
    if score >= 700:
        out.append("Higher limits at all Paytm stores")
    if score >= 750:
        out.append("Partner offer: 2% cashback on groceries")
    return out


def apply_delta(s: Session, customer_id: str, delta: int, reason: str, ref: str | None = None,
                store_id: str | None = None) -> int | None:
    """Change a customer's score (clamped) and log it. With `ref`, a (reason, ref) pair applies once.

    Returns the applied delta, or None if it was a duplicate.
    """
    if ref is not None and s.exec(select(ScoreEvent.id).where(
            ScoreEvent.customer_id == customer_id, ScoreEvent.reason == reason, ScoreEvent.ref == ref)).first():
        return None
    c = s.get(Customer, customer_id)
    before = c.score
    c.score = clamp(before + delta)
    s.add(c)
    s.add(ScoreEvent(customer_id=customer_id, store_id=store_id, delta=c.score - before, score_after=c.score,
                     reason=reason, ref=ref, created_at=clock.now()))
    trace("score", f"{c.name.split()[0]} {before} → {c.score} ({reason})",
          {"customer_id": customer_id, "delta": c.score - before, "reason": reason})
    return c.score - before
