"""
platforms/qq.py - QQ platform adapter for NeoFish.

Connects to a NapCat / go-cqhttp instance via its forward WebSocket
(onebot v11 event bus) and HTTP API for sending messages.

Configuration (via .env or environment variables):
    QQ_WS_URL         — WebSocket URL to receive events,
                        e.g. ws://127.0.0.1:3001  (required)
    QQ_API_URL        — HTTP API base URL for outgoing calls,
                        e.g. http://127.0.0.1:3000  (required)
    QQ_ACCESS_TOKEN   — Access token (optional, depends on NapCat config)
    QQ_ALLOWED_IDS    — Comma-separated user/group IDs to accept (optional)

NapCat setup (quick start):
    1. Install NapCat and log in with your QQ account.
    2. Enable the "HTTP API" plugin on port 3000.
    3. Enable the "正向 WebSocket" (forward WebSocket) plugin on port 3001.
    4. Set QQ_WS_URL and QQ_API_URL in your .env.

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
from typing import List, Optional

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False

from config import QQ_API_URL, QQ_ACCESS_TOKEN, QQ_WS_URL, QQ_ALLOWED_IDS
from message import UnifiedMessage
from platforms.base import PlatformAdapter
from session import SessionStore

logger = logging.getLogger(__name__)

# OneBot v11 message type constants
_MSG_TYPE_GROUP = "group"
_MSG_TYPE_PRIVATE = "private"


class QQAdapter(PlatformAdapter):
    """
    Platform adapter for QQ via NapCat / go-cqhttp (OneBot v11).

    Listens for events on the OneBot WebSocket and forwards incoming messages
    to ``self.on_message`` as ``UnifiedMessage`` objects.  Replies are sent
    via the HTTP API.

    Parameters
    ----------
    session_store:
        ``SessionStore`` instance for mapping QQ chats to unified sessions.
    ws_url:
        WebSocket URL for the OneBot event bus.
    api_url:
        HTTP API base URL for sending messages.
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
        api_url: Optional[str] = None,
        access_token: Optional[str] = None,
        allowed_ids: Optional[List[str]] = None,
    ) -> None:
        super().__init__()
        self._ws_url = ws_url or QQ_WS_URL
        self._api_url = (api_url or QQ_API_URL).rstrip("/")
        self._access_token = access_token or QQ_ACCESS_TOKEN
        self._allowed = set(allowed_ids) if allowed_ids else set(QQ_ALLOWED_IDS)
        self._session_store = session_store
        self._running = False
        self._ws = None          # aiohttp ClientWebSocketResponse
        self._http: Optional[object] = None  # aiohttp ClientSession
        self._task: Optional[asyncio.Task] = None

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
        headers = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        self._http = aiohttp.ClientSession(headers=headers)
        logger.info("Starting QQ adapter, connecting to %s…", self._ws_url)
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
        if self._http is not None:
            await self._http.close()
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

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _listen_loop(self) -> None:
        """Main loop: connect to WS, receive and dispatch OneBot events."""
        headers = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        while self._running:
            try:
                async with self._http.ws_connect(self._ws_url, headers=headers) as ws:
                    self._ws = ws
                    logger.info("QQ adapter: WebSocket connected to %s", self._ws_url)
                    async for msg in ws:
                        if not self._running:
                            break
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._dispatch(msg.data)
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
        """Parse a raw OneBot event JSON string and call on_message if needed."""
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("QQ adapter: received non-JSON data: %s", raw[:200])
            return

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
                if seg.get("type") == "image":
                    url = seg.get("data", {}).get("url") or seg.get("data", {}).get("file", "")
                    if url:
                        attachments.append((f"qq_image.jpg", url))

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

    async def _call_api(self, action: str, params: dict) -> Optional[dict]:
        """
        Call a NapCat / go-cqhttp HTTP API endpoint.

        Parameters
        ----------
        action:
            OneBot v11 action name, e.g. ``"send_msg"``.
        params:
            Action parameters dict.

        Returns
        -------
        The parsed JSON response, or *None* on error.
        """
        url = f"{self._api_url}/{action}"
        headers = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            async with self._http.post(url, json=params, headers=headers) as resp:
                return await resp.json()
        except Exception as exc:
            logger.error("QQ API call failed (%s): %s", action, exc)
            return None


# ── Utilities ─────────────────────────────────────────────────────────────────

def _parse_target(target: str):
    """
    Parse a stored target string back into (msg_type, chat_id).

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
