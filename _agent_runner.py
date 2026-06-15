"""
_agent_runner.py - Shared helper for non-web platform adapters.

Provides ``make_message_handler`` which returns an ``on_message`` callback
suitable for TelegramAdapter.  Each call creates an independent
closure that shares a single PlaywrightManager instance.

Handles message queuing when an agent is already running for a session.
Handles file uploads from users to the workspace.
"""

import asyncio
import base64
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Callable

from config import QQ_QUIET_MODE
from message import UnifiedMessage
from session import SessionStore

logger = logging.getLogger(__name__)

_QUIET_QQ_MESSAGE_KEYS = {
    "common.connected_ws",
    "common.context_compressing",
    "common.manual_compressing",
    "common.agent_resumed",
    "common.sent_resume",
    "common.message_queued",
    "common.agent_starting",
    "common.agent_thinking",
    "common.executing_action",
    "common.takeover_browser_opened",
    "common.takeover_ended_message",
    "common.agent_paused_for_takeover",
}

_QUIET_QQ_TEXT_PREFIXES = (
    "Connected to NeoFish Agent WebSocket",
    "Agent is thinking",
    "Agent starting task:",
    "Executing action:",
    "[Takeover]",
    "[Takeover Ended]",
)

_QUIET_QQ_TEXT_SNIPPETS = (
    "Context threshold reached",
    "Manual compression triggered",
    "已发送继续执行",
    "Agent paused for manual takeover",
)


def _should_suppress_message_for_platform(msg, platform: str) -> bool:
    """Return True for routine progress messages hidden in quiet QQ mode."""
    if platform != "qq" or not QQ_QUIET_MODE:
        return False

    if isinstance(msg, dict):
        if msg.get("message_key") in _QUIET_QQ_MESSAGE_KEYS:
            return True
        text = str(msg.get("message", ""))
    else:
        text = str(msg)

    if not text:
        return False

    return any(text.startswith(prefix) for prefix in _QUIET_QQ_TEXT_PREFIXES) or any(
        snippet in text for snippet in _QUIET_QQ_TEXT_SNIPPETS
    )


def make_message_handler(adapter, pm, session_store: SessionStore, workdir: Path = None, scheduler_service=None) -> Callable:
    """
    Return an ``async (UnifiedMessage) -> None`` callback for a platform adapter.

    If an agent is already running for the session, the message is queued and
    will be processed in the next agent loop iteration. Otherwise, starts a new
    agent loop.

    Parameters
    ----------
    adapter:
        A ``PlatformAdapter`` instance (TelegramAdapter).
    pm:
        A started ``PlaywrightManager`` instance shared across sessions.
    session_store:
        The shared ``SessionStore`` instance for queue and state management.
    workdir:
        The workspace directory for saving uploaded files.
    """

    uploads_dir = (workdir or Path("./workspace")).resolve() / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    async def on_message(unified_msg: UnifiedMessage) -> None:
        from agent import run_agent_loop

        session_id = unified_msg.session_id

        # Convert attachments to data URLs and save files
        images = []
        uploaded_files = []

        for filename, data in unified_msg.attachments:
            try:
                if isinstance(data, bytes):
                    # Binary data - save to uploads directory
                    safe_name = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
                    filepath = uploads_dir / safe_name
                    filepath.write_bytes(data)
                    uploaded_files.append(str(filepath))
                    logger.info("Saved uploaded file: %s", filepath)

                    # Check if it's an image - add to images for vision
                    ext = filename.lower().split(".")[-1] if "." in filename else ""
                    if ext in ("jpg", "jpeg", "png", "gif", "webp"):
                        images.append("data:image/jpeg;base64," + base64.b64encode(data).decode())

                elif isinstance(data, str):
                    # URL or data URL
                    if data.startswith("data:"):
                        # Data URL - save to file
                        try:
                            header, b64_part = data.split(",", 1)
                            media_type = header.split(":")[1].split(";")[0]
                            ext = media_type.split("/")[1] if "/" in media_type else "bin"
                            safe_name = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}.{ext}"
                            filepath = uploads_dir / safe_name
                            filepath.write_bytes(base64.b64decode(b64_part))
                            uploaded_files.append(str(filepath))

                            if ext in ("jpg", "jpeg", "png", "gif", "webp"):
                                images.append(data)
                        except Exception as e:
                            logger.warning("Failed to save data URL: %s", e)
                            images.append(data)  # Still pass to vision
                    elif data.startswith(("http://", "https://")):
                        # HTTP URL - download and save
                        try:
                            import aiohttp
                            async with aiohttp.ClientSession() as session:
                                async with session.get(data) as resp:
                                    if resp.status == 200:
                                        file_bytes = await resp.read()
                                        ext = data.split(".")[-1].split("?")[0] if "." in data else "bin"
                                        safe_name = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}.{ext}"
                                        filepath = uploads_dir / safe_name
                                        filepath.write_bytes(file_bytes)
                                        uploaded_files.append(str(filepath))

                                        if ext in ("jpg", "jpeg", "png", "gif", "webp"):
                                            images.append("data:image/jpeg;base64," + base64.b64encode(file_bytes).decode())
                        except Exception as e:
                            logger.warning("Failed to download URL: %s", e)
            except Exception as e:
                logger.error("Failed to process attachment %s: %s", filename, e)

        # Atomically check if agent is running AND claim the slot.
        # This prevents the race condition where multiple incoming messages
        # all pass is_running() before any calls set_running().
        if not await session_store.try_start(session_id):
            logger.info("Agent running for session %s, queuing message", session_id)
            await session_store.enqueue_message(session_id, unified_msg.text, images)
            if pm.is_waiting_for_human(session_id):
                logger.info(
                    "Session %s is waiting for human — signalling resume", session_id
                )
                pm.signal_resume(session_id)
            return

        try:
            async def _send(msg) -> None:
                if _should_suppress_message_for_platform(msg, unified_msg.platform):
                    return
                text = msg.get("message", "") if isinstance(msg, dict) else str(msg)
                await adapter.send_message(session_id, text)

            async def _request_action(reason: str, image: str) -> None:
                await adapter.request_action(session_id, reason, image)

            async def _send_image(description: str, b64_image: str) -> None:
                await adapter.send_message(
                    session_id,
                    f"[{description}]",
                    images=[b64_image],
                )

            async def _send_file(file_path: str, description: str) -> None:
                await adapter.send_file(session_id, file_path, description)

            await run_agent_loop(
                pm,
                unified_msg.text,
                _send,
                _request_action,
                _send_image,
                _send_file,
                images=images,
                session_store=session_store,
                session_id=session_id,
                uploaded_files=uploaded_files,
                scheduler_service=scheduler_service,
                source_meta={
                    "session_id": session_id,
                    "chat_id": unified_msg.user_id,
                    "platform": unified_msg.platform,
                },
            )
        finally:
            session_store.set_running(session_id, False)

    return on_message
