"""
message.py - Unified message type definitions for NeoFish.

All platform adapters translate their native message formats into
UnifiedMessage so the core agent logic stays platform-agnostic.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union


@dataclass
class UnifiedMessage:
    """A platform-agnostic message that flows into the agent."""

    # Which platform this message came from: "web" | "telegram" | "qq"
    platform: str

    # Opaque user identifier on that platform (e.g. Telegram user_id, QQ number)
    user_id: str

    # Unified session ID (UUID) shared across the system
    session_id: str

    # Plain text content of the message
    text: str

    # List of attachments.  Each item is either:
    #   - a (filename, bytes) tuple for binary data received by the platform
    #   - a (filename, str) tuple where str is an HTTP URL or a base64 data-URL
    attachments: List[Tuple[str, Union[bytes, str]]] = field(default_factory=list)

    # ID of the message being replied to, if any (platform-native format)
    reply_to: Optional[str] = None
