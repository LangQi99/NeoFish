"""
platforms/qq.py - QQ platform adapter for NeoFish.

Connects to a NapCat / go-cqhttp instance via its forward WebSocket
(OneBot v11 event bus). All API calls go through WebSocket.

Configuration (via .env or environment variables):
    QQ_WS_URL         — WebSocket URL for events and API calls,
                        e.g. ws://127.0.0.1:3001  (required)
    QQ_ACCESS_TOKEN   — Access token (optional, depends on NapCat config)
    QQ_ALLOWED_IDS    — Comma-separated user/group IDs to accept (optional)

NapCat setup (quick start):
    1. Install NapCat and log in with your QQ account.
    2. Enable the "正向 WebSocket" (forward WebSocket) plugin on port 3001.
    3. Set QQ_WS_URL in your .env.

Usage::

    from platforms.qq import QQAdapter
    from session import session_store

    adapter = QQAdapter(session_store=session_store)
    adapter.on_message = my_message_handler   # async (UnifiedMessage) -> None
    await adapter.start()
    # … runs until stop() is called
    await adapter.stop()
"""

import asyncio
import json
import logging
import os
from typing import Dict, List, Optional

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False

from config import QQ_ACCESS_TOKEN, QQ_ALLOWED_IDS, QQ_WS_URL
from message import UnifiedMessage
from platforms.base import PlatformAdapter
from session import SessionStore

logger = logging.getLogger(__name__)

# OneBot v11 message type constants
_MSG_TYPE_GROUP = "group"
_MSG_TYPE_PRIVATE = "private"


