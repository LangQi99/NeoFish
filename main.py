from dotenv import load_dotenv

load_dotenv()

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os

from playwright_manager import PlaywrightManager
from agent import run_agent_loop
from platforms.web import WebAdapter
from task_manager import task_manager

pm = PlaywrightManager()

# Workspace for user uploads
WORKSPACE_DIR = Path(os.getenv("WORKDIR", "./workspace")).resolve()
UPLOADS_DIR = WORKSPACE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ─── Session Store ────────────────────────────────────────────────────────────

SESSIONS_FILE = Path("sessions.json")


def _load_sessions() -> dict:
    if SESSIONS_FILE.exists():
        try:
            return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_sessions():
    SESSIONS_FILE.write_text(
        json.dumps(sessions, ensure_ascii=False, indent=2), encoding="utf-8"
    )


sessions: dict = _load_sessions()  # {session_id: {title, created_at, messages: [...]}}

_HIDDEN_PREVIEW_KEYS = {
    "common.connected_ws",
    "common.context_compressing",
    "common.manual_compressing",
    "common.agent_resumed",
    "common.sent_resume",
    "common.message_queued",
    "common.agent_starting",
    "common.agent_thinking",
    "common.executing_action",
    "common.takeover_browser_opened",
    "common.takeover_ended_message",
    "common.agent_paused_for_takeover",
    "common.image_input_disabled",
    "common.max_steps_error",
}

_HIDDEN_PREVIEW_PREFIXES = (
    "[Image] ",
    "[Action Required] ",
    "[Takeover] ",
    "[Takeover Ended] ",
    "Executing action:",
    "Agent is thinking",
    "Error calling LLM:",
)

_HIDDEN_PREVIEW_SNIPPETS = (
    "Connected to NeoFish Agent WebSocket",
    "Task reached maximum steps without calling finish_task",
    "Context threshold reached",
    "Manual compression triggered",
    "Agent paused for manual takeover",
    "已发送继续执行",
)


def _strip_markdown_preview(text: str) -> str:
    clean = text or ""
    clean = re.sub(r"!\[[^\]]*]\([^)]+\)", " ", clean)
    clean = re.sub(r"\[([^\]]+)]\(([^)]+)\)", r"\1", clean)
    clean = re.sub(r"^\s{0,3}#{1,6}\s*", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"^\s*[-*+]\s+", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"^\s*\d+\.\s+", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"[`*_~]+", "", clean)
    clean = re.sub(r"^>\s*", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip().strip("\"'")


def _preview_text(msg: dict) -> str:
    if msg.get("message_key") == "common.task_completed":
        report = (msg.get("params") or {}).get("report")
        if isinstance(report, str) and report.strip():
            return report
    return msg.get("content") or ""


def _is_preview_candidate(msg: dict) -> bool:
    content = _strip_markdown_preview(_preview_text(msg))
    if not content:
        return False

    if msg.get("role") == "user":
        return True

    if msg.get("message_key") in _HIDDEN_PREVIEW_KEYS:
        return False

    if any(content.startswith(prefix) for prefix in _HIDDEN_PREVIEW_PREFIXES):
        return False

    if any(snippet in content for snippet in _HIDDEN_PREVIEW_SNIPPETS):
        return False

    return True


def _extract_session_preview(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if not _is_preview_candidate(msg):
            continue
        preview = _strip_markdown_preview(_preview_text(msg))
        if preview:
            return preview[:120]
    return ""


def _new_session(title: str = "") -> dict:
    sid = str(uuid.uuid4())
    sessions[sid] = {
        "id": sid,
        "title": title,
        "created_at": datetime.now().isoformat(),
        "messages": [],
    }
    _save_sessions()
    return sessions[sid]


def _session_preview(s: dict) -> dict:
    msgs = s.get("messages", [])
    return {
        "id": s["id"],
        "title": s["title"] or "New Chat",
        "created_at": s["created_at"],
        "preview": _extract_session_preview(msgs),
        "message_count": len(msgs),
    }


# ─── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting Playwright Manager...")
    await pm.start()
    yield
    print("Stopping Playwright Manager...")
    await pm.stop()


app = FastAPI(title="NeoFish Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── REST Endpoints ───────────────────────────────────────────────────────────


@app.get("/")
def read_root():
    return {"message": "Welcome to NeoFish Backend"}


@app.get("/chats")
def list_chats():
    """Return all sessions sorted by created_at descending."""
    result = [_session_preview(s) for s in sessions.values()]
    result.sort(key=lambda x: x["created_at"], reverse=True)
    return result


@app.post("/chats")
def create_chat():
    """Create a new empty session and return it."""
    session = _new_session()
    return _session_preview(session)


class PatchChat(BaseModel):
    title: str


@app.patch("/chats/{session_id}")
def rename_chat(session_id: str, body: PatchChat):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    sessions[session_id]["title"] = body.title
    _save_sessions()
    return _session_preview(sessions[session_id])


@app.delete("/chats/{session_id}")
def delete_chat(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    del sessions[session_id]
    _save_sessions()
    return {"ok": True}


@app.get("/chats/{session_id}/messages")
def get_messages(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return sessions[session_id]["messages"]


@app.get("/tasks")
def list_tasks():
    tasks = task_manager.list_tasks()
    summary = {
        "total": len(tasks),
        "pending": sum(1 for task in tasks if task.get("status") == "pending"),
        "in_progress": sum(1 for task in tasks if task.get("status") == "in_progress"),
        "completed": sum(1 for task in tasks if task.get("status") == "completed"),
    }
    return {"tasks": tasks, "summary": summary}


# ─── WebSocket ────────────────────────────────────────────────────────────────


@app.websocket("/ws/agent")
async def websocket_endpoint(websocket: WebSocket):
    session_id: Optional[str] = websocket.query_params.get("session_id")

    # Auto-create session if not provided or not found
    if not session_id or session_id not in sessions:
        session = _new_session()
        session_id = session["id"]

    await websocket.accept()

    adapter = WebAdapter(
        websocket=websocket,
        session_id=session_id,
        sessions=sessions,
        save_sessions=_save_sessions,
        uploads_dir=UPLOADS_DIR,
        playwright_manager=pm,
        run_agent=run_agent_loop,
    )
    await adapter.start()

    try:
        while True:
            data = await websocket.receive_text()
            await adapter.handle_message(data)
    except WebSocketDisconnect:
        print(
            f"WebSocket client disconnected (session: {session_id}), task continues in background"
        )
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await adapter.stop()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
