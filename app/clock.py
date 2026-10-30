"""Simulated clock. Every module reads time only from here.

The current time is held in memory and persisted to `sim_state.sim_now` by whoever
commits the surrounding transaction (`persist`). Keeping writes inside the caller's
session avoids a second SQLite writer while an event is being handled.
"""
from datetime import date, datetime, timedelta, timezone

from sqlmodel import Session

IST = timezone(timedelta(hours=5, minutes=30))
DEMO_START = datetime(2026, 10, 26, 9, 0, 0)

_now: datetime = DEMO_START


def now() -> datetime:
    return _now


def today() -> date:
    return _now.date()


def set(dt: datetime) -> None:  # noqa: A001  (spec name)
    global _now
    _now = dt.replace(microsecond=0, tzinfo=None)


def tick(seconds: int) -> None:
    set(_now + timedelta(seconds=seconds))


def advance_days(n: int) -> None:
    set(_now + timedelta(days=n))


def advance_to(dt: datetime) -> None:
    if dt > _now:
        set(dt)


def datetime_floor(d: date) -> datetime:
    """Midnight at the start of a sim date."""
    return datetime(d.year, d.month, d.day)


def iso(dt: datetime | date | None) -> str | None:
    """Serialise a sim datetime as an ISO string with the IST offset."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.replace(tzinfo=IST).isoformat()
    return dt.isoformat()


def load(s: Session) -> None:
    from app import state

    raw = state.get(s, "sim_now")
    set(datetime.fromisoformat(raw).replace(tzinfo=None) if raw else DEMO_START)


def persist(s: Session) -> None:
    from app import state

    state.put(s, "sim_now", iso(_now))