class QQAdapter(PlatformAdapter):
    """Platform adapter for QQ via NapCat / go-cqhttp (OneBot v11).

    Listens for events on the OneBot WebSocket and forwards incoming messages
    to ``self.on_message`` as ``UnifiedMessage`` objects. Replies are sent
    via WebSocket API calls.

    Parameters
    ----------
    session_store:
        ``SessionStore`` instance for mapping QQ chats to unified sessions.
    ws_url:
        WebSocket URL for the OneBot event bus and API calls.
    access_token:
        Optional access token for NapCat / go-cqhttp authentication.
    allowed_ids:
        List of QQ user / group IDs (as strings) that are permitted to
        interact.  An empty list allows everyone.
    """

    def __init__(
        self,
        session_store: SessionStore,
        ws_url: Optional[str] = None,
        access_token: Optional[str] = None,
        allowed_ids: Optional[List[str]] = None,
    ) -> None:
        super().__init__()
        self._ws_url = ws_url or QQ_WS_URL
        self._access_token = access_token or QQ_ACCESS_TOKEN
        self._allowed = set(allowed_ids) if allowed_ids else set(QQ_ALLOWED_IDS)
        self._session_store = session_store
        self._running = False
        self._ws = None          # aiohttp ClientWebSocketResponse
        self._session: Optional[aiohttp.ClientSession] = None
        self._task: Optional[asyncio.Task] = None
        self._echo_counter = 0   # For WS API call correlation
        self._pending_calls: Dict[str, asyncio.Future] = {}  # echo -> Future

    # ── PlatformAdapter interface ─────────────────────────────────────────────

    async def start(self) -> None:
        """Connect to the OneBot WebSocket and start the event loop."""
        if not _AIOHTTP_AVAILABLE:
            raise RuntimeError(
                "aiohttp is not installed. Run: uv add aiohttp"
            )

        if not self._ws_url:
            raise ValueError(
                "QQ_WS_URL is not set. "
                "Add it to your .env file or set the environment variable."
            )

        self._running = True
        logger.info("Starting QQ adapter, connecting to %s…", self._ws_url)
        self._session = aiohttp.ClientSession()
        self._task = asyncio.create_task(self._listen_loop())

    async def stop(self) -> None:
        """Stop the OneBot event loop and close connections."""
        self._running = False
        if self._ws is not None:
            await self._ws.close()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._session is not None:
            await self._session.close()
        # Cancel any pending API calls
        for future in self._pending_calls.values():
            if not future.done():
                future.cancel()
        self._pending_calls.clear()
        logger.info("QQ adapter stopped.")

    async def send_message(
        self,
        session_id: str,
        text: str,
        images: Optional[List[str]] = None,
    ) -> None:
        """Send a text reply to the QQ chat linked to *session_id*."""
        target = self._session_store.get_chat_id("qq", session_id)
        if target is None:
            logger.warning("send_message: no QQ chat mapped to session %s", session_id)
            return

        msg_type, chat_id = _parse_target(target)
        messages = [{"type": "text", "data": {"text": text}}]

        if images:
            for img in images:
                messages.append(_build_image_segment(img))

        await self._call_api("send_msg", {
            "message_type": msg_type,
            "group_id" if msg_type == _MSG_TYPE_GROUP else "user_id": int(chat_id),
            "message": messages,
        })

    async def request_action(
        self,
        session_id: str,
        reason: str,
        image: Optional[str] = None,
    ) -> None:
        """Notify the QQ user that human intervention is required."""
        text = f"⚠️ 需要人工操作\n\n{reason}"
        target = self._session_store.get_chat_id("qq", session_id)
        if target is None:
            logger.warning("request_action: no QQ chat mapped to session %s", session_id)
            return

        msg_type, chat_id = _parse_target(target)
        messages: list = [{"type": "text", "data": {"text": text}}]
        if image:
            messages.append(_build_image_segment(image))

        await self._call_api("send_msg", {
            "message_type": msg_type,
            "group_id" if msg_type == _MSG_TYPE_GROUP else "user_id": int(chat_id),
            "message": messages,
        })

    async def send_file(
        self,
        session_id: str,
        file_path: str,
        description: str = "",
    ) -> None:
        """Send a file to the QQ user.

        Uses upload_private_file or upload_group_file API for NapCat/OneBot v11.
        """
        target = self._session_store.get_chat_id("qq", session_id)
        if target is None:
            logger.warning("send_file: no QQ chat mapped to session %s", session_id)
            return

        msg_type, chat_id = _parse_target(target)

        if description:
            await self.send_message(session_id, description)

        abs_path = os.path.abspath(file_path)

        if msg_type == _MSG_TYPE_GROUP:
            await self._call_api("upload_group_file", {
                "group_id": int(chat_id),
                "file": abs_path,
                "name": os.path.basename(abs_path),
            })
        else:
            await self._call_api("upload_private_file", {
                "user_id": int(chat_id),
                "file": abs_path,
                "name": os.path.basename(abs_path),
            })

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _listen_loop(self) -> None:
        """Main loop: connect to WS, receive and dispatch OneBot events."""
        headers = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        while self._running:
            try:
                async with self._session.ws_connect(self._ws_url, headers=headers) as ws:
                    self._ws = ws
                    logger.info("QQ adapter: WebSocket connected to %s", self._ws_url)
                    async for msg in ws:
                        if not self._running:
                            break
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            asyncio.create_task(self._dispatch(msg.data))
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            logger.warning("QQ WebSocket closed/error: %s", msg)
                            break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if self._running:
                    logger.error("QQ adapter connection error: %s — reconnecting in 5s", exc)
                    await asyncio.sleep(5)

    async def _dispatch(self, raw: str) -> None:
        """Parse a raw OneBot event JSON string and handle it."""
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("QQ adapter: received non-JSON data: %s", raw[:200])
            return

        # Handle API response (for WS-based API calls)
        if "echo" in event:
            echo = str(event["echo"])
            if echo in self._pending_calls:
                future = self._pending_calls.pop(echo)
                if not future.done():
                    future.set_result(event)
            return

        # Handle message events
        post_type = event.get("post_type")
        if post_type != "message":
            return  # Ignore meta/notice/request events for now

        msg_type: str = event.get("message_type", "")
        user_id_str: str = str(event.get("user_id", ""))
        group_id: Optional[int] = event.get("group_id")

        # Determine the chat ID for session mapping
        if msg_type == _MSG_TYPE_GROUP and group_id:
            chat_id_str = f"group_{group_id}"
        else:
            chat_id_str = f"private_{user_id_str}"

        # Access control
        if self._allowed and chat_id_str not in self._allowed and user_id_str not in self._allowed:
            logger.debug("Rejected QQ message from %s / %s", user_id_str, chat_id_str)
            return

        # get_or_create automatically stores the bidirectional mapping.
        session_id = self._session_store.get_or_create("qq", chat_id_str)

        # Extract plain text from the OneBot message segments
        raw_message = event.get("message", [])
        if isinstance(raw_message, str):
            text = raw_message
        else:
            text = "".join(
                seg.get("data", {}).get("text", "")
                for seg in raw_message
                if seg.get("type") == "text"
            )

        # Collect image attachments (URLs provided by NapCat)
        attachments = []
        if isinstance(raw_message, list):
            for seg in raw_message:
                seg_type = seg.get("type")
                seg_data = seg.get("data", {})

                if seg_type == "image":
                    url = seg_data.get("url") or seg_data.get("file", "")
                    if url:
                        attachments.append(("qq_image.jpg", url))

                elif seg_type == "file":
                    file_url = seg_data.get("url") or seg_data.get("file", "")
                    filename = seg_data.get("name", "qq_file")
                    if file_url:
                        attachments.append((filename, file_url))

                elif seg_type == "video":
                    video_url = seg_data.get("url") or seg_data.get("file", "")
                    if video_url:
                        attachments.append(("qq_video.mp4", video_url))

                elif seg_type == "record":
                    audio_url = seg_data.get("url") or seg_data.get("file", "")
                    if audio_url:
                        attachments.append(("qq_audio.mp3", audio_url))

        unified = UnifiedMessage(
            platform="qq",
            user_id=user_id_str,
            session_id=session_id,
            text=text,
            attachments=attachments,
        )

        if self.on_message is not None:
            await self.on_message(unified)
        else:
            logger.warning("QQAdapter.on_message is not set; message dropped.")

    async def _call_api(self, action: str, params: dict, timeout: float = 10.0) -> Optional[dict]:
        """Call a OneBot v11 API via WebSocket.

        Parameters
        ----------
        action:
            OneBot v11 action name, e.g. ``"send_msg"``.
        params:
            Action parameters dict.
        timeout:
            Seconds to wait for response.

        Returns
        -------
        The parsed JSON response, or *None* on error/timeout.
        """
        if self._ws is None:
            logger.warning("QQ API call failed: WebSocket not connected")
            return None

        self._echo_counter += 1
        echo = str(self._echo_counter)

        payload = {
            "action": action,
            "params": params,
            "echo": echo,
        }

        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending_calls[echo] = future

        try:
            await self._ws.send_str(json.dumps(payload))
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending_calls.pop(echo, None)
            logger.warning("QQ API call timed out: %s", action)
            return None
        except Exception as exc:
            self._pending_calls.pop(echo, None)
            logger.error("QQ API call failed (%s): %s", action, exc)
            return None


# ── Utilities ─────────────────────────────────────────────────────────────────

def _parse_target(target: str):
    """Parse a stored target string back into (msg_type, chat_id).

    Stored format:
        "group_<group_id>"   -> (_MSG_TYPE_GROUP, "<group_id>")
        "private_<user_id>"  -> (_MSG_TYPE_PRIVATE, "<user_id>")
    """
    if target.startswith("group_"):
        return _MSG_TYPE_GROUP, target[len("group_"):]
    if target.startswith("private_"):
        return _MSG_TYPE_PRIVATE, target[len("private_"):]
    # Fallback: treat as private message
    return _MSG_TYPE_PRIVATE, target


def _build_image_segment(image: str) -> dict:
    """Build a OneBot v11 image message segment from a base64 or URL string."""
    if image.startswith("http://") or image.startswith("https://"):
        return {"type": "image", "data": {"file": image}}
    if image.startswith("data:"):
        # data:image/png;base64,<data>  →  base64://<data>
        _, b64_part = image.split(",", 1)
        return {"type": "image", "data": {"file": f"base64://{b64_part}"}}
    # Assume raw base64
    return {"type": "image", "data": {"file": f"base64://{image}"}}
