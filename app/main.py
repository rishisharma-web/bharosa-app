"""FastAPI app: API routers, static frontend, seed-if-missing on startup."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import select

from app import clock, db
from app.api import routes_agents, routes_core, routes_demo
from app.events import handlers  # noqa: F401  (registers event handlers)
from app.models import Store

STATIC = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.create_all()
    with db.session() as s:
        seeded = s.exec(select(Store.id).limit(1)).first() is not None
    if not seeded:
        from app.sim.seed import seed

        seed()
    with db.session() as s:
        clock.load(s)
    yield


app = FastAPI(title="Bharosa", lifespan=lifespan)
app.include_router(routes_core.router)
app.include_router(routes_demo.router)
app.include_router(routes_agents.router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")
