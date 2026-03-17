"""
session.py - Cross-platform session management for NeoFish.

Maps (platform, platform_chat_id) pairs to unified session UUIDs so that
the same conversation thread is maintained regardless of the originating
platform.

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
"""

import json
import uuid
from pathlib import Path
from typing import Optional

# Persist the mapping alongside the regular sessions file by default.
_DEFAULT_MAP_FILE = Path("platform_sessions.json")


class SessionStore:
    """Mapping of platform chats to session UUIDs with bidirectional lookup."""

    def __init__(self, map_file: Optional[Path] = None):
        self._file = map_file or _DEFAULT_MAP_FILE
        # Forward map: "(platform, chat_id)" -> session_uuid
        self._map: dict[str, str] = {}
        # Reverse map: "(platform, session_uuid)" -> chat_id
        self._reverse: dict[str, str] = {}
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
            self._save()

    def all_sessions(self) -> dict[str, str]:
        """Return a copy of the full forward mapping dict."""
        return dict(self._map)


# Module-level singleton for convenience
session_store = SessionStore()
