"""Demo and admin endpoints (spec 10)."""
from fastapi import APIRouter, HTTPException

from app.errors import EventError
from app.sim import demo_script

router = APIRouter(prefix="/api/demo")


@router.post("/reset")
async def reset():
    return {"ok": True, **(await demo_script.reset())}


@router.get("/script")
def script():
    return demo_script.script()


@router.post("/next")
async def next_beat(fast: bool = False):
    """Run the next beat (or finish the current one's presenter steps). Returns the caption."""
    try:
        return await demo_script.next_beat(fast=fast)
    except EventError as e:
        raise HTTPException(e.status, e.message)


@router.post("/goto/{beat}")
async def goto(beat: int):
    """Reset, then run beats up to N (for rehearsal)."""
    try:
        return await demo_script.goto(beat)
    except EventError as e:
        raise HTTPException(e.status, e.message)
