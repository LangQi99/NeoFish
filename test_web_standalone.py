"""
test_web_standalone.py - Test standalone web mode SchedulerService + BotSession in main.py lifespan.
"""
import sys
import io
import asyncio

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from unittest.mock import AsyncMock, MagicMock, patch


def test_lifespan_creates_scheduler_when_none():
    """When scheduler_service is None, lifespan should create everything."""
    import main

    original_scheduler = main.scheduler_service
    main.scheduler_service = None

    mock_app = MagicMock()

    async def _run():
        with patch("main.pm") as mock_pm:
            mock_pm.start = AsyncMock()
            mock_pm.stop = AsyncMock()

            with patch("main.SchedulerService") as MockScheduler:
                mock_scheduler = MockScheduler.return_value
                mock_scheduler.start = AsyncMock()
                mock_scheduler.stop = AsyncMock()

                with patch("main.BotSession") as MockBot:
                    mock_bot = MockBot.return_value
                    mock_bot.start = AsyncMock()
                    mock_bot.stop = AsyncMock()

                    async with main.lifespan(mock_app):
                        # scheduler_service 已设置
                        assert main.scheduler_service is mock_scheduler

                        # SchedulerService 构造时传入了 Queue
                        MockScheduler.assert_called_once()
                        call_args = MockScheduler.call_args
                        queue_arg = (call_args.kwargs.get("bot_task_queue")
                                     or call_args.args[0])
                        assert isinstance(queue_arg, asyncio.Queue)

                        # BotSession 构造正确
                        MockBot.assert_called_once()
                        bot_kwargs = MockBot.call_args.kwargs
                        assert bot_kwargs["task_queue"] is queue_arg
                        assert bot_kwargs["pm"] is mock_pm
                        assert callable(bot_kwargs["on_complete"])

                        # SchedulerService.start 被 awaited
                        mock_scheduler.start.assert_awaited_once()
                        # BotSession.start 被 create_task 调用（未 awaited）
                        assert mock_bot.start.called

                    # 退出 lifespan 后 stop 被 awaited
                    mock_bot.stop.assert_awaited_once()
                    mock_scheduler.stop.assert_awaited_once()
                    mock_pm.stop.assert_awaited_once()

    asyncio.run(_run())
    main.scheduler_service = original_scheduler
    print("[PASS] test_lifespan_creates_scheduler_when_none")


def test_lifespan_skips_when_already_set():
    """When scheduler_service is already set (by run_all.py), skip creation."""
    import main

    original_scheduler = main.scheduler_service
    fake_scheduler = MagicMock()
    main.scheduler_service = fake_scheduler

    mock_app = MagicMock()

    async def _run():
        with patch("main.pm") as mock_pm:
            mock_pm.start = AsyncMock()
            mock_pm.stop = AsyncMock()

            with patch("main.SchedulerService") as MockScheduler:
                with patch("main.BotSession") as MockBot:
                    async with main.lifespan(mock_app):
                        MockScheduler.assert_not_called()
                        MockBot.assert_not_called()
                        assert main.scheduler_service is fake_scheduler

    asyncio.run(_run())
    main.scheduler_service = original_scheduler
    print("[PASS] test_lifespan_skips_when_already_set")


def test_web_result_callback_format():
    """Test the web result callback formats messages correctly."""
    import main
    from main import _create_web_result_callback

    callback = _create_web_result_callback()
    assert callable(callback)
    assert asyncio.iscoroutinefunction(callback)

    import inspect
    sig = inspect.signature(callback)
    params = list(sig.parameters.keys())
    assert "result" in params
    assert "source_session_id" in params
    assert "source_chat_id" in params
    assert "source_platform" in params
    assert "debug" in params

    print("[PASS] test_web_result_callback_format")


def test_web_result_callback_persists_message():
    """Test that the web result callback actually persists to messages.jsonl."""
    import main
    from main import _create_web_result_callback, _new_session, _delete_session_files, _load_messages_jsonl
    from scheduled_task import BotTaskResult

    # 创建临时 session
    session = _new_session("callback-test")
    sid = session["id"]

    try:
        callback = _create_web_result_callback()

        result = BotTaskResult(
            task_id="t-standalone-001",
            description="web定时测试任务",
            status="success",
            summary="任务执行成功：已生成报告",
            files=["/tmp/test_report.txt"],
            error=None,
        )

        async def _run():
            await callback(result, sid, sid, "web", False)

        asyncio.run(_run())

        # 验证消息已持久化到 messages.jsonl
        msgs = _load_messages_jsonl(sid)
        scheduled_msgs = [
            m for m in msgs
            if m.get("message_key") == "common.scheduled_result"
        ]
        assert len(scheduled_msgs) == 1, f"Expected 1 scheduled_result, got {len(scheduled_msgs)}"
        msg = scheduled_msgs[0]
        assert msg["role"] == "assistant"
        assert msg["params"]["task_id"] == "t-standalone-001"
        assert msg["params"]["status"] == "success"
        assert "web定时测试任务" in msg["content"]
        assert "[OK]" in msg["content"]

        print("[PASS] test_web_result_callback_persists_message")
    finally:
        _delete_session_files(sid)
        # 也清理 index
        if sid in main._session_index:
            del main._session_index[sid]
            main._save_index()


if __name__ == "__main__":
    test_lifespan_creates_scheduler_when_none()
    test_lifespan_skips_when_already_set()
    test_web_result_callback_format()
    test_web_result_callback_persists_message()
    print("\nAll tests passed!")
