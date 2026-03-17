"""
run_qq.py - Standalone entry point for the NeoFish QQ bot.

Run with:
    python run_qq.py
or:
    uv run python run_qq.py

Required environment variables (set in .env or shell):
    QQ_WS_URL     — WebSocket URL of your NapCat / go-cqhttp instance,
                    e.g. ws://127.0.0.1:3001
    QQ_API_URL    — HTTP API base URL, e.g. http://127.0.0.1:3000
    ANTHROPIC_API_KEY — Anthropic API key for the agent

Optional:
    QQ_ACCESS_TOKEN   — access token if configured in NapCat
    QQ_ALLOWED_IDS    — comma-separated user/group IDs to accept
    MODEL_NAME, WORKDIR, … — same as the web platform

NapCat quick setup:
    1. Install NapCat and sign in.
    2. Enable the HTTP API plugin on port 3000.
    3. Enable the Forward WebSocket plugin on port 3001.
    4. Set QQ_WS_URL=ws://127.0.0.1:3001 and QQ_API_URL=http://127.0.0.1:3000.
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
    from platforms.qq import QQAdapter
    from playwright_manager import PlaywrightManager
    from session import session_store
    from _agent_runner import make_message_handler

    pm = PlaywrightManager()
    await pm.start()

    adapter = QQAdapter(session_store=session_store)
    adapter.on_message = make_message_handler(adapter, pm)

    logger.info("Starting NeoFish QQ bot…")
    await adapter.start()

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        logger.info("Shutting down QQ bot…")
        await adapter.stop()
        await pm.stop()


if __name__ == "__main__":
    asyncio.run(main())
