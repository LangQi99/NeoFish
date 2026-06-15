"""
Tests for platform-specific quiet message filtering.
Run: python test_agent_runner_quiet_mode.py
"""

import _agent_runner as runner


def test_qq_quiet_mode_suppresses_progress_messages():
    old_value = runner.QQ_QUIET_MODE
    runner.QQ_QUIET_MODE = True
    try:
        assert runner._should_suppress_message_for_platform(
            {"message_key": "common.executing_action", "message": "Executing action: `click`"},
            "qq",
        )
        assert runner._should_suppress_message_for_platform(
            {"message": "Agent is thinking..."},
            "qq",
        )
    finally:
        runner.QQ_QUIET_MODE = old_value

    print("[PASS] test_qq_quiet_mode_suppresses_progress_messages")


def test_qq_quiet_mode_keeps_final_messages():
    old_value = runner.QQ_QUIET_MODE
    runner.QQ_QUIET_MODE = True
    try:
        assert not runner._should_suppress_message_for_platform(
            {
                "message_key": "common.task_completed",
                "message": "Task completed",
                "params": {"report": "done"},
            },
            "qq",
        )
        assert not runner._should_suppress_message_for_platform(
            {"message_key": "common.error", "message": "Something failed"},
            "qq",
        )
    finally:
        runner.QQ_QUIET_MODE = old_value

    print("[PASS] test_qq_quiet_mode_keeps_final_messages")


def test_quiet_mode_does_not_affect_other_platforms():
    old_value = runner.QQ_QUIET_MODE
    runner.QQ_QUIET_MODE = True
    try:
        assert not runner._should_suppress_message_for_platform(
            {"message_key": "common.executing_action", "message": "Executing action: `click`"},
            "telegram",
        )
    finally:
        runner.QQ_QUIET_MODE = old_value

    print("[PASS] test_quiet_mode_does_not_affect_other_platforms")


if __name__ == "__main__":
    test_qq_quiet_mode_suppresses_progress_messages()
    test_qq_quiet_mode_keeps_final_messages()
    test_quiet_mode_does_not_affect_other_platforms()
    print("[PASS] all quiet mode tests")
