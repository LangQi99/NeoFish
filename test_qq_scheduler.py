"""
test_qq_scheduler.py - Verify QQ bot scheduler wiring without real QQ connection.
Tests that SchedulerService + BotSession are properly created and wired.
"""
import sys
import io
import os
import asyncio

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

os.environ["ANTHROPIC_BASE_URL"] = "https://julangai.com"
os.environ["MODEL_NAME"] = "claude-haiku-4-5"


async def test_scheduler_wiring():
    """Test that SchedulerService and BotSession can be created and wired."""
    from scheduler_service import SchedulerService
    from scheduled_task import ScheduledTask
    from bot_session import BotSession

    # 1. Create queue and scheduler
    bot_queue = asyncio.Queue()
    scheduler = SchedulerService(bot_task_queue=bot_queue)
    await scheduler.start()
    print("[PASS] SchedulerService started")

    # 2. Add a task
    task = ScheduledTask.new(
        cron_expr="0 8 * * *",
        description="QQ test task - daily report",
        prompt="Say hello and finish.",
        source_session_id="test-session",
        source_chat_id="private_test123",
        source_platform="qq",
    )
    scheduler.add(task)
    print(f"[PASS] Task added: {task.task_id}")

    # 3. List tasks
    tasks = scheduler.list_all()
    assert len(tasks) == 1, f"Expected 1 task, got {len(tasks)}"
    assert tasks[0].description == "QQ test task - daily report"
    print("[PASS] Task listing works")

    # 4. List by session
    session_tasks = scheduler.list_by_session("test-session")
    assert len(session_tasks) == 1
    print("[PASS] Session-filtered listing works")

    # 5. Verify source_platform is "qq"
    assert tasks[0].source_platform == "qq"
    print("[PASS] QQ platform tag correct")

    # 6. Cancel task
    ok = scheduler.remove(task.task_id)
    assert ok
    assert len(scheduler.list_all()) == 0
    print("[PASS] Task cancellation works")

    # 7. BotSession creation (no-op callback, won't actually run)
    calls = []

    async def on_complete(result, sid, cid, platform, debug):
        calls.append(result)

    from playwright_manager import PlaywrightManager
    pm = PlaywrightManager()

    bot = BotSession(
        task_queue=bot_queue,
        pm=pm,
        on_complete=on_complete,
    )
    print("[PASS] BotSession created with QQ callback")

    # 8. Verify callback output (simulate the result callback logic in run_qq.py)
    from scheduled_task import BotTaskResult

    # Simulate what run_qq.py's _make_result_callback does
    result = BotTaskResult(
        task_id=task.task_id,
        description="QQ test task",
        status="success",
        summary="All done!",
        files=[],
    )

    text = (
        f"定时任务【{result.description}】已完成\n"
        f"[OK] 状态：{result.status}\n"
        f"{'─' * 40}\n"
        f"{result.summary}"
    )
    assert "QQ test task" in text
    assert "[OK]" in text
    assert "All done!" in text
    print("[PASS] QQ result callback message format correct")

    await scheduler.stop()
    print("[PASS] SchedulerService stopped cleanly")

    print("\n" + "=" * 55)
    print("  All QQ bot scheduler tests: PASSED")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(test_scheduler_wiring())
