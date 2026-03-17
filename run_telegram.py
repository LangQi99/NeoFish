"""
run_telegram.py - Standalone entry point for the NeoFish Telegram bot.

Run with:
    python run_telegram.py
or:
    uv run python run_telegram.py

Required environment variables (set in .env or shell):
    TELEGRAM_BOT_TOKEN    — token from @BotFather
    ANTHROPIC_API_KEY     — Anthropic API key for the agent

Optional:
    TELEGRAM_ALLOWED_USERS  — comma-separated Telegram user IDs (default: allow all)
    MODEL_NAME, WORKDIR, … — same as the web platform
"""

import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    from platforms.telegram import TelegramAdapter
    from playwright_manager import PlaywrightManager
    from session import session_store
    from _agent_runner import make_message_handler

    pm = PlaywrightManager()
    await pm.start()

    adapter = TelegramAdapter(session_store=session_store)
    adapter.on_message = make_message_handler(adapter, pm)

    logger.info("Starting NeoFish Telegram bot…")
    await adapter.start()

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        logger.info("Shutting down Telegram bot…")
        await adapter.stop()
        await pm.stop()


if __name__ == "__main__":
    asyncio.run(main())
