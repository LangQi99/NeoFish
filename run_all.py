"""
run_all.py - Launch all NeoFish platform adapters + BotSession + SchedulerService.

Run with:
    python run_all.py

Which platforms are started depends on which tokens / URLs are configured:
    - Web        — always started (FastAPI on WEB_HOST:WEB_PORT)
    - Telegram   — started when TELEGRAM_BOT_TOKEN is set
    - QQ         — started when QQ_WS_URL is set

Environment variables are loaded from .env automatically.
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

# ── 全局适配器注册表（方案 B）───────────────────────────────────

platform_adapters: dict = {}


# ── 结果回调工厂 ────────────────────────────────────────────────

def _make_result_callback(session_store, message_bus):
    """创建 BotSession 的结果回调，按平台路由。"""

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

        # 按平台路由
        if source_platform == "telegram":
            tg = platform_adapters.get("telegram")
            if tg:
                try:
                    await tg.send_message(source_session_id, text)
                    for f in result.files:
                        try:
                            await tg.send_file(source_session_id, f, "")
                        except Exception:
                            logger.exception("Failed to send file %s via Telegram", f)
                except Exception:
                    logger.exception("Telegram result callback failed")

        elif source_platform == "web":
            # Web：直接写入 session 的 messages.jsonl
            from main import _append_message_jsonl
            msg = {
                "role": "assistant",
                "content": text,
                "timestamp": datetime.now().isoformat(),
                "message_key": "common.scheduled_result",
                "params": {
                    "task_id": result.task_id,
                    "description": result.description,
                    "status": result.status,
                    "summary": result.summary,
                    "files": result.files,
                },
            }
            try:
                _append_message_jsonl(source_session_id, msg)
                logger.info("Scheduled result persisted for web session %s", source_session_id)
            except Exception:
                logger.exception("Failed to persist scheduled result for web")

        elif source_platform == "qq":
            qq = platform_adapters.get("qq")
            if qq:
                try:
                    await qq.send_message(source_session_id, text)
                    for f in result.files:
                        try:
                            await qq.send_file(source_session_id, f, "")
                        except Exception:
                            logger.exception("Failed to send file %s via QQ", f)
                except Exception:
                    logger.exception("QQ result callback failed")

        else:
            logger.warning("Unknown source_platform for result: %s", source_platform)

    return on_bot_task_complete


# ── 平台启动函数 ────────────────────────────────────────────────

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
    logger.info("Starting Web adapter on %s:%d ...", WEB_HOST, WEB_PORT)
    await server.serve()


async def _run_telegram(pm, session_store, scheduler_service):
    """Start the Telegram bot adapter using shared PlaywrightManager."""
    from config import TELEGRAM_BOT_TOKEN
    if not TELEGRAM_BOT_TOKEN:
        logger.info("Telegram adapter skipped (TELEGRAM_BOT_TOKEN not set).")
        return

    from platforms.telegram import TelegramAdapter
    from _agent_runner import make_message_handler

    adapter = TelegramAdapter(session_store=session_store)
    adapter.on_message = make_message_handler(
        adapter, pm, session_store, scheduler_service=scheduler_service
    )
    platform_adapters["telegram"] = adapter

    logger.info("Starting Telegram adapter ...")
    await adapter.start()

    try:
        await asyncio.Event().wait()
    finally:
        await adapter.stop()


async def _run_qq(pm, session_store, scheduler_service):
    """Start the QQ bot adapter using shared PlaywrightManager."""
    from config import QQ_WS_URL
    if not QQ_WS_URL:
        logger.info("QQ adapter skipped (QQ_WS_URL not set).")
        return

    from platforms.qq import QQAdapter
    from _agent_runner import make_message_handler

    adapter = QQAdapter(session_store=session_store)
    adapter.on_message = make_message_handler(
        adapter, pm, session_store, scheduler_service=scheduler_service
    )
    platform_adapters["qq"] = adapter

    logger.info("Starting QQ adapter ...")
    await adapter.start()

    try:
        await asyncio.Event().wait()
    finally:
        await adapter.stop()


# ── Main ────────────────────────────────────────────────────────

async def main():
    from playwright_manager import PlaywrightManager
    from session import session_store
    from bot_session import BotSession
    from scheduler_service import SchedulerService
    from message_center import message_bus

    # 共享的 PlaywrightManager
    pm = PlaywrightManager()
    await pm.start()
    logger.info("PlaywrightManager started")

    # 创建 BotSession 的任务队列
    bot_queue = asyncio.Queue()

    # 启动 SchedulerService
    scheduler = SchedulerService(bot_task_queue=bot_queue)
    await scheduler.start()

    # 注入到 main.py，使 Web 端也能使用定时任务
    import main
    main.scheduler_service = scheduler

    # 创建结果回调（使用全局 platform_adapters 字典）
    on_complete = _make_result_callback(session_store, message_bus)

    # 创建 BotSession
    bot = BotSession(
        task_queue=bot_queue,
        pm=pm,
        on_complete=on_complete,
    )

    # 并行启动所有组件
    tasks = [
        asyncio.create_task(_run_web(), name="web"),
        asyncio.create_task(_run_telegram(pm, session_store, scheduler), name="telegram"),
        asyncio.create_task(_run_qq(pm, session_store, scheduler), name="qq"),
        asyncio.create_task(bot.start(), name="bot-session"),
    ]

    logger.info("All components started")

    try:
        await asyncio.gather(*tasks)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down ...")
        await bot.stop()
        await scheduler.stop()
        await pm.stop()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
