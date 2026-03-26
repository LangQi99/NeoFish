import asyncio
import base64
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from fastapi import WebSocket

from message import UnifiedMessage
from platforms.base import PlatformAdapter
from agent_task_manager import task_manager
from background_manager import background_manager

logger = logging.getLogger(__name__)

_ASSISTANT_MSG_PREFIXES = (
    "[Image] ",
    "[Action Required] ",
    "[Takeover] ",
    "[Takeover Ended] ",
)

_MIME_TYPES = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip": "application/zip",
    "txt": "text/plain",
    "json": "application/json",
    "csv": "text/csv",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "mp4": "video/mp4",
    "mp3": "audio/mpeg",
}

_web_queues: dict[str, asyncio.Queue] = {}
_web_running: set[str] = set()


class WebAdapter(PlatformAdapter):
    """
    Platform adapter for the browser-based WebSocket frontend.

    One instance is created per active WebSocket connection.  The caller
    (FastAPI route) passes the live WebSocket object and a reference to the
    shared sessions dict so the adapter can persist messages.

    Supports message queuing: if an agent is running and a new message arrives,
    it's queued and processed in the next agent loop iteration.

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
        self._workspace_dir = uploads_dir.parent
        self._pm = playwright_manager
        self._run_agent = run_agent

    # ── PlatformAdapter interface ─────────────────────────────────────────────

    async def start(self) -> None:
        await self._ws.send_text(
            json.dumps(
                {
                    "type": "info",
                    "message": "Connected to NeoFish Agent WebSocket",
                    "message_key": "common.connected_ws",
                    "session_id": self._session_id,
                }
            )
        )

        task_status = task_manager.get_task_status(self._session_id)
        await self._ws.send_text(
            json.dumps(
                {
                    "type": "task_status",
                    "status": task_status.value if task_status else None,
                }
            )
        )

        buffered = task_manager.get_buffered_messages(self._session_id)
        for msg_data in buffered:
            await self._ws.send_text(json.dumps(msg_data["message"]))

    async def stop(self) -> None:
        if not task_manager.has_running_task(self._session_id):
            self._pm.deactivate_tab(self._session_id)

    def _is_ws_connected(self) -> bool:
        client_state = getattr(self._ws, "client_state", None)
        return bool(client_state and client_state.name == "CONNECTED")

    async def _send_packet(
        self, packet: dict, *, buffer_on_disconnect: bool = True
    ) -> None:
        try:
            if self._is_ws_connected():
                await self._ws.send_text(json.dumps(packet))
                return
        except Exception as e:
            logger.warning("WebSocket send failed for session %s: %s", self._session_id, e)

        if buffer_on_disconnect:
            task_manager.buffer_message(self._session_id, packet)

    async def send_message(
        self,
        session_id: str,
        text: str,
        images: Optional[List[str]] = None,
    ) -> None:
        """Send a plain text (+ optional images) assistant message."""
        packet: dict = {"type": "info", "message": text}
        await self._send_packet(packet)
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
        await self._send_packet(payload)
        self._append_message(
            "assistant",
            f"[Action Required] {reason}",
            image_data=image or "",
        )

    async def send_file(
        self,
        session_id: str,
        file_path: str,
        description: str = "",
    ) -> None:
        """Send a file to the web user."""
        try:
            full_path = Path(file_path)
            if not full_path.is_absolute():
                full_path = (self._workspace_dir / full_path).resolve()

            # Read file and encode to base64
            with open(full_path, "rb") as f:
                file_bytes = f.read()

            filename = full_path.name
            b64_data = base64.b64encode(file_bytes).decode()

            # Determine MIME type
            ext = filename.lower().split(".")[-1] if "." in filename else "bin"
            mime_type = _MIME_TYPES.get(ext, "application/octet-stream")

            payload = {
                "type": "file",
                "filename": filename,
                "mime_type": mime_type,
                "data": b64_data,
                "description": description,
            }
            await self._send_packet(payload)
            self._append_message("assistant", f"[File] {description or filename}")
        except Exception as e:
            logger.error("Failed to send file to web user: %s", e)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _append_message(
        self,
        role: str,
        content: str,
        images: list = None,
        image_data: str = "",
        message_key: str = "",
        params: dict = None,
    ) -> None:
        if images is None:
            images = []
        if params is None:
            params = {}
        msg: dict = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "images": images,
        }
        if image_data:
            msg["image_data"] = image_data
        if message_key:
            msg["message_key"] = message_key
        if params:
            msg["params"] = params
        self._sessions[self._session_id]["messages"].append(msg)
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
        await self._send_packet(payload)
        self._append_message(
            "assistant", f"[Image] {description}", image_data=b64_image
        )

    def _build_history(self) -> list:
        """Build the conversation history list for the agent (excludes last msg)."""
        history: list = []
        messages = self._sessions[self._session_id]["messages"]
        for m in messages[:-1]:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "user":
                history.append(
                    {"role": "user", "content": content or "(user sent an image)"}
                )
            else:
                clean = content
                for prefix in _ASSISTANT_MSG_PREFIXES:
                    if clean.startswith(prefix):
                        clean = clean[len(prefix) :]
                if clean:
                    history.append({"role": "assistant", "content": clean})
        return history

    # ── Message dispatch ──────────────────────────────────────────────────────

    async def handle_message(self, raw: str) -> None:
        payload = json.loads(raw)
        msg_type = payload.get("type")

        if msg_type == "resume":
            await self._handle_resume()
        elif msg_type == "stop_task":
            await self._handle_stop_task()
        elif msg_type == "takeover":
            await self._handle_takeover()
        elif msg_type == "takeover_done":
            self._pm.signal_takeover_done()
        elif msg_type == "takeover_click":
            await self._handle_takeover_click(payload)
        elif msg_type == "takeover_double_click":
            await self._handle_takeover_double_click(payload)
        elif msg_type == "takeover_mouse_move":
            await self._handle_takeover_mouse_move(payload)
        elif msg_type == "takeover_key":
            await self._handle_takeover_key(payload)
        elif msg_type == "takeover_type":
            await self._handle_takeover_type(payload)
        elif msg_type == "takeover_scroll":
            await self._handle_takeover_scroll(payload)
        elif msg_type == "takeover_navigate":
            await self._handle_takeover_navigate(payload)
        elif msg_type == "user_input":
            await self._handle_user_input(payload)

    async def _handle_stop_task(self) -> None:
        task_stopped = await task_manager.stop_task(self._session_id)
        background_cancelled = await background_manager.cancel_by_session(
            self._session_id
        )
        success = task_stopped or background_cancelled > 0

        if success:
            if task_stopped and background_cancelled > 0:
                message = (
                    f"Task stopped. Cancelled {background_cancelled} background task(s)."
                )
                message_key = ""
            elif background_cancelled > 0:
                message = f"Cancelled {background_cancelled} background task(s)."
                message_key = ""
            else:
                message = "Task stopped."
                message_key = "common.task_stopped"
            await self._send_packet(
                {
                    "type": "info",
                    "message": message,
                    **({"message_key": message_key} if message_key else {}),
                }
            )
            self._append_message(
                "assistant", message, message_key=message_key or ""
            )
        else:
            message = "No running task to stop."
            message_key = "common.no_task_to_stop"
            await self._send_packet(
                {
                    "type": "info",
                    "message": message,
                    "message_key": message_key,
                }
            )
            self._append_message("assistant", message, message_key=message_key)

    async def _handle_resume(self) -> None:
        self._pm.signal_resume(self._session_id)
        message = "Agent resumed execution."
        message_key = "common.agent_resumed"
        await self._send_packet(
            {
                "type": "info",
                "message": message,
                "message_key": message_key,
            }
        )
        self._append_message("assistant", message, message_key=message_key)

    async def _handle_takeover(self) -> None:
        if self._pm.in_takeover:
            await self._send_packet(
                {
                    "type": "info",
                    "message": "Takeover is already in progress.",
                    "message_key": "common.takeover_already_active",
                }
            )
            return

        self._pm.set_current_session(self._session_id)
        self._pm.request_pause(self._session_id)

        async def do_takeover() -> None:
            # Capture current URL and initial screenshot before handing over.
            current_url: str = "about:blank"
            try:
                page = (
                    self._pm.tab_manager.get_active_page(self._session_id)
                    if self._pm.tab_manager
                    else None
                )
                if page and not page.is_closed():
                    current_url = page.url
            except Exception:
                pass

            initial_screenshot = await self._pm.get_page_screenshot_base64(
                self._session_id
            )

            await self._send_packet(
                {
                    "type": "takeover_started",
                    "message": "Browser embedded for manual interaction.",
                    "message_key": "common.takeover_started",
                    "url": current_url,
                    "image": initial_screenshot,
                    "viewport": {
                        "width": self._pm.viewport_width,
                        "height": self._pm.viewport_height,
                    },
                }
            )
            self._append_message(
                "assistant",
                "[Takeover] Browser opened for manual interaction.",
            )

            # Mark as in takeover and create the completion event.
            done_event = self._pm.begin_embedded_takeover(self._session_id)

            # Stream screenshots to the frontend.
            async def send_frame(screenshot_b64: str, url: str) -> None:
                try:
                    await self._send_packet(
                        {
                            "type": "takeover_frame",
                            "image": screenshot_b64,
                            "url": url,
                        },
                        buffer_on_disconnect=False,
                    )
                except Exception as e:
                    logger.warning("Takeover frame send error: %s", e)

            await self._pm.start_takeover_stream(
                send_frame, stream_interval=0.5, session_id=self._session_id
            )

            # Block until the user signals "done".
            await done_event.wait()

            try:
                # Collect final state.
                final_url: str = "about:blank"
                final_screenshot: str = ""
                try:
                    page = (
                        self._pm.tab_manager.get_active_page(self._session_id)
                        if self._pm.tab_manager
                        else None
                    )
                    if page and not page.is_closed():
                        final_url = page.url
                        final_screenshot = await self._pm.get_page_screenshot_base64(
                            self._session_id
                        )
                except Exception:
                    pass

                ended_payload: dict = {
                    "type": "takeover_ended",
                    "message": "Takeover ended. AI is resuming.",
                    "message_key": "common.takeover_ended",
                    "final_url": final_url,
                }
                if final_screenshot:
                    ended_payload["image"] = final_screenshot
                await self._send_packet(ended_payload)
                if final_screenshot:
                    self._append_message(
                        "assistant",
                        f"[Takeover Ended] Resumed at: {final_url}",
                        image_data=final_screenshot,
                    )
            finally:
                self._pm.end_embedded_takeover()
                self._pm.signal_resume(self._session_id)

        asyncio.create_task(do_takeover())

    # ── Takeover input forwarding ─────────────────────────────────────────────

    async def _handle_takeover_click(self, payload: dict) -> None:
        x = float(payload.get("x", 0))
        y = float(payload.get("y", 0))
        button = payload.get("button", "left")
        await self._pm.handle_takeover_click(x, y, button)

    async def _handle_takeover_double_click(self, payload: dict) -> None:
        x = float(payload.get("x", 0))
        y = float(payload.get("y", 0))
        await self._pm.handle_takeover_double_click(x, y)

    async def _handle_takeover_mouse_move(self, payload: dict) -> None:
        x = float(payload.get("x", 0))
        y = float(payload.get("y", 0))
        await self._pm.handle_takeover_mouse_move(x, y)

    async def _handle_takeover_key(self, payload: dict) -> None:
        key = payload.get("key", "")
        if key:
            await self._pm.handle_takeover_key(key)

    async def _handle_takeover_type(self, payload: dict) -> None:
        text = payload.get("text", "")
        if text:
            await self._pm.handle_takeover_type(text)

    async def _handle_takeover_scroll(self, payload: dict) -> None:
        delta_x = float(payload.get("deltaX", 0))
        delta_y = float(payload.get("deltaY", 0))
        await self._pm.handle_takeover_scroll(delta_x, delta_y)

    async def _handle_takeover_navigate(self, payload: dict) -> None:
        url = payload.get("url", "")
        if url:
            await self._pm.handle_takeover_navigate(url)

    async def _handle_user_input(self, payload: dict) -> None:
        user_msg: str = payload.get("message", "")
        user_images: list = payload.get("images", [])
        user_files: list = payload.get("files", [])

        if task_manager.has_running_task(self._session_id):
            if self._session_id not in _web_queues:
                _web_queues[self._session_id] = asyncio.Queue()
            await _web_queues[self._session_id].put(
                {
                    "text": user_msg,
                    "images": user_images,
                    "files": user_files,
                }
            )
            await self._send_packet(
                {
                    "type": "info",
                    "message": "Message queued (agent is busy).",
                    "message_key": "common.message_queued",
                }
            )
            return

        # Save uploaded images to workspace and collect paths
        saved_paths: list = []
        for i, data_url in enumerate(user_images):
            try:
                header, b64_data = data_url.split(",", 1)
                media_type = header.split(":")[1].split(";")[0]
                ext = media_type.split("/")[1] if "/" in media_type else "bin"
                ext = ext.replace("+xml", "")
                filename = (
                    f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i}.{ext}"
                )
                filepath = self._uploads_dir / filename
                filepath.write_bytes(base64.b64decode(b64_data))
                saved_paths.append(str(filepath))
            except Exception as e:
                logger.warning("Failed to save uploaded image: %s", e)

        # Save uploaded files to workspace
        for file_data in user_files:
            try:
                filename = file_data.get("name", "upload")
                data_url = file_data.get("data", "")
                if not data_url:
                    continue

                header, b64_data = data_url.split(",", 1)
                # Use original filename with timestamp prefix
                safe_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
                filepath = self._uploads_dir / safe_name
                filepath.write_bytes(base64.b64decode(b64_data))
                saved_paths.append(str(filepath))
                logger.info("Saved uploaded file: %s", filepath)
            except Exception as e:
                logger.warning(
                    "Failed to save uploaded file %s: %s", file_data.get("name"), e
                )

        self._append_message("user", user_msg, images=user_images)

        # Dispatch to on_message callback if set (allows external orchestration)
        if self.on_message is not None:
            attachments = [(f"image_{i}", du) for i, du in enumerate(user_images)]
            attachments.extend(
                (f.get("name", f"file_{i}"), f.get("data", ""))
                for i, f in enumerate(user_files)
            )
            unified = UnifiedMessage(
                platform="web",
                user_id="web_user",
                session_id=self._session_id,
                text=user_msg,
                attachments=attachments,
            )
            await self.on_message(unified)

        history = self._build_history()

        async def _ws_send_msg(msg) -> None:
            if isinstance(msg, dict):
                human_text = msg.get("message", "")
                packet = {"type": "info", **msg}
                self._append_message(
                    "assistant",
                    human_text,
                    message_key=msg.get("message_key", ""),
                    params=msg.get("params"),
                )
            else:
                human_text = str(msg)
                packet = {"type": "info", "message": human_text}
                self._append_message("assistant", human_text)

            await self._send_packet(packet)

        _web_running.add(self._session_id)

        async def _run_with_queue(cancel_event: asyncio.Event = None):
            try:
                await self._run_agent(
                    self._pm,
                    user_msg,
                    _ws_send_msg,
                    lambda reason, img: self.request_action(
                        self._session_id, reason, img
                    ),
                    self._send_image,
                    lambda path, desc: self.send_file(self._session_id, path, desc),
                    images=user_images,
                    history_messages=history,
                    uploaded_files=saved_paths,
                    web_queue_getter=lambda: _web_queues.get(self._session_id),
                    web_session_id=self._session_id,
                    cancel_event=cancel_event,
                )
            finally:
                _web_running.discard(self._session_id)
                _web_queues.pop(self._session_id, None)
                self._pm.deactivate_tab(self._session_id)

        await task_manager.start_task(
            self._session_id,
            _run_with_queue,
        )
