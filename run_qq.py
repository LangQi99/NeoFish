"""
run_qq.py - Standalone entry point for the NeoFish QQ bot.

Run with:
    python run_qq.py

Required environment variables (set in .env or shell):
    QQ_WS_URL          — WebSocket URL of your NapCat / go-cqhttp instance,
                         e.g. ws://127.0.0.1:3001
    ANTHROPIC_API_KEY  — Anthropic API key for the agent

Optional:
    QQ_ACCESS_TOKEN    — access token if configured in NapCat
    QQ_ALLOWED_IDS     — comma-separated user/group IDs to accept
    MODEL_NAME, WORKDIR, … — same as the web platform

NapCat quick setup:
    1. Install NapCat and sign in.
    2. Enable the Forward WebSocket plugin on port 3001.
    3. Set QQ_WS_URL=ws://127.0.0.1:3001 in your .env.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _make_result_callback(adapter):
    """Create a result callback that routes scheduled task results to QQ."""

    async def on_bot_task_complete(result, source_session_id, source_chat_id, source_platform, debug):
        status_icon = "[OK]" if result.status == "success" else "[FAIL]"
        text = (
            f"定时任务【{result.description}】已完成\n"
            f"{status_icon} 状态：{result.status}\n"
            f"{'─' * 40}\n"
            f"{result.summary}"
        )

        if debug:
            text += f"\n\n[Debug] 任务ID: {result.task_id}"

        if result.files:
            text += f"\n\n附件: {', '.join(result.files)}"

        if result.error:
            text += f"\n\n错误: {result.error}"

        try:
            await adapter.send_message(source_session_id, text)
            for f in result.files:
                try:
                    await adapter.send_file(source_session_id, f, "")
                except Exception:
                    logger.exception("Failed to send file %s via QQ", f)
        except Exception:
            logger.exception("QQ result callback failed")

    return on_bot_task_complete


async def main():
    from platforms.qq import QQAdapter
    from playwright_manager import PlaywrightManager
    from session import session_store
    from _agent_runner import make_message_handler
    from bot_session import BotSession
    from scheduler_service import SchedulerService

    # Shared PlaywrightManager
    pm = PlaywrightManager()
    await pm.start()
    logger.info("PlaywrightManager started")

    # BotSession task queue
    bot_queue = asyncio.Queue()

    # SchedulerService
    scheduler = SchedulerService(bot_task_queue=bot_queue)
    await scheduler.start()

    # QQ adapter
    adapter = QQAdapter(session_store=session_store)
    adapter.on_message = make_message_handler(
        adapter, pm, session_store, scheduler_service=scheduler
    )

    # Result callback
    on_complete = _make_result_callback(adapter)

    # BotSession
    bot = BotSession(
        task_queue=bot_queue,
        pm=pm,
        on_complete=on_complete,
    )

    logger.info("Starting NeoFish QQ bot…")
    await adapter.start()

    tasks = [
        asyncio.create_task(bot.start(), name="bot-session"),
    ]

    try:
        # Wait forever (adapter runs its own task internally)
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        logger.info("Shutting down QQ bot…")
        await bot.stop()
        await scheduler.stop()
        await adapter.stop()
        await pm.stop()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
