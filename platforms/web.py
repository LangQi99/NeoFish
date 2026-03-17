"""
platforms/web.py - WebSocket platform adapter for NeoFish.

Handles the existing browser-based frontend over WebSocket.
The adapter owns a single WebSocket connection; one WebAdapter instance
is created per WS connection inside the FastAPI route handler.
"""

import asyncio
import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from fastapi import WebSocket

from message import UnifiedMessage
from platforms.base import PlatformAdapter

# Prefixes used to tag assistant messages that carry structured data.
_ASSISTANT_MSG_PREFIXES = (
    "[Image] ",
    "[Action Required] ",
    "[Takeover] ",
    "[Takeover Ended] ",
)


class WebAdapter(PlatformAdapter):
    """
    Platform adapter for the browser-based WebSocket frontend.

    One instance is created per active WebSocket connection.  The caller
    (FastAPI route) passes the live WebSocket object and a reference to the
    shared sessions dict so the adapter can persist messages.

    Parameters
    ----------
    websocket:
        The accepted FastAPI WebSocket connection.
    session_id:
        The unified session UUID for this connection.
    sessions:
        The shared in-memory sessions dictionary (mutated in-place).
    save_sessions:
        Callable that flushes *sessions* to disk.
    uploads_dir:
        Directory where user-uploaded files are saved.
    playwright_manager:
        Shared PlaywrightManager instance (used for takeover flow).
    run_agent:
        Coroutine factory – called with ``(pm, message, send_fn,
        request_action_fn, send_image_fn, …)`` to kick off an agent loop.
    """

    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        sessions: dict,
        save_sessions: Callable,
        uploads_dir: Path,
        playwright_manager,
        run_agent: Callable,
    ) -> None:
        super().__init__()
        self._ws = websocket
        self._session_id = session_id
        self._sessions = sessions
        self._save_sessions = save_sessions
        self._uploads_dir = uploads_dir
        self._pm = playwright_manager
        self._run_agent = run_agent

    # ── PlatformAdapter interface ─────────────────────────────────────────────

    async def start(self) -> None:
        """Send the initial "connected" info frame to the client."""
        await self._ws.send_text(json.dumps({
            "type": "info",
            "message": "Connected to NeoFish Agent WebSocket",
            "message_key": "common.connected_ws",
            "session_id": self._session_id,
        }))

    async def stop(self) -> None:
        """No-op: WebSocket lifecycle is managed by FastAPI."""

    async def send_message(
        self,
        session_id: str,
        text: str,
        images: Optional[List[str]] = None,
    ) -> None:
        """Send a plain text (+ optional images) assistant message."""
        packet: dict = {"type": "info", "message": text}
        await self._ws.send_text(json.dumps(packet))
        self._append_message("assistant", text)

    async def request_action(
        self,
        session_id: str,
        reason: str,
        image: Optional[str] = None,
    ) -> None:
        """Notify the frontend that human assistance is required."""
        payload = {"type": "action_required", "reason": reason}
        if image:
            payload["image"] = image
        await self._ws.send_text(json.dumps(payload))
        self._append_message(
            "assistant",
            f"[Action Required] {reason}",
            image_data=image or "",
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _append_message(
        self,
        role: str,
        content: str,
        images: list = None,
        image_data: str = "",
    ) -> None:
        """Append a message to the session store and persist to disk."""
        if images is None:
            images = []
        msg: dict = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "images": images,
        }
        if image_data:
            msg["image_data"] = image_data
        self._sessions[self._session_id]["messages"].append(msg)
        # Auto-title: use the first user message (truncated)
        if role == "user" and not self._sessions[self._session_id]["title"]:
            self._sessions[self._session_id]["title"] = (content or "📷 Image")[:40]
        self._save_sessions()

    async def _send_image(self, description: str, b64_image: str) -> None:
        """Send a screenshot / image frame to the frontend."""
        payload = {
            "type": "image",
            "description": description,
            "image": b64_image,
        }
        await self._ws.send_text(json.dumps(payload))
        self._append_message("assistant", f"[Image] {description}", image_data=b64_image)

    def _build_history(self) -> list:
        """Build the conversation history list for the agent (excludes last msg)."""
        history: list = []
        messages = self._sessions[self._session_id]["messages"]
        for m in messages[:-1]:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "user":
                history.append({"role": "user", "content": content or "(user sent an image)"})
            else:
                clean = content
                for prefix in _ASSISTANT_MSG_PREFIXES:
                    if clean.startswith(prefix):
                        clean = clean[len(prefix):]
                if clean:
                    history.append({"role": "assistant", "content": clean})
        return history

    # ── Message dispatch ──────────────────────────────────────────────────────

    async def handle_message(self, raw: str) -> None:
        """
        Dispatch a raw JSON string received from the WebSocket client.

        This is the main entry-point called by the FastAPI route loop.
        """
        payload = json.loads(raw)
        msg_type = payload.get("type")

        if msg_type == "resume":
            await self._handle_resume()
        elif msg_type == "takeover":
            await self._handle_takeover()
        elif msg_type == "takeover_done":
            self._pm.signal_takeover_done()
        elif msg_type == "user_input":
            await self._handle_user_input(payload)

    async def _handle_resume(self) -> None:
        self._pm.resume_from_human()
        await self._ws.send_text(json.dumps({
            "type": "info",
            "message": "Agent resumed execution.",
            "message_key": "common.agent_resumed",
        }))

    async def _handle_takeover(self) -> None:
        if self._pm.in_takeover:
            await self._ws.send_text(json.dumps({
                "type": "info",
                "message": "Takeover is already in progress.",
                "message_key": "common.takeover_already_active",
            }))
            return

        self._pm.request_pause()

        async def do_takeover() -> None:
            await self._ws.send_text(json.dumps({
                "type": "takeover_started",
                "message": "Browser opened for manual interaction. Close it when you are done.",
                "message_key": "common.takeover_started",
            }))
            self._append_message("assistant", "[Takeover] Browser opened for manual interaction.")

            await self._pm.start_takeover()
            final_url, final_screenshot = await self._pm.wait_for_takeover_complete()
            await self._pm.end_takeover(final_url)

            if not final_screenshot:
                final_screenshot = await self._pm.get_page_screenshot_base64()

            ended_payload: dict = {
                "type": "takeover_ended",
                "message": "Takeover ended. AI is resuming.",
                "message_key": "common.takeover_ended",
                "final_url": final_url,
            }
            if final_screenshot:
                ended_payload["image"] = final_screenshot
            await self._ws.send_text(json.dumps(ended_payload))
            if final_screenshot:
                self._append_message(
                    "assistant",
                    f"[Takeover Ended] Resumed at: {final_url}",
                    image_data=final_screenshot,
                )

            self._pm.resume_from_human()

        asyncio.create_task(do_takeover())

    async def _handle_user_input(self, payload: dict) -> None:
        user_msg: str = payload.get("message", "")
        user_images: list = payload.get("images", [])

        # Save uploaded images to workspace and collect paths
        saved_paths: list = []
        for i, data_url in enumerate(user_images):
            try:
                header, b64_data = data_url.split(",", 1)
                media_type = header.split(":")[1].split(";")[0]
                ext = media_type.split("/")[1] if "/" in media_type else "bin"
                ext = ext.replace("+xml", "")
                filename = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i}.{ext}"
                filepath = self._uploads_dir / filename
                filepath.write_bytes(base64.b64decode(b64_data))
                saved_paths.append(str(filepath))
            except Exception as e:
                print(f"Failed to save uploaded image: {e}")

        self._append_message("user", user_msg, images=user_images)

        # Dispatch to on_message callback if set (allows external orchestration)
        if self.on_message is not None:
            unified = UnifiedMessage(
                platform="web",
                user_id="web_user",
                session_id=self._session_id,
                text=user_msg,
                attachments=[(f"image_{i}", du) for i, du in enumerate(user_images)],
            )
            await self.on_message(unified)

        history = self._build_history()

        async def _ws_send_msg(msg) -> None:
            if isinstance(msg, dict):
                human_text = msg.get("message", "")
                packet = {"type": "info", **msg}
            else:
                human_text = str(msg)
                packet = {"type": "info", "message": human_text}
            self._append_message("assistant", human_text)
            await self._ws.send_text(json.dumps(packet))

        asyncio.create_task(self._run_agent(
            self._pm,
            user_msg,
            _ws_send_msg,
            lambda reason, img: self.request_action(self._session_id, reason, img),
            self._send_image,
            images=user_images,
            history_messages=history,
            uploaded_files=saved_paths,
        ))
