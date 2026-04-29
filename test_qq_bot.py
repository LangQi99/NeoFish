"""
test_qq_bot.py - QQ bot integration tests.

Runs multiple checks:
  1. Module loading & import verification
  2. Adapter initialization (no WS connection needed)
  3. Message parsing (_dispatch logic)
  4. API call serialization (_call_api payload format)
  5. NapCat connectivity test (if server is running)
"""
import sys
import io
import os
import json
import asyncio

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

os.environ["ANTHROPIC_BASE_URL"] = "https://julangai.com"
os.environ["MODEL_NAME"] = "claude-haiku-4-5"

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from dotenv import load_dotenv
load_dotenv()


# ═══════════════════════════════════════════════════════════════
# Test 1: Module loading
# ═══════════════════════════════════════════════════════════════

def test_imports():
    """Verify all QQ adapter dependencies import correctly."""
    from platforms.qq import QQAdapter, _parse_target, _build_image_segment
    from config import QQ_WS_URL, QQ_ACCESS_TOKEN, QQ_ALLOWED_IDS
    from session import SessionStore

    assert QQ_WS_URL == "ws://127.0.0.1:3001"
    assert QQ_ACCESS_TOKEN == "483FcqWsABmkqsjs"
    assert QQ_ALLOWED_IDS == ["private_642476404"]
    print("[PASS] Imports & config loaded")
    return SessionStore()


# ═══════════════════════════════════════════════════════════════
# Test 2: Adapter initialization
# ═══════════════════════════════════════════════════════════════

def test_adapter_init(session_store):
    """QQAdapter constructs without errors."""
    from platforms.qq import QQAdapter

    adapter = QQAdapter(
        session_store=session_store,
        ws_url="ws://127.0.0.1:3001",
        access_token="test-token",
        allowed_ids=["private_642476404"],
    )
    assert adapter._ws_url == "ws://127.0.0.1:3001"
    assert adapter._access_token == "test-token"
    assert adapter._allowed == {"private_642476404"}
    assert adapter._session_store is session_store
    assert adapter._pending_calls == {}
    assert adapter._echo_counter == 0
    assert adapter._running is False
    print("[PASS] QQAdapter init")


# ═══════════════════════════════════════════════════════════════
# Test 3: Helper functions
# ═══════════════════════════════════════════════════════════════

def test_parse_target():
    """_parse_target correctly splits group_/private_ prefixes."""
    from platforms.qq import _parse_target

    assert _parse_target("group_123456") == ("group", "123456")
    assert _parse_target("private_789012") == ("private", "789012")
    assert _parse_target("bare_id") == ("private", "bare_id")  # fallback
    print("[PASS] _parse_target")


def test_build_image_segment():
    """_build_image_segment handles URL, data: URL, and raw base64."""
    from platforms.qq import _build_image_segment

    # HTTP URL
    seg = _build_image_segment("http://example.com/img.png")
    assert seg == {"type": "image", "data": {"file": "http://example.com/img.png"}}

    # data: URL
    seg = _build_image_segment("data:image/png;base64,abc123")
    assert seg == {"type": "image", "data": {"file": "base64://abc123"}}

    # Raw base64 (fallback)
    seg = _build_image_segment("Zm9vYmFy")
    assert seg == {"type": "image", "data": {"file": "base64://Zm9vYmFy"}}

    print("[PASS] _build_image_segment")


# ═══════════════════════════════════════════════════════════════
# Test 4: Message dispatch (unit — no WS needed)
# ═══════════════════════════════════════════════════════════════

def test_dispatch_private_message(session_store):
    """_dispatch handles a private message event."""
    from platforms.qq import QQAdapter

    adapter = QQAdapter(
        session_store=session_store,
        ws_url="ws://127.0.0.1:3001",
    )
    received = []

    async def handler(msg):
        received.append(msg)

    adapter.on_message = handler

    event = json.dumps({
        "post_type": "message",
        "message_type": "private",
        "user_id": 642476404,
        "message": [
            {"type": "text", "data": {"text": "你好，测试消息"}},
        ],
    })

    asyncio.run(adapter._dispatch(event))

    assert len(received) == 1
    msg = received[0]
    assert msg.platform == "qq"
    assert msg.user_id == "642476404"
    assert msg.text == "你好，测试消息"
    assert "private_642476404" in msg.session_id or session_store.get("qq", "private_642476404") is not None
    print("[PASS] _dispatch private message")


