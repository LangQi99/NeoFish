"""
E2E test with real LLM: agent calls schedule_task / list / cancel tools
Run: python test_llm_schedule.py
"""

import asyncio
import io
import logging
import os
import sys
import tempfile
from pathlib import Path

# 强制使用 .env 中的 API 配置，覆盖系统环境变量
os.environ["ANTHROPIC_BASE_URL"] = "https://julangai.com"
os.environ["ANTHROPIC_API_KEY"] = "sk-0qOt4UP564mcoJRNsWcKiDGGTVhQxA4WJwl1GeDl5L7Syt7t"
os.environ["MODEL_NAME"] = "claude-haiku-4-5"

# 强制 stdout 使用 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

async def test_schedule_and_list():
    from playwright_manager import PlaywrightManager
    from scheduler_service import SchedulerService
    from agent import run_agent_loop

    pm = PlaywrightManager()
    await pm.start()
    print("[OK] Playwright started")

    queue = asyncio.Queue()
    path = Path(tempfile.mktemp(suffix=".json"))
    svc = SchedulerService(queue, storage_path=path)

    source_meta = {
        "session_id": "real-llm-test",
        "chat_id": "test-chat",
        "platform": "web",
    }

    async def emit(msg):
        text = msg.get("message", str(msg)) if isinstance(msg, dict) else str(msg)
        print(f"  [emit] {text[:200]}")

    async def request_action(reason, img=None):
        print(f"  [action] {reason[:120]}")

    async def emit_image(desc, img):
        pass

    async def emit_file(path, desc):
        pass

    print("=" * 60)
    print("Test 1: schedule_task with real LLM")
    print("=" * 60)

    await run_agent_loop(
        pm=pm,
        user_instruction="帮我创建一个每天早上8点30分的定时任务，任务名称叫「每日早报」，任务是：查询当前系统时间，然后直接调用 finish_task 报告当前时间即可，不需要打开浏览器。",
        ws_send_msg=emit,
        ws_request_action=request_action,
        ws_send_image=emit_image,
        ws_send_file=emit_file,
        session_id="real-llm-test",
        scheduler_service=svc,
        source_meta=source_meta,
    )

    tasks = svc.list_all()
    print(f"\n>>> Tasks in scheduler: {len(tasks)}")
    for t in tasks:
        print(f"    [{t.task_id}] {t.description}")
        print(f"    cron: {t.cron_expr}")
        print(f"    prompt: {t.prompt[:120]}")
    assert len(tasks) >= 1, f"Expected >=1 task, got {len(tasks)}"

    # Test 2: list tasks
    print()
    print("=" * 60)
    print("Test 2: list_scheduled_tasks with real LLM")
    print("=" * 60)

    await run_agent_loop(
        pm=pm,
        user_instruction="列出我所有的定时任务。",
        ws_send_msg=emit,
        ws_request_action=request_action,
        ws_send_image=emit_image,
        ws_send_file=emit_file,
        session_id="real-llm-test",
        scheduler_service=svc,
        source_meta=source_meta,
    )

    # Test 3: cancel task
    task_to_cancel = tasks[0].task_id
    print()
    print("=" * 60)
    print(f"Test 3: cancel_scheduled_task with real LLM (id={task_to_cancel[:8]}...)")
    print("=" * 60)

    await run_agent_loop(
        pm=pm,
        user_instruction=f"取消这个定时任务：{task_to_cancel}",
        ws_send_msg=emit,
        ws_request_action=request_action,
        ws_send_image=emit_image,
        ws_send_file=emit_file,
        session_id="real-llm-test",
        scheduler_service=svc,
        source_meta=source_meta,
    )

    remaining = svc.list_all()
    print(f"\n>>> Tasks remaining: {len(remaining)}")
    assert len(remaining) == 0, f"Expected 0 tasks, got {len(remaining)}"

    print()
    print("=" * 60)
    print("ALL REAL LLM TESTS PASSED")
    print("=" * 60)

    path.unlink(missing_ok=True)
    await pm.stop()


if __name__ == "__main__":
    asyncio.run(test_schedule_and_list())
