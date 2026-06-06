"""
Tests for agent.py scheduled task tools
Run: python test_agent_tools.py
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


async def test_tool_registry_handlers_registered():
    """验证 3 个工具 handler 已在 _create_tool_registry 中注册"""
    from agent import _create_tool_registry
    from tool_registry import ToolRegistry

    mock_pm = MagicMock()
    mock_page = MagicMock()

    async def noop(*args, **kwargs):
        pass

    registry = _create_tool_registry(
        pm=mock_pm,
        page=mock_page,
        effective_session_id="test-sess",
        auto_plan=None,
        emit_info=noop,
        emit_action_required=noop,
        emit_image=noop,
        emit_file=noop,
    )

    # 验证 3 个工具 handler 存在
    for name in ["schedule_task", "list_scheduled_tasks", "cancel_scheduled_task"]:
        result = await registry.execute(name, {})
        assert "SchedulerService is not available" in result.output or \
               "SchedulerService not available" in result.output, \
               f"{name}: expected 'not available' message, got: {result.output}"

    print("[PASS] test_tool_registry_handlers_registered")


async def test_schedule_task_adds_and_lists():
    """schedule_task 添加任务，list_scheduled_tasks 列出"""
    from agent import _create_tool_registry
    from scheduler_service import SchedulerService
    from scheduled_task import ScheduledTask

    queue = asyncio.Queue()
    path = Path(tempfile.mktemp(suffix=".json"))
    svc = SchedulerService(queue, storage_path=path)

    mock_pm = MagicMock()
    mock_page = MagicMock()

    async def noop(*args, **kwargs):
        pass

    registry = _create_tool_registry(
        pm=mock_pm,
        page=mock_page,
        effective_session_id="sess-web",
        auto_plan=None,
        emit_info=noop,
        emit_action_required=noop,
        emit_image=noop,
        emit_file=noop,
        scheduler_service=svc,
        source_meta={"session_id": "sess-web", "chat_id": "chat-web", "platform": "web"},
    )

    # schedule_task
    result = await registry.execute("schedule_task", {
        "cron": "0 8 * * *",
        "prompt": "请打开B站生成每日报告",
        "description": "每日B站报告",
        "debug": False,
    })
    assert "已添加定时任务" in result.output
    assert "每日B站报告" in result.output
    assert "0 8 * * *" in result.output

    # 提取 task_id
    tasks = svc.list_all()
    assert len(tasks) == 1
    task_id = tasks[0].task_id
    assert tasks[0].source_session_id == "sess-web"
    assert tasks[0].source_platform == "web"

    # list_scheduled_tasks — 不需要传 args
    result = await registry.execute("list_scheduled_tasks", {})
    assert "每日B站报告" in result.output
    assert task_id in result.output
    assert "0 8 * * *" in result.output

    # 清理
    path.unlink(missing_ok=True)
    print("[PASS] test_schedule_task_adds_and_lists")


async def test_cancel_scheduled_task():
    """cancel_scheduled_task 删除任务"""
    from agent import _create_tool_registry
    from scheduler_service import SchedulerService
    from scheduled_task import ScheduledTask

    queue = asyncio.Queue()
    path = Path(tempfile.mktemp(suffix=".json"))
    svc = SchedulerService(queue, storage_path=path)

    task = ScheduledTask.new(
        cron_expr="*/5 * * * *",
        description="测试取消",
        prompt="test",
        source_session_id="sess-x",
        source_chat_id="chat-x",
        source_platform="telegram",
    )
    svc.add(task)

    mock_pm = MagicMock()
    mock_page = MagicMock()

    async def noop(*args, **kwargs):
        pass

    registry = _create_tool_registry(
        pm=mock_pm,
        page=mock_page,
        effective_session_id="sess-x",
        auto_plan=None,
        emit_info=noop,
        emit_action_required=noop,
        emit_image=noop,
        emit_file=noop,
        scheduler_service=svc,
        source_meta={"session_id": "sess-x", "chat_id": "chat-x", "platform": "telegram"},
    )

    # 取消
    result = await registry.execute("cancel_scheduled_task", {"task_id": task.task_id})
    assert "已取消" in result.output
    assert len(svc.list_all()) == 0

    # 取消不存在的
    result = await registry.execute("cancel_scheduled_task", {"task_id": "nonexistent"})
    assert "未找到" in result.output

    path.unlink(missing_ok=True)
    print("[PASS] test_cancel_scheduled_task")


async def test_schedule_task_without_source_meta_fallback():
    """source_meta=None 时 fallback 到 effective_session_id"""
    from agent import _create_tool_registry
    from scheduler_service import SchedulerService

    queue = asyncio.Queue()
    path = Path(tempfile.mktemp(suffix=".json"))
    svc = SchedulerService(queue, storage_path=path)

    mock_pm = MagicMock()
    mock_page = MagicMock()

    async def noop(*args, **kwargs):
        pass

    registry = _create_tool_registry(
        pm=mock_pm,
        page=mock_page,
        effective_session_id="fallback-sess",
        auto_plan=None,
        emit_info=noop,
        emit_action_required=noop,
        emit_image=noop,
        emit_file=noop,
        scheduler_service=svc,
        source_meta=None,  # ← 无 source_meta
    )

    result = await registry.execute("schedule_task", {
        "cron": "0 12 * * *",
        "prompt": "中午检查",
        "description": "午间任务",
    })

    assert "已添加定时任务" in result.output
    task = svc.list_all()[0]
    assert task.source_session_id == "fallback-sess"   # fallback
    assert task.source_platform == "web"               # default

    path.unlink(missing_ok=True)
    print("[PASS] test_schedule_task_without_source_meta_fallback")


async def test_finish_task_files_in_schema():
    """finish_task 工具 schema 包含 files 参数"""
    from agent import TOOLS

    ft = [t for t in TOOLS if t["name"] == "finish_task"][0]
    props = ft["input_schema"]["properties"]

    assert "files" in props
    assert props["files"]["type"] == "array"
    assert props["files"]["items"]["type"] == "string"
    assert "report" in props  # 原有参数不受影响
    assert "report" in ft["input_schema"]["required"]

    print("[PASS] test_finish_task_files_in_schema")


async def test_no_scheduler_service_returns_error():
    """scheduler_service=None 时所有 3 个工具返回错误提示"""
    from agent import _create_tool_registry

    mock_pm = MagicMock()
    mock_page = MagicMock()

    async def noop(*args, **kwargs):
        pass

    registry = _create_tool_registry(
        pm=mock_pm,
        page=mock_page,
        effective_session_id="sess",
        auto_plan=None,
        emit_info=noop,
        emit_action_required=noop,
        emit_image=noop,
        emit_file=noop,
        scheduler_service=None,  # ← 没有 scheduler
    )

    r1 = await registry.execute("schedule_task", {"cron": "* * * * *", "prompt": "x", "description": "x"})
    assert "not available" in r1.output.lower()

    r2 = await registry.execute("list_scheduled_tasks", {})
    assert "not available" in r2.output.lower()

    r3 = await registry.execute("cancel_scheduled_task", {"task_id": "x"})
    assert "not available" in r3.output.lower()

    print("[PASS] test_no_scheduler_service_returns_error")


async def main():
    print("=" * 60)
    print("Testing agent.py scheduled task tools")
    print("=" * 60)
    await test_tool_registry_handlers_registered()
    await test_schedule_task_adds_and_lists()
    await test_cancel_scheduled_task()
    await test_schedule_task_without_source_meta_fallback()
    await test_finish_task_files_in_schema()
    await test_no_scheduler_service_returns_error()
    print()
    print("=" * 60)
    print("All agent.py tool tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
