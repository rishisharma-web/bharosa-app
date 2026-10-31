"""Shared and admin endpoints (v2 spec §7 Shared): SSE stream, activity, reset, login QRs, health."""
import asyncio

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlmodel import select
from sse_starlette.sse import EventSourceResponse

from app import auth, bus, db, seed
from app.agents import growth_agent
from app.ai import sarvam
from app.config import get_settings
from app.core import activity, growth
from app.models import Store

router = APIRouter(prefix="/api")


class MagicIn(BaseModel):
    customer_id: str


@router.get("/stream")
async def stream(request: Request):
    """'changed' pings only: {"type": "changed", "scopes": [...]}. Clients refetch their own views."""
    q = bus.subscribe()

    async def gen():
        try:
            yield {"data": '{"type": "hello"}'}
            while not await request.is_disconnected():
                try:
                    yield {"data": await asyncio.wait_for(q.get(), timeout=10)}
                except asyncio.TimeoutError:
                    continue
        finally:
            bus.unsubscribe(q)

    return EventSourceResponse(gen(), ping=15)


@router.get("/changes")
async def changes(after: int = -1, wait: float = 20):
    """Long-poll fallback for /api/stream (same pings, same no-data rule), for proxies that buffer
    SSE, such as a Cloudflare quick tunnel. Returns as soon as a ping newer than `after` exists."""
    seq, events, reset = await bus.wait_since(after, min(max(wait, 0.0), 25.0))
    return JSONResponse({"seq": seq, "reset": reset, "events": events}, headers={"Cache-Control": "no-store"})


@router.get("/activity")
def get_activity(limit: int = 20, bh_merchant: str | None = Cookie(default=None),
                 x_admin_key: str | None = Header(default=None)):
    if x_admin_key:
        auth.admin(x_admin_key)
        store = None
    else:
        store = auth.merchant(bh_merchant).store_id
    with db.session() as s:
        return activity.recent(s, store, limit)


@router.post("/admin/reset", dependencies=[Depends(auth.admin)])
async def reset():
    async with bus.tx() as t:
        out = seed.build()  # rebuilds every table in its own transaction
        t.touch("merchant:S1", "soundbox:S1", *(f"customer:{c.id}" for c in seed.CUSTOMERS))
    await reword_plan()
    return out


async def reword_plan() -> None:
    """With AI on, let the Growth Agent word the plan (validated); otherwise templates stay."""
    if not sarvam.enabled():
        return
    async with bus.tx() as t:
        plan = growth.view(t.s, "S1")
        out = await growth_agent.word_plan(plan)
        if out:
            growth.apply_wording(t.s, "S1", out["wording"])
            activity.log(t.s, "S1", "ai", "Growth Agent worded this week's plan", "ai")
        else:
            activity.log(t.s, "S1", "ai", "Growth plan wording kept as template", "template")
        t.touch("merchant:S1")


@router.post("/admin/magic", dependencies=[Depends(auth.admin)])
def magic(body: MagicIn):
    with db.session() as s:
        url = auth.new_magic(s, body.customer_id)
        s.commit()
    return {"url": url}


@router.get("/admin/customers", dependencies=[Depends(auth.admin)])
def login_customers():
    return [{"customer_id": c.id, "name": c.name, "phone": c.phone} for c in seed.CUSTOMERS]


@router.get("/health")
def health():
    st = get_settings()
    try:
        with db.session() as s:
            s.exec(select(Store.id)).first()
    except Exception:
        raise HTTPException(503, "database unavailable")
    return {"ok": True, "sarvam_enabled": sarvam.enabled(), "demo_date": st.demo_date.isoformat(),
            "public_base_url": st.public_base_url}
