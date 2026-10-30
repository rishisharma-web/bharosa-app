"""Overview (pitch page) data: the notebook vs Bharosa comparison (spec 11.5)."""
from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.sim import compare

router = APIRouter(prefix="/api/overview")


@router.get("/compare")
async def get_compare():
    return await run_in_threadpool(compare.cached)
