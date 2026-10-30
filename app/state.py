"""Key/value access to the `sim_state` table (lang, focus customer, demo beat, soundbox, briefing)."""
from typing import Any

from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session

from app.models import SimState

DEFAULTS: dict[str, Any] = {
    "lang": "hi-IN",
    "focus_customer": "C_RAMESH",
    "demo_beat": 0,
    "demo_step": 0,
    "demo_last": None,
    "demo_caption": "Morning: Munim briefs Lakshmi Stores in Hindi.",
    "soundbox": {
        "store_id": "S1",
        "top": None,
        "front": {"mode": "idle"},
        "last_alert": None,
    },
    "briefing": None,
}


def get(s: Session, key: str, default: Any = None) -> Any:
    row = s.get(SimState, key)
    if row is not None:
        return row.value
    return DEFAULTS.get(key, default)


def put(s: Session, key: str, value: Any) -> None:
    row = s.get(SimState, key)
    if row is None:
        s.add(SimState(key=key, value=value))
    else:
        row.value = value
        flag_modified(row, "value")  # callers may pass back a mutated copy of the same dict
        s.add(row)
