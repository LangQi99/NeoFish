from dotenv import load_dotenv

load_dotenv()

import json
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
    last_msg = msgs[-1]["content"] if msgs else ""
    return {
        "id": s["id"],
        "title": s["title"] or "New Chat",
        "created_at": s["created_at"],
        "preview": last_msg[:80] if last_msg else "",
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
