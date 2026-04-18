"""
message_center.py - Lightweight message bus and message center for NeoFish.

Provides:
1. In-process async publish/subscribe bus scoped by session_id
2. MessageCenter helper to publish typed events from core logic
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable


@dataclass
class BusEvent:
    session_id: str
    event_type: str
    payload: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


EventHandler = Callable[[BusEvent], Awaitable[None]]


class InMemoryMessageBus:
    """In-process pub/sub bus with per-session producer/consumer workers."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._workers: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._stop_sentinel = object()

    async def _ensure_worker_locked(self, session_id: str) -> None:
        if session_id in self._workers and not self._workers[session_id].done():
            return
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue()
        self._workers[session_id] = asyncio.create_task(
            self._consume_loop(session_id), name=f"msg-bus-{session_id}"
        )

    async def _consume_loop(self, session_id: str) -> None:
        queue = self._queues.get(session_id)
        if queue is None:
            return

        while True:
            item = await queue.get()
            if item is self._stop_sentinel:
                break

            event: BusEvent = item
            async with self._lock:
                handlers = list(self._subscribers.get(session_id, []))

            if not handlers:
                continue

            for handler in handlers:
                try:
                    await handler(event)
                except Exception:
                    # Keep bus resilient: one bad subscriber must not block others.
                    continue

    async def subscribe(self, session_id: str, handler: EventHandler) -> None:
        async with self._lock:
            handlers = self._subscribers.setdefault(session_id, [])
            if handler not in handlers:
                handlers.append(handler)
            await self._ensure_worker_locked(session_id)

    async def unsubscribe(self, session_id: str, handler: EventHandler) -> None:
        worker: asyncio.Task | None = None
        queue: asyncio.Queue | None = None
        async with self._lock:
            handlers = self._subscribers.get(session_id, [])
            if handler in handlers:
                handlers.remove(handler)
            if not handlers and session_id in self._subscribers:
                del self._subscribers[session_id]
                worker = self._workers.pop(session_id, None)
                queue = self._queues.get(session_id)

        if queue is not None:
            await queue.put(self._stop_sentinel)
        if worker is not None:
            try:
                await worker
            except Exception:
                pass
            async with self._lock:
                self._queues.pop(session_id, None)

    async def publish(self, event: BusEvent) -> None:
        queue: asyncio.Queue | None = None
        async with self._lock:
            handlers = self._subscribers.get(event.session_id, [])
            if handlers:
                await self._ensure_worker_locked(event.session_id)
                queue = self._queues.get(event.session_id)

        if not handlers or queue is None:
            return
        await queue.put(event)


message_bus = InMemoryMessageBus()


class MessageCenter:
    """Session-scoped message publisher facade."""

    def __init__(self, session_id: str, bus: InMemoryMessageBus | None = None) -> None:
        self.session_id = session_id
        self.bus = bus or message_bus

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event = BusEvent(
            session_id=self.session_id,
            event_type=event_type,
            payload=payload,
        )
        await self.bus.publish(event)

