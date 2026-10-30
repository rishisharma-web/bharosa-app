"""Core API: events, snapshot, SSE stream, trace, customer pickers (spec 10)."""
import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select
from sse_starlette.sse import EventSourceResponse

from app import clock, db
from app.config import get_settings
from app.core import ledger, score as sc
from app.events.router import EventError, fire
from app.models import Customer, StoreCustomer
from app.realtime import broadcaster, trace as tr
from app.realtime.snapshot import build_snapshot

router = APIRouter(prefix="/api")


class EventIn(BaseModel):
    type: str
    payload: dict[str, Any] = {}


@router.post("/events")
async def post_event(body: EventIn):
    try:
        return await fire(body.type, body.payload)
    except EventError as e:
        raise HTTPException(status_code=e.status, detail=e.message)


@router.get("/snapshot")
def get_snapshot():
    with db.session() as s:
        return build_snapshot(s)


@router.get("/stream")
async def stream(request: Request):
    q = broadcaster.subscribe()

    async def gen():
        try:
            with db.session() as s:
                first = [{"type": "snapshot", "data": build_snapshot(s)}]
                first += [{"type": "trace", "data": ln} for ln in tr.recent(s, 30)]
            for msg in first:
                yield {"data": json.dumps(msg, ensure_ascii=False)}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=10)
                except asyncio.TimeoutError:
                    continue
                yield {"data": json.dumps(msg, ensure_ascii=False)}
        finally:
            broadcaster.unsubscribe(q)

    return EventSourceResponse(gen(), ping=15)


@router.get("/trace")
def get_trace(limit: int = 100):
    with db.session() as s:
        return tr.recent(s, min(max(limit, 1), 500))


@router.get("/customers")
def list_customers(store_id: str = "S1"):
    today = clock.today()
    with db.session() as s:
        rows = s.exec(select(Customer).join(StoreCustomer, StoreCustomer.customer_id == Customer.id)
                      .where(StoreCustomer.store_id == store_id).order_by(Customer.name)).all()
        per = ledger.totals_by_customer(ledger.open_entries(s, store_id), today)
        return [
            {"id": c.id, "name": c.name, "score": c.score, "score_band": sc.band(c.score),
             "outstanding": per[c.id].outstanding if c.id in per else 0,
             "overdue_days": per[c.id].oldest_overdue_days if c.id in per else 0}
            for c in rows
        ]


@router.get("/health")
def health():
    ok_db = True
    try:
        with db.session() as s:
            s.exec(select(Customer.id).limit(1)).all()
    except Exception:
        ok_db = False
    settings = get_settings()
    return {
        "ok": ok_db,
        "llm_mode": settings.llm_mode,
        "sarvam_configured": bool(settings.sarvam_api_key),
        "sarvam_reachable": None,  # probed once the LLM gateway lands
        "db": settings.db_path if ok_db else "unavailable",
        "sim_now": clock.iso(clock.now()),
    }