def test_dispatch_group_message(session_store):
    """_dispatch handles a group message event."""
    from platforms.qq import QQAdapter

    adapter = QQAdapter(
        session_store=session_store,
        ws_url="ws://127.0.0.1:3001",
        allowed_ids=[],  # empty = allow all for test
    )
    received = []

    async def handler(msg):
        received.append(msg)

    adapter.on_message = handler

    event = json.dumps({
        "post_type": "message",
        "message_type": "group",
        "user_id": 111222,
        "group_id": 987654,
        "message": [
            {"type": "text", "data": {"text": "群消息测试"}},
        ],
    })

    asyncio.run(adapter._dispatch(event))

    assert len(received) == 1
    msg = received[0]
    assert msg.platform == "qq"
    assert msg.user_id == "111222"
    assert msg.text == "群消息测试"
    print("[PASS] _dispatch group message")


def test_dispatch_api_response(session_store):
    """_dispatch handles API call responses (echo correlation)."""
    from platforms.qq import QQAdapter

    adapter = QQAdapter(
        session_store=session_store,
        ws_url="ws://127.0.0.1:3001",
    )

    loop = asyncio.new_event_loop()
    future = loop.create_future()
    adapter._pending_calls["42"] = future

    response = json.dumps({
        "echo": "42",
        "status": "ok",
        "data": {"message_id": 999888},
    })

    asyncio.run(adapter._dispatch(response))

    assert future.done()
    result = future.result()
    assert result["status"] == "ok"
    assert result["data"]["message_id"] == 999888
    assert "42" not in adapter._pending_calls  # cleaned up
    print("[PASS] _dispatch API response echo")


def test_dispatch_image_message(session_store):
    """_dispatch extracts image attachments."""
    from platforms.qq import QQAdapter

    adapter = QQAdapter(
        session_store=session_store,
        ws_url="ws://127.0.0.1:3001",
    )
    received = []

    async def handler(msg):
        received.append(msg)

    adapter.on_message = handler

    event = json.dumps({
        "post_type": "message",
        "message_type": "private",
        "user_id": 642476404,
        "message": [
            {"type": "text", "data": {"text": "看这张图"}},
            {"type": "image", "data": {"url": "http://example.com/photo.jpg", "file": "photo.jpg"}},
        ],
    })

    asyncio.run(adapter._dispatch(event))

    assert len(received) == 1
    msg = received[0]
    assert msg.text == "看这张图"
    assert len(msg.attachments) == 1
    assert msg.attachments[0][0] == "qq_image.jpg"
    assert "http://example.com/photo.jpg" in msg.attachments[0][1]
    print("[PASS] _dispatch image attachment")


def test_dispatch_access_control(session_store):
    """_dispatch rejects messages from non-allowed IDs."""
    from platforms.qq import QQAdapter

    adapter = QQAdapter(
        session_store=session_store,
        ws_url="ws://127.0.0.1:3001",
        allowed_ids=["private_642476404"],  # only this user
    )
    received = []

    async def handler(msg):
        received.append(msg)

    adapter.on_message = handler

    # Message from a blocked user
    event = json.dumps({
        "post_type": "message",
        "message_type": "private",
        "user_id": 999999,  # not in allowed list
        "message": [
            {"type": "text", "data": {"text": "不应该收到这条消息"}},
        ],
    })

    asyncio.run(adapter._dispatch(event))
    assert len(received) == 0  # blocked!
    print("[PASS] _dispatch access control (blocked)")


def test_dispatch_non_message_event(session_store):
    """_dispatch ignores non-message events (notices, meta events)."""
    from platforms.qq import QQAdapter

    adapter = QQAdapter(
        session_store=session_store,
        ws_url="ws://127.0.0.1:3001",
    )
    received = []

    async def handler(msg):
        received.append(msg)

    adapter.on_message = handler

    event = json.dumps({
        "post_type": "notice",
        "notice_type": "group_increase",
    })

    asyncio.run(adapter._dispatch(event))
    assert len(received) == 0
    print("[PASS] _dispatch ignores non-message events")


