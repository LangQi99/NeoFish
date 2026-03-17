"""
platforms/base.py - Abstract base class for all NeoFish platform adapters.

Every platform (Web, Telegram, QQ, …) must implement PlatformAdapter so the
core agent logic can interact with any platform through a single, consistent
interface.

Lifecycle
---------
1. Instantiate the adapter and assign an ``on_message`` callback.
2. Call ``await adapter.start()`` to begin receiving messages.
3. The adapter invokes ``on_message(unified_msg)`` for each incoming message.
4. The agent calls ``send_message`` / ``request_action`` to respond.
5. Call ``await adapter.stop()`` for graceful shutdown.
"""

from abc import ABC, abstractmethod
from typing import Awaitable, Callable, List, Optional

from message import UnifiedMessage


class PlatformAdapter(ABC):
    """Abstract platform adapter — subclass for each messaging platform."""

    def __init__(self) -> None:
        # Assigned by the caller before start().
        self.on_message: Optional[Callable[[UnifiedMessage], Awaitable[None]]] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @abstractmethod
    async def start(self) -> None:
        """Start the platform listener (connect, poll, serve, …)."""

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully shut down the platform listener."""

    # ── Outgoing messages ─────────────────────────────────────────────────────

    @abstractmethod
    async def send_message(
        self,
        session_id: str,
        text: str,
        images: Optional[List[str]] = None,
    ) -> None:
        """
        Send a text (and optional images) reply back to the user.

        Parameters
        ----------
        session_id:
            Unified session UUID that identifies the conversation.
        text:
            Plain text content to send.
        images:
            Optional list of base64-encoded PNG/JPEG strings or HTTP URLs.
        """

    @abstractmethod
    async def request_action(
        self,
        session_id: str,
        reason: str,
        image: Optional[str] = None,
    ) -> None:
        """
        Notify the user that human intervention is required.

        Parameters
        ----------
        session_id:
            Unified session UUID.
        reason:
            Human-readable explanation of what action is needed.
        image:
            Optional base64-encoded screenshot providing context.
        """
