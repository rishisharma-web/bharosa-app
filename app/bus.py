"""Writes and real-time pings (v2 spec §8).

Every state change runs inside `tx()`: one global lock, one transaction, then a "changed" ping
listing the scopes that moved (e.g. merchant:S1, customer:C_RAMESH, soundbox:S1). The ping
carries no data, so the stream never leaks one user's data to another; each app refetches its
own view endpoint.

Pings go out two ways: the SSE stream (`subscribe`), and a numbered log of recent pings for the
long-poll fallback (`wait_since`), used when a proxy buffers SSE (e.g. a Cloudflare quick tunnel).
"""
import asyncio
import json
from collections import deque
from contextlib import asynccontextmanager

from sqlmodel import Session

from app import db

LOCK = asyncio.Lock()
_subscribers: set[asyncio.Queue] = set()
_seq = 0
_recent: deque[tuple[int, dict]] = deque(maxlen=500)


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
    global _seq
    _seq += 1
    _recent.append((_seq, msg))
    data = json.dumps(msg, ensure_ascii=False)
    for q in list(_subscribers):
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            _subscribers.discard(q)


def since(after: int) -> tuple[int, list[dict], bool]:
    """(latest seq, pings after `after`, reset). reset=True means the caller can't catch up
    (first call, server restarted, or too far behind) and should refetch everything."""
    oldest = _recent[0][0] if _recent else _seq + 1
    if after < 0 or after > _seq or after < oldest - 1:
        return _seq, [], True
    return _seq, [m for n, m in _recent if n > after], False


async def wait_since(after: int, timeout: float) -> tuple[int, list[dict], bool]:
    """Like `since`, but waits up to `timeout` seconds for a new ping when there is none yet."""
    q = subscribe()  # subscribe before checking, so a ping between the two can't be missed
    try:
        seq, items, reset = since(after)
        if items or reset or timeout <= 0:
            return seq, items, reset
        try:
            await asyncio.wait_for(q.get(), timeout)
        except asyncio.TimeoutError:
            pass
        return since(after)
    finally:
        unsubscribe(q)
