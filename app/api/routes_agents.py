"""Agent endpoints (spec 10): Ask Munim, and the recovery threads for the Collect screen."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from app import clock, db, state
from app.agents import munim
from app.events.router import EventError, unit_of_work
from app.models import Message

router = APIRouter(prefix="/api")


class AskIn(BaseModel):
    store_id: str = "S1"
    question: str = Field(min_length=1, max_length=300)
    lang: str | None = None


@router.post("/agents/munim/ask")
async def ask_munim(body: AskIn):
    """Read-only tools; runs under the event lock so its trace lines broadcast in order."""
    try:
        async with unit_of_work() as uow:
            return await munim.ask(uow.s, body.store_id, body.question, body.lang or state.get(uow.s, "lang"))
    except EventError as e:
        raise HTTPException(e.status, e.message)


@router.get("/messages")
def messages(store_id: str = "S1", customer_id: str | None = None):
    """Merchant view of recovery threads at this store (drafts included)."""
    with db.session() as s:
        q = select(Message).where(Message.store_id == store_id)
        if customer_id:
            q = q.where(Message.customer_id == customer_id)
        rows = s.exec(q.order_by(Message.created_at, Message.id)).all()
        return [{"id": m.id, "customer_id": m.customer_id, "direction": m.direction, "text": m.text, "lang": m.lang,
                 "status": m.status, "ts": clock.iso(m.created_at), "agent": m.agent_output} for m in rows]
