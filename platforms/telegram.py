"""
platforms/telegram.py - Telegram Bot API adapter for NeoFish.

Uses the python-telegram-bot library (v20+ async API).
Install it with:  uv add python-telegram-bot

Configuration (via .env or environment variables):
    TELEGRAM_BOT_TOKEN      — token from @BotFather (required)
    TELEGRAM_ALLOWED_USERS  — comma-separated Telegram user IDs (optional)

Usage::

    from platforms.telegram import TelegramAdapter
    from session import session_store

    adapter = TelegramAdapter(session_store=session_store)
    adapter.on_message = my_message_handler   # async (UnifiedMessage) -> None
    await adapter.start()
    # … runs until stop() is called
    await adapter.stop()
"""

import logging
from typing import Callable, List, Optional

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USERS
from message import UnifiedMessage
from platforms.base import PlatformAdapter
from session import SessionStore

logger = logging.getLogger(__name__)


class TelegramAdapter(PlatformAdapter):
    """
    Platform adapter for Telegram.

    Each incoming Telegram message is translated into a ``UnifiedMessage``
    and handed to ``self.on_message``.  Replies are sent back via the
    Telegram Bot API.

    Parameters
    ----------
    session_store:
        ``SessionStore`` instance used to map Telegram chat IDs to unified
        session UUIDs.
    bot_token:
        Telegram Bot token.  Defaults to ``TELEGRAM_BOT_TOKEN`` from config.
    allowed_users:
        List of Telegram user IDs (as strings) that are permitted to interact
        with the bot.  An empty list allows everyone.
    """

    def __init__(
        self,
        session_store: SessionStore,
        bot_token: Optional[str] = None,
        allowed_users: Optional[List[str]] = None,
    ) -> None:
        super().__init__()
        self._token = bot_token or TELEGRAM_BOT_TOKEN
        self._allowed = set(allowed_users) if allowed_users else set(TELEGRAM_ALLOWED_USERS)
        self._session_store = session_store
        self._app = None  # telegram.ext.Application, created in start()

    # ── PlatformAdapter interface ─────────────────────────────────────────────

    async def start(self) -> None:
        """Initialise and start the Telegram long-poll loop."""
        try:
            from telegram.ext import Application, MessageHandler, filters
        except ImportError as exc:
            raise RuntimeError(
                "python-telegram-bot is not installed. "
                "Run: uv add python-telegram-bot"
            ) from exc

        if not self._token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN is not set. "
                "Add it to your .env file or set the environment variable."
            )

        self._app = (
            Application.builder()
            .token(self._token)
            .build()
        )

        # Register a handler for every text/photo message
        self._app.add_handler(
            MessageHandler(filters.TEXT | filters.PHOTO, self._on_telegram_message)
        )

        logger.info("Starting Telegram adapter (long-polling)…")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

    async def stop(self) -> None:
        """Stop the Telegram long-poll loop."""
        if self._app is not None:
            logger.info("Stopping Telegram adapter…")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def send_message(
        self,
        session_id: str,
        text: str,
        images: Optional[List[str]] = None,
    ) -> None:
        """Send a text reply to the Telegram chat linked to *session_id*."""
        chat_id = self._session_store.get_chat_id("telegram", session_id)
        if chat_id is None:
            logger.warning("send_message: no Telegram chat mapped to session %s", session_id)
            return

        if self._app is None:
            logger.warning("send_message called before start()")
            return

        # Telegram message length limit is 4096 characters
        for chunk in _split_text(text, max_length=4096):
            await self._app.bot.send_message(chat_id=chat_id, text=chunk)

        if images:
            for img in images:
                await self._send_image_to_chat(chat_id, img)

    async def request_action(
        self,
        session_id: str,
        reason: str,
        image: Optional[str] = None,
    ) -> None:
        """Notify the Telegram user that human intervention is required."""
        text = f"⚠️ *Action required*\n\n{reason}"
        chat_id = self._session_store.get_chat_id("telegram", session_id)
        if chat_id is None:
            logger.warning("request_action: no Telegram chat mapped to session %s", session_id)
            return

        if self._app is None:
            return

        await self._app.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
        )
        if image:
            await self._send_image_to_chat(chat_id, image)

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _on_telegram_message(self, update, context) -> None:
        """Handler registered with python-telegram-bot for incoming messages."""
        from telegram import Update  # local import to keep startup fast

        if update.message is None:
            return

        user = update.message.from_user
        chat = update.message.chat
        user_id_str = str(user.id) if user else "unknown"
        chat_id_str = str(chat.id)

        # Access control
        if self._allowed and user_id_str not in self._allowed:
            logger.warning("Rejected message from unauthorised Telegram user %s", user_id_str)
            await update.message.reply_text("Sorry, you are not authorised to use this bot.")
            return

        # Map the Telegram chat to a unified session (create if absent).
        # get_or_create automatically stores the bidirectional mapping.
        session_id = self._session_store.get_or_create("telegram", chat_id_str)

        # Collect text and photo attachments
        text = update.message.text or update.message.caption or ""
        attachments = []
        if update.message.photo:
            # Telegram provides multiple sizes; pick the largest
            photo = update.message.photo[-1]
            tg_file = await context.bot.get_file(photo.file_id)
            file_bytes = await tg_file.download_as_bytearray()
            attachments.append((f"{photo.file_id}.jpg", bytes(file_bytes)))

        msg = UnifiedMessage(
            platform="telegram",
            user_id=user_id_str,
            session_id=session_id,
            text=text,
            attachments=attachments,
        )

        if self.on_message is not None:
            await self.on_message(msg)
        else:
            logger.warning("TelegramAdapter.on_message is not set; message dropped.")

    async def _send_image_to_chat(self, chat_id: str, image: str) -> None:
        """Send a base64-encoded or URL image to a Telegram chat."""
        import base64 as _b64
        import io

        if image.startswith("data:"):
            # data-URL: data:image/png;base64,<data>
            _, b64_part = image.split(",", 1)
            img_bytes = _b64.b64decode(b64_part)
            buf = io.BytesIO(img_bytes)
            buf.name = "screenshot.png"
            await self._app.bot.send_photo(chat_id=chat_id, photo=buf)
        elif image.startswith("http://") or image.startswith("https://"):
            await self._app.bot.send_photo(chat_id=chat_id, photo=image)
        else:
            # Assume raw base64
            img_bytes = _b64.b64decode(image)
            buf = io.BytesIO(img_bytes)
            buf.name = "screenshot.png"
            await self._app.bot.send_photo(chat_id=chat_id, photo=buf)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _split_text(text: str, max_length: int = 4096) -> List[str]:
    """Split *text* into chunks no longer than *max_length* characters."""
    if len(text) <= max_length:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:max_length])
        text = text[max_length:]
    return chunks
