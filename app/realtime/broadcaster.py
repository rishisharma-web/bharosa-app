"""Fan-out of SSE messages to every connected browser.

Message shapes (spec 10.1): {"type": "snapshot"|"trace"|"audio"|"notify"|"caption"|"toast", "data": {...}}
"""
import asyncio
from typing import Any

_subscribers: set[asyncio.Queue] = set()


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def subscriber_count() -> int:
    return len(_subscribers)


def publish(messages: list[dict[str, Any]]) -> None:
    for q in list(_subscribers):
        for m in messages:
            try:
                q.put_nowait(m)
            except asyncio.QueueFull:  # a stalled tab; drop it, EventSource will reconnect
                _subscribers.discard(q)
                break
