"""
_agent_runner.py - Shared helper for non-web platform adapters.

Provides ``make_message_handler`` which returns an ``on_message`` callback
suitable for TelegramAdapter and QQAdapter.  Each call creates an independent
closure that shares a single PlaywrightManager instance.
"""

import asyncio
import base64
import logging
from typing import Callable

from message import UnifiedMessage

logger = logging.getLogger(__name__)


def make_message_handler(adapter, pm) -> Callable[[UnifiedMessage], asyncio.coroutines]:
    """
    Return an ``async (UnifiedMessage) -> None`` callback for a platform adapter.

    Parameters
    ----------
    adapter:
        A ``PlatformAdapter`` instance (TelegramAdapter or QQAdapter).
    pm:
        A started ``PlaywrightManager`` instance shared across sessions.
    """

    async def on_message(unified_msg: UnifiedMessage) -> None:
        from agent import run_agent_loop

        async def _send(msg) -> None:
            text = msg.get("message", "") if isinstance(msg, dict) else str(msg)
            await adapter.send_message(unified_msg.session_id, text)

        async def _request_action(reason: str, image: str) -> None:
            await adapter.request_action(unified_msg.session_id, reason, image)

        async def _send_image(description: str, b64_image: str) -> None:
            await adapter.send_message(
                unified_msg.session_id,
                f"[{description}]",
                images=[b64_image],
            )

        images = []
        for _fname, data in unified_msg.attachments:
            if isinstance(data, bytes):
                images.append("data:image/jpeg;base64," + base64.b64encode(data).decode())
            else:
                images.append(data)

        await run_agent_loop(
            pm,
            unified_msg.text,
            _send,
            _request_action,
            _send_image,
            images=images,
        )

    return on_message
