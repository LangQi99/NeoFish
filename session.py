"""
session.py - Cross-platform session management for NeoFish.

Maps (platform, platform_chat_id) pairs to unified session UUIDs so that
the same conversation thread is maintained regardless of the originating
platform.

Also manages message queues for each session to handle incoming messages
while an agent is running.

Note: This class is asyncio-safe for single-threaded event-loop use.
Concurrent calls from multiple threads are not supported.

Usage::

    from session import SessionStore

    store = SessionStore()
    sid = store.get_or_create("telegram", "chat_789")  # creates if absent
    sid2 = store.get_or_create("telegram", "chat_789") # returns same sid
    sid3 = store.get_or_create("qq", "group_123456")   # different session

    # Reverse lookup: find the chat_id for a session
    chat_id = store.get_chat_id("telegram", sid)

    # Message queue for session
    queue = store.get_queue(sid)
    await queue.put("new message")

    # Running state
    if not store.is_running(sid):
        store.set_running(sid, True)
        # ... run agent ...
        store.set_running(sid, False)
"""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Optional


# Persist the mapping alongside the regular sessions file by default.
_DEFAULT_MAP_FILE = Path("platform_sessions.json")


class SessionStore:
    """Mapping of platform chats to session UUIDs with bidirectional lookup.

    Also manages per-session message queues and running state for proper
    handling of incoming messages while an agent is executing.
    """

    def __init__(self, map_file: Optional[Path] = None):
        self._file = map_file or _DEFAULT_MAP_FILE
        # Forward map: "(platform, chat_id)" -> session_uuid
        self._map: dict[str, str] = {}
        # Reverse map: "(platform, session_uuid)" -> chat_id
        self._reverse: dict[str, str] = {}
        # Message queues: session_uuid -> asyncio.Queue
        self._queues: dict[str, asyncio.Queue] = {}
        # Running state: session_uuids that have an active agent loop
        self._running: set[str] = set()
        self._start_locks: dict[str, asyncio.Lock] = {}
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text(encoding="utf-8"))
                self._map = data.get("forward", {})
                self._reverse = data.get("reverse", {})
                return
            except Exception:
                pass
        self._map = {}
        self._reverse = {}

    def _save(self) -> None:
        self._file.write_text(
            json.dumps(
                {"forward": self._map, "reverse": self._reverse},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _fwd_key(platform: str, chat_id: str) -> str:
        return f"{platform}:{chat_id}"

    @staticmethod
    def _rev_key(platform: str, session_id: str) -> str:
        return f"{platform}:{session_id}"

    # ── Public API ───────────────────────────────────────────────────────────

    def get(self, platform: str, chat_id: str) -> Optional[str]:
        """Return the session UUID for this platform chat, or *None*."""
        return self._map.get(self._fwd_key(platform, chat_id))

    def get_chat_id(self, platform: str, session_id: str) -> Optional[str]:
        """Return the platform chat_id for a given session UUID, or *None*."""
        return self._reverse.get(self._rev_key(platform, session_id))

    def reverse_lookup(self, session_id: str) -> tuple[str, str] | None:
        """根据 session_id 反查其所属平台和 chat_id。

        Returns (platform, chat_id) or None.
        """
        for rev_key, chat_id in self._reverse.items():
            if rev_key.endswith(f":{session_id}"):
                platform = rev_key.rsplit(":", 1)[0]
                return platform, chat_id
        if session_id in self._queues:
            return "web", session_id
        return None

    def get_or_create(self, platform: str, chat_id: str) -> str:
        """Return existing session UUID, or create and persist a new one."""
        fwd = self._fwd_key(platform, chat_id)
        if fwd not in self._map:
            session_id = str(uuid.uuid4())
            self._map[fwd] = session_id
            self._reverse[self._rev_key(platform, session_id)] = chat_id
            self._save()
        return self._map[fwd]

    def set(self, platform: str, chat_id: str, session_id: str) -> None:
        """Explicitly bind a platform chat to an existing session UUID."""
        self._map[self._fwd_key(platform, chat_id)] = session_id
        self._reverse[self._rev_key(platform, session_id)] = chat_id
        self._save()

    def remove(self, platform: str, chat_id: str) -> None:
        """Remove the mapping for this platform chat."""
        fwd = self._fwd_key(platform, chat_id)
        if fwd in self._map:
            session_id = self._map.pop(fwd)
            self._reverse.pop(self._rev_key(platform, session_id), None)
            # Also clean up queue if exists
            self._queues.pop(session_id, None)
            self._running.discard(session_id)
            self._save()

    def all_sessions(self) -> dict[str, str]:
        """Return a copy of the full forward mapping dict."""
        return dict(self._map)

    # ── Message Queue API ─────────────────────────────────────────────────────

    def get_queue(self, session_id: str) -> asyncio.Queue:
        """Get or create the message queue for a session."""
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue()
        return self._queues[session_id]

    def is_running(self, session_id: str) -> bool:
        """Check if an agent loop is currently running for this session."""
        return session_id in self._running

    def set_running(self, session_id: str, running: bool) -> None:
        """Set the running state for a session."""
        if running:
            self._running.add(session_id)
        else:
            self._running.discard(session_id)

    def _get_start_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._start_locks:
            self._start_locks[session_id] = asyncio.Lock()
        return self._start_locks[session_id]

    async def try_start(self, session_id: str) -> bool:
        """Atomically claim the agent slot for *session_id*.

        Returns True if this caller won the slot and should start the agent.
        Returns False if another agent is already running for this session.
        """
        lock = self._get_start_lock(session_id)
        async with lock:
            if session_id in self._running:
                return False
            self._running.add(session_id)
            return True

    async def enqueue_message(self, session_id: str, text: str, images: list = None) -> None:
        """Put a message into the session's queue.

        Parameters
        ----------
        session_id:
            The session UUID.
        text:
            Message text content.
        images:
            Optional list of image data URLs.
        """
        queue = self.get_queue(session_id)
        await queue.put({
            "text": text,
            "images": images or [],
        })

    def drain_queue_nowait(self, session_id: str) -> list:
        """Drain all pending messages from the queue (non-blocking).

        Returns a list of {"text": ..., "images": ...} dicts.
        """
        queue = self._queues.get(session_id)
        if queue is None:
            return []

        messages = []
        while not queue.empty():
            try:
                messages.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return messages


# Module-level singleton for convenience
session_store = SessionStore()
