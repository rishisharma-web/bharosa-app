"""Demo and admin endpoints (spec 10). Beat stepping arrives with the demo-script milestone."""
from fastapi import APIRouter

from app.events.effects import caption
from app.events.router import unit_of_work
from app.sim.seed import seed

router = APIRouter(prefix="/api/demo")


@router.post("/reset")
async def reset():
    async with unit_of_work() as uow:
        stats = seed()  # rebuilds tables in its own transaction and resets the sim clock
        uow.effects.append(caption("Demo reset: Mon 26 Oct, 09:00 at Lakshmi Stores."))
    return {"ok": True, **stats}
