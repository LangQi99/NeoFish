"""
Tests for planner.py PlanManager
Run: python test_planner.py
"""

import tempfile
from pathlib import Path

from planner import PlanManager


def _new_manager() -> PlanManager:
    return PlanManager(plan_dir=Path(tempfile.mkdtemp()))


def test_write_assigns_sequential_ids():
    pm = _new_manager()
    pm.write(
        steps=[{"content": "a"}, {"content": "b", "status": "in_progress"}],
        goal="demo goal",
        title="demo",
    )
    plan = pm.get_plan()
    assert [s["id"] for s in plan["steps"]] == [1, 2]
    assert plan["steps"][0]["status"] == "pending"
    assert plan["steps"][1]["status"] == "in_progress"
    assert plan["goal"] == "demo goal"
    assert plan["title"] == "demo"
    assert pm.path.exists()
    print("[PASS] test_write_assigns_sequential_ids")


def test_write_overwrites_existing():
    pm = _new_manager()
    pm.write(steps=[{"content": "a"}, {"content": "b"}, {"content": "c"}])
    pm.write(steps=[{"content": "only"}])
    plan = pm.get_plan()
    assert len(plan["steps"]) == 1
    assert plan["steps"][0]["content"] == "only"
    assert plan["steps"][0]["id"] == 1
    print("[PASS] test_write_overwrites_existing")


def test_write_normalizes_invalid_status():
    pm = _new_manager()
    pm.write(steps=[{"content": "a", "status": "bogus"}])
    assert pm.get_plan()["steps"][0]["status"] == "pending"
    print("[PASS] test_write_normalizes_invalid_status")


def test_update_step():
    pm = _new_manager()
    pm.write(steps=[{"content": "a"}, {"content": "b"}])
    pm.update_step(1, status="completed")
    pm.update_step(2, content="b2")
    plan = pm.get_plan()
    assert plan["steps"][0]["status"] == "completed"
    assert plan["steps"][1]["content"] == "b2"

    err = pm.update_step(1, status="bogus")
    assert "invalid status" in err
    missing = pm.update_step(99, status="completed")
    assert "not found" in missing
    print("[PASS] test_update_step")


def test_mark_all_and_pause():
    pm = _new_manager()
    pm.write(
        steps=[
            {"content": "a", "status": "in_progress"},
            {"content": "b", "status": "pending"},
        ]
    )
    pm.pause()
    assert all(s["status"] == "pending" for s in pm.get_plan()["steps"])

    pm.update_step(1, status="in_progress")
    pm.mark_all("completed")
    assert all(s["status"] == "completed" for s in pm.get_plan()["steps"])
    print("[PASS] test_mark_all_and_pause")


def test_set_goal_and_render():
    pm = _new_manager()
    assert pm.render() == "No plan yet."
    pm.set_goal("the goal", title="t")
    pm.write(steps=[{"content": "step one", "status": "completed"}])
    rendered = pm.render()
    assert "Goal: the goal" in rendered
    assert "[x] #1 step one" in rendered
    print("[PASS] test_set_goal_and_render")


def test_clear():
    pm = _new_manager()
    pm.write(steps=[{"content": "a"}], goal="g")
    pm.clear()
    plan = pm.get_plan()
    assert plan["steps"] == []
    assert plan["goal"] == ""
    print("[PASS] test_clear")


def main():
    print("=" * 60)
    print("Testing planner.py PlanManager")
    print("=" * 60)
    test_write_assigns_sequential_ids()
    test_write_overwrites_existing()
    test_write_normalizes_invalid_status()
    test_update_step()
    test_mark_all_and_pause()
    test_set_goal_and_render()
    test_clear()
    print()
    print("=" * 60)
    print("All planner.py tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
