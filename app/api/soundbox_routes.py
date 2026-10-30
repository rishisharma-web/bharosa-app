"""AI Soundbox simulator endpoints (v2 spec §7 Soundbox, §5.1–5.2). No login: fixed to store S1."""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import bus
from app.agents import counter
from app.ai import sarvam
from app.auth import SOUNDBOX_STORE as STORE
from app.core import activity, requests as req
from app.errors import EventError
from app.models import Store
from app.seed import PRESETS
from app.voice import spoken_line

router = APIRouter(prefix="/api/soundbox")


class UdhaarIn(BaseModel):
    text: str | None = Field(default=None, max_length=200)
    customer_id: str | None = None
    amount: int | None = Field(default=None, ge=1, le=50_000)


class AcceptIn(BaseModel):
    override: bool = False


@router.get("/presets")
def presets():
    return PRESETS


def _scopes(t: bus.Tx) -> None:
    t.touch(f"soundbox:{STORE}", f"merchant:{STORE}")


@router.get("/state")
async def state():
    async with bus.tx() as t:
        if req.expire_stale(t.s):
            _scopes(t)
        st = req.sb_get(t.s, STORE)
        store = t.s.get(Store, STORE)
    front = dict(st.get("front") or req.IDLE)
    if front.get("token"):
        front["qr_url"] = req.request_url(front["token"])
    return {"store": store.name, "vpa": store.vpa, "top": st.get("top"), "front": front,
            "ai_enabled": sarvam.enabled(), "voice_lang": store.voice_lang}


@router.post("/udhaar")
async def udhaar(body: UdhaarIn):
    async with bus.tx() as t:
        if body.customer_id and body.amount:
            cid, amount, source = body.customer_id, body.amount, "rule"
        elif body.text:
            parsed = await counter.parse(t.s, STORE, body.text)
            if "error" in parsed:
                raise EventError(parsed["error"], 422)
            cid, amount, source = parsed["customer_id"], parsed["amount"], parsed["source"]
            if source == "ai":
                activity.log(t.s, STORE, "ai", f"Counter Agent understood “{body.text}”", "ai")
        else:
            raise EventError("Say a name and an amount, e.g. a preset", 422)
        top = req.udhaar(t.s, STORE, cid, amount)
        _scopes(t)
        t.touch(f"customer:{cid}")  # a share request may now be waiting in their app
        await spoken_line(t, STORE, top["text"], translate=True)
    return top


@router.post("/accept")
async def accept(body: AcceptIn):
    async with bus.tx() as t:
        out = req.accept(t.s, STORE, body.override)
        _scopes(t)
        t.touch(f"customer:{out['customer_id']}")  # the confirm request now waits in their app
    return out


@router.post("/clear")
async def clear():
    async with bus.tx() as t:
        cid = req.clear(t.s, STORE)
        _scopes(t)
        if cid:
            t.touch(f"customer:{cid}")
    return {"ok": True}

