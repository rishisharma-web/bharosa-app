"""Event router (spec 7.1): validate → persist → dispatch → commit → broadcast.

All writes in the app go through `unit_of_work()`, which holds one global asyncio lock,
so handlers run strictly one after another. A handler may emit child events (e.g. the
Counter Agent turning one sentence into two actions); children run inside the same
transaction and are persisted with `parent_id`, so the event log stays replayable.
"""
import asyncio
import inspect
import time
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from app import clock, db
from app.config import get_settings
from app.errors import EventError  # noqa: F401  (re-exported for handlers and routes)
from app.events.effects import Effect, toast
from app.events.schemas import NO_TICK, SCHEMAS
from app.models import Event
from app.realtime import broadcaster, trace as tr

LOCK = asyncio.Lock()

Handler = Callable[["UnitOfWork", Any], "list[Effect] | None | Awaitable[list[Effect] | None]"]
HANDLERS: dict[str, Handler] = {}
# Housekeeping that must see the current sim time before any top-level event is handled
# (e.g. lazily expiring confirm tokens). Hooks take the UnitOfWork.
BEFORE_EACH: list[Callable[["UnitOfWork"], None]] = []


def before_each(fn):
    BEFORE_EACH.append(fn)
    return fn


# Run inside the transaction just before it commits (e.g. the demo script noticing that the
# presenter has already done the step it was waiting for). Hooks take the UnitOfWork.
BEFORE_COMMIT: list[Callable[["UnitOfWork"], None]] = []


def before_commit(fn):
    BEFORE_COMMIT.append(fn)
    return fn


def handles(event_type: str):
    assert event_type in SCHEMAS, event_type

    def deco(fn: Handler) -> Handler:
        HANDLERS[event_type] = fn
        return fn

    return deco


class UnitOfWork:
    def __init__(self, s: Session):
        self.s = s
        self.effects: list[Effect] = []
        self.event_ids: list[int] = []
        self._parents: list[int] = []

    @property
    def event_id(self) -> int | None:
        return self._parents[-1] if self._parents else None

    @property
    def nested(self) -> bool:
        """True while handling a child event (e.g. a salary sweep inside advance_day)."""
        return len(self._parents) > 1

    async def emit(self, event_type: str, payload: BaseModel | dict) -> int:
        """Persist and handle one event inside the current transaction. Returns its id."""
        model = validate(event_type, payload) if isinstance(payload, dict) else payload
        handler = HANDLERS.get(event_type)
        if handler is None:
            raise EventError(f"event type '{event_type}' is not implemented yet", 501)

        if event_type not in NO_TICK:
            clock.tick(get_settings().event_tick_s)
        if not self._parents:
            for hook in BEFORE_EACH:
                hook(self)
        ev = Event(ts=clock.now(), type=event_type, payload=model.model_dump(mode="json"), parent_id=self.event_id)
        self.s.add(ev)
        self.s.flush()
        self.event_ids.append(ev.id)

        self._parents.append(ev.id)
        t0 = time.perf_counter()
        try:
            out = handler(self, model)
            if inspect.isawaitable(out):
                out = await out
        finally:
            self._parents.pop()
        tr.trace("router", event_type, {"event_id": ev.id}, ms=(time.perf_counter() - t0) * 1000)
        if out:
            self.effects.extend(out)
        return ev.id


def validate(event_type: str, payload: dict) -> BaseModel:
    schema = SCHEMAS.get(event_type)
    if schema is None:
        raise EventError(f"unknown event type '{event_type}'", 400)
    try:
        return schema.model_validate(payload or {})
    except ValidationError as e:
        msg = "; ".join(f"{'.'.join(map(str, err['loc'])) or 'payload'}: {err['msg']}" for err in e.errors())
        raise EventError(msg, 422) from e


@asynccontextmanager
async def unit_of_work():
    """One transaction under the global lock; on success broadcasts snapshot + traces + effects."""
    from app.realtime.snapshot import build_snapshot

    async with LOCK:
        t_start = clock.now()
        s = db.session()
        uow = UnitOfWork(s)
        try:
            yield uow
            for hook in BEFORE_COMMIT:
                hook(uow)
            clock.persist(s)
            lines = tr.drain()
            tr.persist(s, lines)
            s.commit()
        except Exception as e:
            s.rollback()
            tr.drain()
            clock.set(t_start)
            _record_failure(e)
            raise
        finally:
            s.close()

        tr.trace("broadcaster", "snapshot", {"clients": broadcaster.subscriber_count()})
        lines.extend(tr.drain())  # not persisted: purely a UI breadcrumb
        with db.session() as rs:
            snap = build_snapshot(rs)
        broadcaster.publish(
            [{"type": "snapshot", "data": snap}]
            + [{"type": "trace", "data": ln} for ln in lines]
            + [eff.message() for eff in uow.effects]
        )


def _record_failure(e: Exception) -> None:
    msg = e.message if isinstance(e, EventError) else f"{type(e).__name__}: {e}"
    line = tr.trace("router", "error", {"error": msg})
    tr.drain()
    try:
        with db.session() as s:
            tr.persist(s, [line])
            s.commit()
    except Exception:  # never mask the original error
        pass
    level = "warn" if isinstance(e, EventError) and e.status < 500 else "error"
    broadcaster.publish([{"type": "trace", "data": line}, toast(msg, level).message()])


async def fire(event_type: str, payload: dict | None) -> dict:
    """Entry point for POST /api/events and for the demo script."""
    model = validate(event_type, payload or {})
    async with unit_of_work() as uow:
        event_id = await uow.emit(event_type, model)
    return {
        "ok": True,
        "event_id": event_id,
        "child_event_ids": uow.event_ids[1:],
        "effects_summary": [e.type for e in uow.effects],
    }
