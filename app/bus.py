"""Writes and real-time pings (v2 spec §8).

Every state change runs inside `tx()`: one global lock, one transaction, then a "changed" ping
listing the scopes that moved (e.g. merchant:S1, customer:C_RAMESH, soundbox:S1). The ping
carries no data, so the stream never leaks one user's data to another; each app refetches its
own view endpoint.
"""
import asyncio
import json
from contextlib import asynccontextmanager

from sqlmodel import Session

from app import db

LOCK = asyncio.Lock()
_subscribers: set[asyncio.Queue] = set()


class Tx:
    def __init__(self, s: Session):
        self.s = s
        self.scopes: set[str] = set()
        self.speak: list[dict] = []  # one short spoken line per event, for the Soundbox page (AI on only)

    def touch(self, *scopes: str) -> None:
        self.scopes.update(scopes)


@asynccontextmanager
async def tx():
    async with LOCK:
        s = db.session()
        t = Tx(s)
        try:
            yield t
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()
    if t.scopes:
        publish({"type": "changed", "scopes": sorted(t.scopes | {"activity"})})
    for line in t.speak:
        publish({"type": "speak", "scopes": [line["scope"]], "text": line["text"], "lang": line["lang"]})


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def publish(msg: dict) -> None:
    data = json.dumps(msg, ensure_ascii=False)
    for q in list(_subscribers):
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            _subscribers.discard(q)
