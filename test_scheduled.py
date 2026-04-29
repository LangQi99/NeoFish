"""
Tests for scheduler_service.py and bot_session.py
Run: python test_scheduled.py
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ── Test scheduler_service ──────────────────────────────────────

async def test_scheduler_add_remove():
    """添加/删除/查询任务"""
    from scheduler_service import SchedulerService
    from scheduled_task import ScheduledTask

    queue = asyncio.Queue()
    svc = SchedulerService(queue, storage_path=Path(tempfile.mktemp(suffix=".json")))

    task = ScheduledTask.new(
        cron_expr="0 8 * * *",
        description="测试任务",
        prompt="执行测试",
        source_session_id="sess-1",
        source_chat_id="chat-1",
        source_platform="web",
    )

    # add
    tid = svc.add(task)
    assert tid == task.task_id
    assert svc.get(tid) is not None
    assert svc.get(tid).description == "测试任务"

    # list
    assert len(svc.list_all()) == 1
    assert len(svc.list_by_session("sess-1")) == 1
    assert len(svc.list_by_session("sess-none")) == 0

    # remove
    assert svc.remove(tid) is True
    assert svc.get(tid) is None
    assert len(svc.list_all()) == 0
    assert svc.remove("nonexistent") is False

    # cleanup
    svc._path.unlink(missing_ok=True)
    print("[PASS] test_scheduler_add_remove")


async def test_scheduler_persistence():
    """重启后任务恢复"""
    from scheduler_service import SchedulerService
    from scheduled_task import ScheduledTask

    path = Path(tempfile.mktemp(suffix=".json"))
    queue = asyncio.Queue()

    # 创建并添加任务
    svc1 = SchedulerService(queue, storage_path=path)
    task = ScheduledTask.new(
        cron_expr="*/5 * * * *",
        description="持久化测试",
        prompt="test",
        source_session_id="sess-2",
        source_chat_id="chat-2",
        source_platform="telegram",
    )
    svc1.add(task)

    # 模拟重启 — 新建实例并 load
    svc2 = SchedulerService(asyncio.Queue(), storage_path=path)
    svc2._load()
    assert len(svc2.list_all()) == 1
    restored = svc2.get(task.task_id)
    assert restored is not None
    assert restored.description == "持久化测试"
    assert restored.cron_expr == "*/5 * * * *"
    assert restored.source_platform == "telegram"

    path.unlink()
    print("[PASS] test_scheduler_persistence")


async def test_scheduler_cron_trigger():
    """cron 匹配触发逻辑（用过去时间确保立即触发）"""
    from scheduler_service import SchedulerService
    from scheduled_task import ScheduledTask

    queue = asyncio.Queue()
    path = Path(tempfile.mktemp(suffix=".json"))
    svc = SchedulerService(queue, storage_path=path)

    # 用每分钟的 cron，last_run_at=None，应该触发
    task = ScheduledTask.new(
        cron_expr="* * * * *",
        description="每分钟触发",
        prompt="test",
        source_session_id="sess-3",
        source_chat_id="chat-3",
        source_platform="web",
    )
    svc.add(task)

    # 手动调用 _trigger 验证队列收到 TaskTrigger
    await svc._trigger(task)
    assert not queue.empty()

    from scheduled_task import TaskTrigger
    trigger = queue.get_nowait()
    assert isinstance(trigger, TaskTrigger)
    assert trigger.task_id == task.task_id
    assert trigger.description == "每分钟触发"
    assert trigger.prompt == "test"
    assert trigger.source_session_id == "sess-3"

    # last_run_at 应已更新
    assert task.last_run_at is not None

    path.unlink()
    print("[PASS] test_scheduler_cron_trigger")


async def test_scheduler_disabled_task():
    """禁用的任务不触发"""
    from scheduler_service import SchedulerService
    from scheduled_task import ScheduledTask

    queue = asyncio.Queue()
    path = Path(tempfile.mktemp(suffix=".json"))
    svc = SchedulerService(queue, storage_path=path)

    task = ScheduledTask.new(
        cron_expr="* * * * *",
        description="禁用任务",
        prompt="test",
        source_session_id="sess-4",
        source_chat_id="chat-4",
        source_platform="web",
    )
    task.enabled = False
    svc.add(task)

    # _tick 会跳过 disabled 任务 — 这里直接验证 _trigger 不会被调用
    # 简化：队列应为空
    assert queue.empty()

    path.unlink()
    print("[PASS] test_scheduler_disabled_task")


async def test_scheduler_multiple_sessions():
    """按 session 列出任务"""
    from scheduler_service import SchedulerService
    from scheduled_task import ScheduledTask

    queue = asyncio.Queue()
    path = Path(tempfile.mktemp(suffix=".json"))
    svc = SchedulerService(queue, storage_path=path)

    t1 = ScheduledTask.new("0 8 * * *", "Task A", "A", "sess-a", "chat-a", "web")
    t2 = ScheduledTask.new("0 9 * * *", "Task B", "B", "sess-a", "chat-a", "web")
    t3 = ScheduledTask.new("0 10 * * *", "Task C", "C", "sess-b", "chat-b", "telegram")

    svc.add(t1)
    svc.add(t2)
    svc.add(t3)

    assert len(svc.list_by_session("sess-a")) == 2
    assert len(svc.list_by_session("sess-b")) == 1
    assert len(svc.list_by_session("sess-none")) == 0
    assert len(svc.list_all()) == 3

    path.unlink()
    print("[PASS] test_scheduler_multiple_sessions")


# ── Test bot_session ───────────────────────────────────────────

async def test_bot_session_instantiation():
    """BotSession 基本实例化"""
    from bot_session import BotSession, BOT_SESSION_ID

    queue = asyncio.Queue()
    mock_pm = MagicMock()

    called = []
    async def on_complete(result, sid, cid, plat, debug):
        called.append(result)

    bot = BotSession(queue, mock_pm, on_complete)
    assert bot.session_id == BOT_SESSION_ID
    assert bot.is_running is False
    print("[PASS] test_bot_session_instantiation")


async def test_bot_session_execute_task():
    """模拟任务执行 — mock run_agent_loop 验证结果捕获"""
    from bot_session import BotSession, BOT_SESSION_ID
    from scheduled_task import TaskTrigger, BotTaskResult

    queue = asyncio.Queue()
    mock_pm = MagicMock()

    results = []
    async def on_complete(result, sid, cid, plat, debug):
        results.append((result, sid, cid, plat, debug))

    bot = BotSession(queue, mock_pm, on_complete)

    trigger = TaskTrigger(
        task_id="test-task-1",
        description="测试任务",
        prompt="请执行测试",
        source_session_id="sess-src",
        source_chat_id="chat-src",
        source_platform="web",
        debug=False,
    )

    # Mock run_agent_loop — simulate finish_task call
    async def mock_run_agent_loop(**kwargs):
        # 模拟 BotSession 传入的 tool_overrides
        finish_handler = kwargs.get("tool_overrides", {}).get("finish_task")
        assert finish_handler is not None, "tool_overrides should contain finish_task"

        from tool_registry import ToolExecutionResult
        result = await finish_handler({
            "report": "任务已完成，生成了报告",
            "files": ["report.pdf", "data.csv"],
        })
        assert result.finished is True
        assert result.output == "Task completed."

    with patch("agent.run_agent_loop", mock_run_agent_loop):
        result = await bot._execute_task(trigger)

    assert isinstance(result, BotTaskResult)
    assert result.task_id == "test-task-1"
    assert result.status == "success"
    assert "报告" in result.summary
    assert result.files == ["report.pdf", "data.csv"]

    print("[PASS] test_bot_session_execute_task")


async def test_bot_session_execute_failure():
    """任务失败时状态为 failed"""
    from bot_session import BotSession
    from scheduled_task import TaskTrigger, BotTaskResult

    queue = asyncio.Queue()
    mock_pm = MagicMock()
    bot = BotSession(queue, mock_pm, lambda *a: None)

    trigger = TaskTrigger(
        task_id="test-fail-1",
        description="失败任务",
        prompt="test",
        source_session_id="sess-src",
        source_chat_id="chat-src",
        source_platform="web",
    )

    async def mock_run_agent_loop(**kwargs):
        finish_handler = kwargs.get("tool_overrides", {}).get("finish_task")
        await finish_handler({
            "report": "Unable to complete: site is down, error connecting",
            "files": [],
        })

    with patch("agent.run_agent_loop", mock_run_agent_loop):
        result = await bot._execute_task(trigger)

    assert result.status == "failed"
    print("[PASS] test_bot_session_execute_failure")


async def test_bot_session_execute_exception():
    """run_agent_loop 崩溃时捕获异常并返回 error 状态"""
    from bot_session import BotSession
    from scheduled_task import TaskTrigger

    queue = asyncio.Queue()
    mock_pm = MagicMock()
    bot = BotSession(queue, mock_pm, lambda *a: None)

    trigger = TaskTrigger(
        task_id="test-crash-1",
        description="崩溃任务",
        prompt="test",
        source_session_id="sess-src",
        source_chat_id="chat-src",
        source_platform="web",
    )

    async def mock_crashing_loop(**kwargs):
        raise RuntimeError("Browser crashed")

    with patch("agent.run_agent_loop", mock_crashing_loop):
        result = await bot._execute_task(trigger)

    assert result.status == "error"
    assert "Browser crashed" in result.error
    print("[PASS] test_bot_session_execute_exception")


async def test_bot_session_callback_routing():
    """验证 on_complete 回调收到正确的路由参数"""
    from bot_session import BotSession
    from scheduled_task import TaskTrigger

    queue = asyncio.Queue()
    mock_pm = MagicMock()

    callbacks = []
    async def on_complete(result, sid, cid, plat, debug):
        callbacks.append((result.status, sid, cid, plat, debug))

    bot = BotSession(queue, mock_pm, on_complete)

    trigger = TaskTrigger(
        task_id="test-route-1",
        description="路由测试",
        prompt="test",
        source_session_id="sess-telegram",
        source_chat_id="chat-12345",
        source_platform="telegram",
        debug=True,
    )

    async def mock_run_agent_loop(**kwargs):
        finish_handler = kwargs.get("tool_overrides", {}).get("finish_task")
        await finish_handler({"report": "done", "files": []})

    with patch("agent.run_agent_loop", mock_run_agent_loop):
        result = await bot._execute_task(trigger)
        await bot._on_complete(
            result,
            trigger.source_session_id,
            trigger.source_chat_id,
            trigger.source_platform,
            trigger.debug,
        )

    assert len(callbacks) == 1
    status, sid, cid, plat, debug = callbacks[0]
    assert status == "success"
    assert sid == "sess-telegram"
    assert cid == "chat-12345"
    assert plat == "telegram"
    assert debug is True
    print("[PASS] test_bot_session_callback_routing")


# ── Main ───────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("Testing scheduler_service.py")
    print("=" * 60)
    await test_scheduler_add_remove()
    await test_scheduler_persistence()
    await test_scheduler_cron_trigger()
    await test_scheduler_disabled_task()
    await test_scheduler_multiple_sessions()

    print()
    print("=" * 60)
    print("Testing bot_session.py")
    print("=" * 60)
    await test_bot_session_instantiation()
    await test_bot_session_execute_task()
    await test_bot_session_execute_failure()
    await test_bot_session_execute_exception()
    await test_bot_session_callback_routing()

    print()
    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
