"""Demo and admin endpoints (spec 10)."""
from fastapi import APIRouter, HTTPException

from app import db
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
async def next_step(fast: bool = False):
    """One step: run the next step and return its explanation (or enter the next beat)."""
    try:
        return await demo_script.next_step(fast=fast)
    except EventError as e:
        raise HTTPException(e.status, e.message)


@router.post("/run_beat")
async def run_beat(fast: bool = False):
    """Run the rest of the current beat (or the whole next beat) without pausing between steps."""
    try:
        return await demo_script.run_beat(fast=fast)
    except EventError as e:
        raise HTTPException(e.status, e.message)


@router.get("/status")
def demo_status():
    with db.session() as s:
        return demo_script.status(s)


@router.post("/goto/{beat}")
async def goto(beat: int):
    """Reset, then play every beat before N: the next press of Next enters beat N (rehearsal / ◀)."""
    try:
        return await demo_script.goto(beat)
    except EventError as e:
        raise HTTPException(e.status, e.message)
