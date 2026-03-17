"""
run_all.py - Launch all NeoFish platform adapters in a single process.

Run with:
    python run_all.py
or:
    uv run python run_all.py

Which platforms are started depends on which tokens / URLs are configured:
    • Web        — always started (FastAPI on WEB_HOST:WEB_PORT)
    • Telegram   — started when TELEGRAM_BOT_TOKEN is set
    • QQ         — started when QQ_WS_URL is set

Environment variables are loaded from .env automatically.
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


async def _run_web():
    """Start the FastAPI/uvicorn web server."""
    import uvicorn
    from config import WEB_HOST, WEB_PORT

    config = uvicorn.Config(
        "main:app",
        host=WEB_HOST,
        port=WEB_PORT,
        reload=False,
        log_level="info",
    )
    server = uvicorn.Server(config)
    logger.info("Starting Web adapter on %s:%d…", WEB_HOST, WEB_PORT)
    await server.serve()


async def _run_telegram():
    """Start the Telegram bot adapter (only if token is set)."""
    from config import TELEGRAM_BOT_TOKEN
    if not TELEGRAM_BOT_TOKEN:
        logger.info("Telegram adapter skipped (TELEGRAM_BOT_TOKEN not set).")
        return

    from platforms.telegram import TelegramAdapter
    from playwright_manager import PlaywrightManager
    from session import session_store
    from _agent_runner import make_message_handler

    pm = PlaywrightManager()
    await pm.start()

    adapter = TelegramAdapter(session_store=session_store)
    adapter.on_message = make_message_handler(adapter, pm)

    logger.info("Starting Telegram adapter…")
    await adapter.start()

    try:
        await asyncio.Event().wait()
    finally:
        await adapter.stop()
        await pm.stop()


async def _run_qq():
    """Start the QQ bot adapter (only if WS URL is set)."""
    from config import QQ_WS_URL
    if not QQ_WS_URL:
        logger.info("QQ adapter skipped (QQ_WS_URL not set).")
        return

    from platforms.qq import QQAdapter
    from playwright_manager import PlaywrightManager
    from session import session_store
    from _agent_runner import make_message_handler

    pm = PlaywrightManager()
    await pm.start()

    adapter = QQAdapter(session_store=session_store)
    adapter.on_message = make_message_handler(adapter, pm)

    logger.info("Starting QQ adapter…")
    await adapter.start()

    try:
        await asyncio.Event().wait()
    finally:
        await adapter.stop()
        await pm.stop()


async def main():
    tasks = [
        asyncio.create_task(_run_web(), name="web"),
        asyncio.create_task(_run_telegram(), name="telegram"),
        asyncio.create_task(_run_qq(), name="qq"),
    ]

    try:
        await asyncio.gather(*tasks)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down all adapters…")
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
