"""Activity log (v2 spec §4.12): one plain-English line per decision, with its source
(rule, ai or template). Shown on the presenter screen and in the merchant app."""
from sqlmodel import Session, select

from app.config import now
from app.models import Activity

KINDS = {"guardrail", "confirm", "payment", "advance", "growth", "ai", "integrity", "message"}


def log(s: Session, store_id: str | None, kind: str, text: str, source: str = "rule") -> None:
    assert kind in KINDS, kind
    s.add(Activity(ts=now(), store_id=store_id, kind=kind, text=text, source=source))


def recent(s: Session, store_id: str | None = None, limit: int = 20) -> list[dict]:
    q = select(Activity)
    if store_id:
        q = q.where(Activity.store_id == store_id)
    rows = s.exec(q.order_by(Activity.id.desc()).limit(max(1, min(limit, 100)))).all()
    return [{"ts": r.ts.isoformat(), "kind": r.kind, "text": r.text, "source": r.source} for r in rows]
