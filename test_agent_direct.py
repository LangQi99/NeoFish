"""
Direct agent pipeline test — bypasses QQ/NapCat entirely.
Tests the exact same code path as the QQ bot: _agent_runner → run_agent_loop → LLM.
"""
import sys, io, os, asyncio, logging

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("anthropic").setLevel(logging.DEBUG)

os.environ["ANTHROPIC_BASE_URL"] = "https://julangai.com"
os.environ["MODEL_NAME"] = "claude-haiku-4-5"

from dotenv import load_dotenv
load_dotenv()

async def test():
    from playwright_manager import PlaywrightManager
    from agent import run_agent_loop
    from memory.session_memory import SessionMemory

    pm = PlaywrightManager()
    await pm.start()

    print("=" * 50)
    print("Direct agent test — 'say hello in Chinese'")
    print("=" * 50)

    results = []

    async def send_fn(msg):
        text = msg.get("message", str(msg)) if isinstance(msg, dict) else str(msg)
        results.append(("send", text[:200]))
        print(f"[SEND] {text[:200]}")

    async def request_action(reason, img):
        results.append(("action", reason))
        print(f"[ACTION] {reason}")

    async def send_image(desc, img):
        results.append(("image", desc))
        print(f"[IMAGE] {desc}")

    async def send_file(path, desc):
        results.append(("file", path))
        print(f"[FILE] {path}")

    sm = SessionMemory(session_id="test-direct")

    try:
        await run_agent_loop(
            pm=pm,
            user_instruction="Say hello in Chinese and finish.",
            ws_send_msg=send_fn,
            ws_request_action=request_action,
            ws_send_image=send_image,
            ws_send_file=send_file,
            session_id="test-direct",
            session_memory=sm,
            images=[],
            message_center=None,
            scheduler_service=None,
        )
        print("\nAgent loop completed!")
    except Exception as e:
        print(f"\nAgent loop failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    await pm.stop()

    print("\nResults:")
    for i, (typ, content) in enumerate(results):
        print(f"  [{i}] {typ}: {content[:120]}")

    # Check for success
    success = any("hello" in c.lower() or "你好" in c for _, c in results)
    print(f"\n{'PASS' if success else 'FAIL'}: Agent {'responded' if success else 'did not respond'}")

if __name__ == "__main__":
    asyncio.run(test())
