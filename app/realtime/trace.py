"""Trace lines: one per system step, shown live in the UI and used to light the architecture SVG.

`trace()` only buffers. The event router (or `app.events.router.unit_of_work`) drains the
buffer, writes the rows in the same transaction as the state change, and broadcasts them.
Node ids must match the SVG ids listed in spec 11.9.
"""
from typing import Any

from sqlmodel import Session, select

from app import clock
from app.models import Trace

NODES = {
    "soundbox", "merchant_app", "customer_app", "router", "counter_agent", "recovery_agent",
    "recon_agent", "munim_agent", "validator", "ledger", "risk", "reconcile", "mandate",
    "forecast", "advance", "integrity", "score", "llm", "tts", "upi", "lender", "distributor",
    "db", "broadcaster",
}

_pending: list[dict] = []


def trace(node: str, label: str, detail: Any = None, ms: float | None = None, source: str | None = None) -> dict:
    assert node in NODES, f"unknown trace node {node!r}"
    line = {
        "ts": clock.iso(clock.now()),
        "node": node,
        "label": label,
        "detail": detail,
        "ms": None if ms is None else round(ms, 2),
        "source": source,
    }
    _pending.append(line)
    return line


def drain() -> list[dict]:
    lines = list(_pending)
    _pending.clear()
    return lines


def persist(s: Session, lines: list[dict]) -> None:
    for ln in lines:
        s.add(Trace(ts=clock.now(), node=ln["node"], label=ln["label"], detail=ln["detail"],
                    ms=ln["ms"], source=ln["source"]))


def recent(s: Session, limit: int = 30) -> list[dict]:
    rows = s.exec(select(Trace).order_by(Trace.id.desc()).limit(limit)).all()
    return [
        {"ts": clock.iso(r.ts), "node": r.node, "label": r.label, "detail": r.detail, "ms": r.ms, "source": r.source}
        for r in reversed(rows)
    ]
