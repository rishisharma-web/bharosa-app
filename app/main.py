"""FastAPI app (v2 spec §13): APIs, the five web apps, and seed-if-missing on startup.

    /merchant  /customer  /soundbox  /demo  /overview      the apps
    /c/r/{token}                                             a QR request, opened in the customer app
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import select

from app import db, seed
from app.api import admin_routes, auth_routes, customer_routes, merchant_routes, soundbox_routes, voice_routes
from app.errors import EventError
from app.models import Store

STATIC = Path(__file__).resolve().parent.parent / "static"
APPS = ("merchant", "customer", "soundbox", "demo", "overview")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.create_all()
    with db.session() as s:
        seeded = s.exec(select(Store.id).limit(1)).first() is not None
    if not seeded:
        seed.build()
    yield


app = FastAPI(title="Bharosa", lifespan=lifespan)
for r in (auth_routes, soundbox_routes, customer_routes, merchant_routes, voice_routes, admin_routes):
    app.include_router(r.router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.exception_handler(EventError)
async def event_error(_: Request, e: EventError):
    return JSONResponse({"detail": e.message}, status_code=e.status)


def _page(name: str) -> FileResponse:
    return FileResponse(STATIC / name / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/demo")


@app.get("/c/r/{token}", include_in_schema=False)
def request_link(token: str):
    return _page("customer")


for _name in APPS:
    app.add_api_route(f"/{_name}", (lambda n=_name: _page(n)), include_in_schema=False, methods=["GET"])
