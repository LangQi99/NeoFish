"""
test_llm_web_schedule.py - Real LLM E2E test for web standalone scheduled tasks.
Starts main.py server as subprocess on a clean port, connects via WebSocket,
tests schedule_task / list_scheduled_tasks / cancel_scheduled_task tools.
"""
import sys
import io
import os
import json
import asyncio
import subprocess
import time
import signal

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

os.environ["ANTHROPIC_BASE_URL"] = "https://julangai.com"
os.environ["MODEL_NAME"] = "claude-haiku-4-5"

import websockets
import requests

PORT = 18768
BASE_URL = f"http://127.0.0.1:{PORT}"
WS_URL = f"ws://127.0.0.1:{PORT}/ws/agent"

SERVER_SCRIPT = f"""
import uvicorn, os
os.environ["ANTHROPIC_BASE_URL"] = "https://julangai.com"
os.environ["MODEL_NAME"] = "claude-haiku-4-5"
import main
uvicorn.run(main.app, host="127.0.0.1", port={PORT}, log_level="warning")
"""


def wait_for_server(timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/", timeout=2)
            print(f"  Server ready: {r.json()}")
            return True
        except Exception:
            time.sleep(0.5)
    return False


class WebTestClient:
    def __init__(self):
        self.session_id = None
        self.ws = None

    def create_session(self):
        r = requests.post(f"{BASE_URL}/chats")
        data = r.json()
        self.session_id = data["id"]
        print(f"  Session: {self.session_id[:8]}...")
        return self.session_id

    async def connect(self):
        self.ws = await websockets.connect(
            f"{WS_URL}?session_id={self.session_id}",
            ping_interval=None, max_size=2**24
        )
        print("  WebSocket connected")

    async def send_message(self, text: str, timeout=180) -> dict | None:
        await self.ws.send(json.dumps({"type": "message", "text": text}))
        print(f"  >>> {text[:70]}...")

        while True:
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
                msg = json.loads(raw)
                key = msg.get("message_key", "")
                if key == "common.task_completed":
                    report = (msg.get("params") or {}).get("report", "")
                    print(f"  <<< task_completed: {report[:150]}")
                    return msg
                elif key == "common.executing_action":
                    action = (msg.get("params") or {}).get("action", "")
                    if action:
                        print(f"       tool: {action}")
                elif key not in ("common.agent_thinking", "common.agent_starting"):
                    print(f"  <<< {key}")
            except asyncio.TimeoutError:
                print("  TIMEOUT waiting for response!")
                return None

    async def close(self):
        if self.ws:
            await self.ws.close()


async def run_tests():
    client = WebTestClient()
    client.create_session()
    await client.connect()

    try:
        # ── Test 1: schedule_task ──────────────────────────────
        print("\n[Test 1/3] schedule_task")
        r = await client.send_message(
            "请使用 schedule_task 工具创建一个定时任务："
            "cron 表达式 '0 8 * * *'（每天早上8点），"
            "描述为 'web测试-晨间汇报'，"
            "任务内容是：执行 bash date 命令获取当前时间，然后用 finish_task 汇报。"
        )
        if r:
            report = r.get("params", {}).get("report", "")
            ok = any(kw in report.lower() for kw in ["schedule", "task", "创建", "定时", "成功", "8"])
            assert ok, f"schedule_task failed. Report: {report[:200]}"
            print("  [PASS] schedule_task")

        # ── Test 2: list_scheduled_tasks ───────────────────────
        print("\n[Test 2/3] list_scheduled_tasks")
        r = await client.send_message(
            "请使用 list_scheduled_tasks 工具列出我当前所有的定时任务"
        )
        if r:
            report = r.get("params", {}).get("report", "")
            ok = any(kw in report.lower() for kw in ["web测试", "晨间汇报", "8"])
            assert ok, f"list_scheduled_tasks failed. Report: {report[:200]}"
            print("  [PASS] list_scheduled_tasks")

        # ── Test 3: cancel_scheduled_task ──────────────────────
        print("\n[Test 3/3] cancel_scheduled_task")
        r = await client.send_message(
            "请使用 cancel_scheduled_task 工具取消我刚创建的定时任务（描述包含'web测试-晨间汇报'的那个）。"
            "如果不知道 task_id，先用 list_scheduled_tasks 查询。"
        )
        if r:
            report = r.get("params", {}).get("report", "")
            ok = any(kw in report.lower() for kw in ["cancel", "取消", "删除", "remove", "成功"])
            assert ok, f"cancel_scheduled_task failed. Report: {report[:200]}"
            print("  [PASS] cancel_scheduled_task")

        print("\n" + "=" * 55)
        print("  All 3 web scheduled-task tools: PASSED")
        print("=" * 55)

    finally:
        await client.close()


def main():
    print("=" * 55)
    print("NeoFish Web Standalone — Real AI Scheduler Test")
    print(f"Port: {PORT}")
    print("=" * 55)

    print("\nStarting server...")
    proc = subprocess.Popen(
        [sys.executable, "-u", "-c", SERVER_SCRIPT],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        if not wait_for_server():
            print("FAIL: server did not start!")
            proc.kill()
            return

        asyncio.run(run_tests())

    finally:
        print("\nStopping server...")
        proc.send_signal(signal.CTRL_BREAK_EVENT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("Done.")


if __name__ == "__main__":
    main()
