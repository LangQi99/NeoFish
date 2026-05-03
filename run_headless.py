"""
run_headless.py — Backend-only HTTP API for programmatic integration.

启动一个 FastAPI 服务器，通过纯 HTTP 接口让其他应用调用 NeoFish 的 Agent 能力，
无需启动前端。默认使用有头的本机 Chrome 浏览器，方便人工接管。

Usage::

    uv run python run_headless.py
    # or:
    uv run uvicorn run_headless:app --host 0.0.0.0 --port 8100

Environment
-----------
HEADLESS_API_HOST           — bind address (default: 0.0.0.0)
HEADLESS_API_PORT           — port (default: 8100)
NEOFISH_HEADLESS_BROWSER_MODE — "local_chrome" (default) | "headless"
ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL / MODEL_NAME — same as main app

See docs/headless_api.md for the protocol.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent import run_agent_loop
from config import WORKDIR
from memory.session_memory import SessionMemory
from playwright_manager import (
    BROWSER_MODE_HEADLESS,
    BROWSER_MODE_LOCAL_CHROME,
    PlaywrightManager,
)
from session import session_store

logger = logging.getLogger("neofish.headless")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ── Configuration ─────────────────────────────────────────────────────────────

HEADLESS_API_HOST = os.getenv("HEADLESS_API_HOST", "0.0.0.0")
HEADLESS_API_PORT = int(os.getenv("HEADLESS_API_PORT", "8100"))

_MODE_RAW = os.getenv("NEOFISH_HEADLESS_BROWSER_MODE", BROWSER_MODE_LOCAL_CHROME).strip()
_INITIAL_MODE = (
    BROWSER_MODE_HEADLESS if _MODE_RAW == BROWSER_MODE_HEADLESS else BROWSER_MODE_LOCAL_CHROME
)

PLATFORM = "headless_api"

# ── State ─────────────────────────────────────────────────────────────────────

pm = PlaywrightManager(browser_mode=_INITIAL_MODE)

# Per-session channel where terminal outcomes (completed / needs_input) land.
_outcomes: dict[str, asyncio.Queue] = {}
# Per-session broadcast queue for streaming info events (for SSE clients).
_streams: dict[str, asyncio.Queue] = {}
# The background asyncio.Task running run_agent_loop for each session.
_agent_tasks: dict[str, asyncio.Task] = {}
# Session memory instances kept warm so that follow-up calls reuse task_spec.
_memories: dict[str, SessionMemory] = {}


def _outcome_queue(session_id: str) -> asyncio.Queue:
    q = _outcomes.get(session_id)
    if q is None:
        q = asyncio.Queue()
        _outcomes[session_id] = q
    return q


def _stream_queue(session_id: str) -> asyncio.Queue:
    q = _streams.get(session_id)
    if q is None:
        q = asyncio.Queue()
        _streams[session_id] = q
    return q


def _memory_for(session_id: str) -> SessionMemory:
    mem = _memories.get(session_id)
    if mem is None:
        mem = SessionMemory(session_id=session_id)
        _memories[session_id] = mem
    return mem


# ── Agent runner ──────────────────────────────────────────────────────────────


async def _run_agent_once(
    session_id: str,
    message: str,
    images: list[str],
) -> None:
    """Drive one invocation of run_agent_loop and feed terminal events into the outcome queue."""

    q = _outcome_queue(session_id)
    sq = _stream_queue(session_id)

    async def _send(msg: Any) -> None:
        # Push every info event to the stream queue for SSE clients.
        if isinstance(msg, dict):
            await sq.put({"type": "info", **msg})
        if isinstance(msg, dict) and msg.get("message_key") == "common.task_completed":
            report = msg.get("params", {}).get("report") or msg.get("message", "")
            await q.put({"status": "completed", "output": report})

    async def _request_action(reason: str, image: Optional[str]) -> None:
        payload = {"status": "needs_input", "reason": reason}
        if image:
            payload["screenshot"] = image
        await sq.put({"type": "needs_input", **payload})
        await q.put(payload)

    async def _send_image(description: str, image_b64: str) -> None:
        # Headless API doesn't stream images mid-task — they're accessible via
        # the browser window and will be included in the final report if relevant.
        return

    async def _send_file(file_path: str, description: str) -> None:
        return

    try:
        await run_agent_loop(
            pm,
            message,
            _send,
            _request_action,
            _send_image,
            _send_file,
            images=images,
            session_store=session_store,
            session_id=session_id,
            session_memory=_memory_for(session_id),
            source_meta={
                "platform": PLATFORM,
                "session_id": session_id,
            },
        )
    except Exception as e:
        logger.exception("Agent loop crashed for session %s", session_id)
        await sq.put({"type": "error", "message": str(e)})
        await q.put({"status": "completed", "output": f"[agent error] {e}"})
    finally:
        session_store.set_running(session_id, False)
        # If the loop exited without ever producing a terminal event
        # (e.g. max-steps), synthesize a completed outcome so the HTTP call returns.
        if q.empty():
            await q.put({"status": "completed", "output": "(agent finished without report)"})
        await sq.put({"type": "done"})


# ── FastAPI lifespan ──────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting PlaywrightManager (browser_mode=%s)…", pm.browser_mode
    )
    await pm.start()
    logger.info("PlaywrightManager ready. Headless API listening.")
    yield
    logger.info("Shutting down PlaywrightManager…")
    for task in list(_agent_tasks.values()):
        if not task.done():
            task.cancel()
    await pm.stop()


app = FastAPI(title="NeoFish Headless API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / response models ─────────────────────────────────────────────────


class ChatBody(BaseModel):
    message: str
    session_id: Optional[str] = None
    images: Optional[list[str]] = None
    timeout_seconds: Optional[float] = None  # per-call wait for the next outcome


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "browser_mode": pm.browser_mode,
        "sessions": len(_agent_tasks),
    }


@app.get("/browser/mode")
def get_browser_mode() -> dict:
    return {"mode": pm.browser_mode}


@app.post("/v1/chat")
async def chat(body: ChatBody) -> dict:
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    session_id = body.session_id
    if not session_id:
        chat_id = str(uuid.uuid4())
        session_id = session_store.get_or_create(PLATFORM, chat_id)

    images = body.images or []
    q = _outcome_queue(session_id)

    existing = _agent_tasks.get(session_id)
    agent_running = existing is not None and not existing.done()

    if agent_running:
        # Agent is alive — likely blocked waiting for human assistance.
        # Enqueue the new input so drain_queue_nowait picks it up, then unblock.
        await session_store.enqueue_message(session_id, body.message, images)
        if pm.is_waiting_for_human(session_id):
            pm.signal_resume(session_id)
    else:
        # Fresh run: try_start claims the session slot atomically.
        if not await session_store.try_start(session_id):
            raise HTTPException(
                status_code=409,
                detail="Session already busy; retry shortly.",
            )
        task = asyncio.create_task(
            _run_agent_once(session_id, body.message, images),
            name=f"neofish-agent-{session_id}",
        )
        _agent_tasks[session_id] = task

    timeout = body.timeout_seconds if body.timeout_seconds and body.timeout_seconds > 0 else None
    try:
        if timeout is None:
            outcome = await q.get()
        else:
            outcome = await asyncio.wait_for(q.get(), timeout=timeout)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail={
                "status": "timeout",
                "session_id": session_id,
                "message": "Agent did not reach a terminal state before the deadline; retry POST /v1/chat with the same session_id (and optional new instructions) to keep waiting.",
            },
        )

    outcome["session_id"] = session_id
    return outcome


@app.get("/v1/chat/{session_id}")
async def get_session(session_id: str) -> dict:
    task = _agent_tasks.get(session_id)
    return {
        "session_id": session_id,
        "active": bool(task and not task.done()),
        "waiting_for_human": pm.is_waiting_for_human(session_id),
        "browser_mode": pm.browser_mode,
    }


@app.post("/v1/chat/stream")
async def chat_stream(body: ChatBody):
    """SSE endpoint: start a new agent task and stream all info events until done."""
    import json as _json

    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    session_id = body.session_id
    if not session_id:
        chat_id = str(uuid.uuid4())
        session_id = session_store.get_or_create(PLATFORM, chat_id)

    images = body.images or []
    # Fresh stream queue for this session
    _streams[session_id] = asyncio.Queue()
    sq = _stream_queue(session_id)
    _outcomes[session_id] = asyncio.Queue()

    if not await session_store.try_start(session_id):
        raise HTTPException(status_code=409, detail="Session already busy; retry shortly.")

    task = asyncio.create_task(
        _run_agent_once(session_id, body.message, images),
        name=f"neofish-agent-{session_id}",
    )
    _agent_tasks[session_id] = task

    async def event_gen():
        yield f"data: {_json.dumps({'type': 'start', 'session_id': session_id}, ensure_ascii=False)}\n\n"
        while True:
            try:
                event = await asyncio.wait_for(sq.get(), timeout=120.0)
            except asyncio.TimeoutError:
                yield "data: {\"type\":\"heartbeat\"}\n\n"
                continue
            yield f"data: {_json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get("type") in ("done", "error"):
                break

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/v1/chat/{session_id}")
async def delete_session(session_id: str) -> dict:
    task = _agent_tasks.pop(session_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    _outcomes.pop(session_id, None)
    _memories.pop(session_id, None)
    session_store.set_running(session_id, False)
    await pm.close_tab(session_id)
    return {"ok": True}


# ── Entry ─────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "run_headless:app",
        host=HEADLESS_API_HOST,
        port=HEADLESS_API_PORT,
        reload=False,
    )