def test_dispatch_json_decode_error(session_store):
    """_dispatch handles malformed JSON gracefully."""
    from platforms.qq import QQAdapter

    adapter = QQAdapter(
        session_store=session_store,
        ws_url="ws://127.0.0.1:3001",
    )
    received = []

    async def handler(msg):
        received.append(msg)

    adapter.on_message = handler

    # Bad JSON
    asyncio.run(adapter._dispatch("not-valid-json{{{"))
    assert len(received) == 0
    print("[PASS] _dispatch handles malformed JSON")


# ═══════════════════════════════════════════════════════════════
# Test 5: _call_api payload format
# ═══════════════════════════════════════════════════════════════

def test_call_api_payload_format(session_store):
    """_call_api sends correctly formatted OneBot v11 payloads."""
    from platforms.qq import QQAdapter

    adapter = QQAdapter(
        session_store=session_store,
        ws_url="ws://127.0.0.1:3001",
    )

    # Simulate a connected WebSocket
    mock_ws = MagicMock()
    mock_ws.send_str = AsyncMock()
    adapter._ws = mock_ws

    async def run():
        result = await adapter._call_api("send_msg", {
            "message_type": "private",
            "user_id": 642476404,
            "message": [{"type": "text", "data": {"text": "hello"}}],
        })
        # Check that send_str was called with correct format
        mock_ws.send_str.assert_called_once()
        sent_payload = json.loads(mock_ws.send_str.call_args[0][0])
        assert sent_payload["action"] == "send_msg"
        assert sent_payload["params"]["user_id"] == 642476404
        assert "echo" in sent_payload
        print("[PASS] _call_api payload format")

    asyncio.run(run())


# ═══════════════════════════════════════════════════════════════
# Test 6: NapCat connectivity (optional)
# ═══════════════════════════════════════════════════════════════

async def test_napcat_connectivity():
    """Try to connect to the configured QQ_WS_URL. Non-fatal if offline."""
    import aiohttp
    from config import QQ_WS_URL, QQ_ACCESS_TOKEN

    if not QQ_WS_URL:
        print("[SKIP] QQ_WS_URL not configured")
        return

    print(f"\n--- NapCat connectivity test ({QQ_WS_URL}) ---")
    headers = {}
    if QQ_ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {QQ_ACCESS_TOKEN}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(QQ_WS_URL, headers=headers) as ws:
                print(f"  Connected! Server: {ws.headers.get('Server', 'unknown')}")
                # Send a get_login_info call to verify the connection
                echo_id = "test-echo-001"
                await ws.send_str(json.dumps({
                    "action": "get_login_info",
                    "echo": echo_id,
                }))
                # Wait for response
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("echo") == echo_id:
                            print(f"  Login info: {json.dumps(data, ensure_ascii=False)[:300]}")
                            print("  [PASS] NapCat is online and responding!")
                            return
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        print("  WS closed unexpectedly")
                        return
    except aiohttp.ClientConnectorError:
        print(f"  [WARN] Cannot connect to {QQ_WS_URL} — NapCat not running?")
        print("  Start NapCat first, or set QQ_WS_URL to empty to skip.")
    except Exception as e:
        print(f"  [WARN] Connection failed: {e}")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("NeoFish QQ Bot — Integration Tests")
    print("=" * 55)

    # Unit tests (no network)
    print("\n[Unit Tests]")
    store = test_imports()
    test_adapter_init(store)
    test_parse_target()
    test_build_image_segment()
    test_dispatch_private_message(store)
    test_dispatch_group_message(store)
    test_dispatch_api_response(store)
    test_dispatch_image_message(store)
    test_dispatch_access_control(store)
    test_dispatch_non_message_event(store)
    test_dispatch_json_decode_error(store)
    test_call_api_payload_format(store)

    print(f"\n{len([1]*12)}/12 unit tests passed!")

    # Connectivity test
    asyncio.run(test_napcat_connectivity())

    print("\nDone.")


if __name__ == "__main__":
    main()
