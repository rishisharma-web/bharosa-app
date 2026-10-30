"""Soundbox adapter (spec 7.12). Simulated: the browser renders the device from snapshot state.

Production equivalent: Paytm's device platform pushing the top display, the
customer-facing front screen and audio (ASSUMPTION: event contract proposed by us).
"""
from sqlmodel import Session

from app import state
from app.events.effects import Effect, audio
from app.realtime.trace import trace

IDLE_FRONT = {"mode": "idle"}


def current(s: Session) -> dict:
    return dict(state.get(s, "soundbox"))


def display(s: Session, store_id: str, *, top: dict | None = None, front: dict | None = None,
            last_alert: str | None = None) -> None:
    sb = current(s)
    sb["store_id"] = store_id
    if top is not None:
        sb["top"] = top
    if front is not None:
        sb["front"] = front
    if last_alert is not None:
        sb["last_alert"] = last_alert
    state.put(s, "soundbox", sb)
    if top is not None:
        trace("soundbox", f"Top display: {top.get('band', '')} · {top.get('text', '')[:60]}")
    if front is not None:
        trace("soundbox", f"Front screen: {front.get('mode')}")


def clear_front_if_showing(s: Session, entry_id: int, replacement: dict | None = None) -> None:
    sb = current(s)
    if (sb.get("front") or {}).get("entry_id") == entry_id:
        display(s, sb.get("store_id", "S1"), front=replacement or IDLE_FRONT)


def play(store_id: str, text: str, lang: str, kind: str = "alert") -> Effect:
    """Queue speech for the device. The TTS adapter fills `url` once it exists; text is always shown.
    `kind` lets the UI treat the long morning briefing differently from short alerts."""
    trace("soundbox", f"Speak ({lang}): {text[:50]}")
    return audio(f"soundbox:{store_id}", text, lang, url=None, kind=kind)
