from dotenv import load_dotenv

load_dotenv()

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os

from memory.session_memory import SessionMemory
from playwright_manager import PlaywrightManager
from agent import run_agent_loop
from platforms.web import WebAdapter
from task_manager import task_manager
from knowledge_service import KnowledgeService

pm = PlaywrightManager()

# Workspace for user uploads
WORKSPACE_DIR = Path(os.getenv("WORKDIR", "./workspace")).resolve()
UPLOADS_DIR = WORKSPACE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
knowledge_service = KnowledgeService(WORKSPACE_DIR)

# ─── Session Store ────────────────────────────────────────────────────────────

SESSIONS_DIR = Path("sessions/")
INDEX_FILE = SESSIONS_DIR / "index.json"

_session_index: dict[str, dict] = {}


def _ensure_sessions_dir() -> None:
    SESSIONS_DIR.mkdir(exist_ok=True)


def _load_index() -> dict[str, dict]:
    if INDEX_FILE.exists():
        try:
            import orjson
            return orjson.loads(INDEX_FILE.read_bytes())
        except Exception:
            pass
    return {}


def _save_index() -> None:
    import orjson
    INDEX_FILE.write_bytes(orjson.dumps(_session_index))


def _session_dir(sid: str) -> Path:
    return SESSIONS_DIR / sid


def _load_session(sid: str) -> dict | None:
    meta_path = _session_dir(sid) / "meta.json"
    if not meta_path.exists():
        return None
    try:
        import orjson
        meta = orjson.loads(meta_path.read_bytes())
    except Exception:
        return None
    msgs = _load_messages_jsonl(sid)
    meta["messages"] = msgs
    return meta


def _load_messages_jsonl(sid: str) -> list:
    path = _session_dir(sid) / "messages.jsonl"
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        import orjson as _orjson
        return [_orjson.loads(line) for line in lines if line.strip()]
    except Exception:
        return []


def _append_message_jsonl(sid: str, msg: dict) -> None:
    import orjson as _orjson
    path = _session_dir(sid) / "messages.jsonl"
    with open(path, "ab") as f:
        f.write(_orjson.dumps(msg))
        f.write(b"\n")


def _save_session_meta(sid: str, data: dict) -> None:
    import orjson as _orjson
    meta = {
        "id": data["id"],
        "title": data.get("title", ""),
        "created_at": data.get("created_at", ""),
        "session_memory": data.get("session_memory"),
    }
    meta_path = _session_dir(sid) / "meta.json"
    meta_path.write_bytes(_orjson.dumps(meta))


def _new_session(title: str = "") -> dict:
    import uuid as _uuid
    sid = str(_uuid.uuid4())
    created = datetime.now().isoformat()
    data = {
        "id": sid,
        "title": title,
        "created_at": created,
        "messages": [],
        "session_memory": None,
    }
    sdir = _session_dir(sid)
    sdir.mkdir(parents=True, exist_ok=True)
    _save_session_meta(sid, data)
    _append_message_jsonl(sid, {"role": "system", "content": "session_start", "timestamp": created})
    _session_index[sid] = {"id": sid, "title": title, "created_at": created}
    _save_index()
    return data


def _delete_session_files(sid: str) -> None:
    import shutil
    sdir = _session_dir(sid)
    if sdir.exists():
        shutil.rmtree(sdir)


def _migrate_legacy() -> None:
    legacy = Path("sessions.json")
    if not legacy.exists():
        return
    try:
        import json
        legacy_data = json.loads(legacy.read_text(encoding="utf-8"))
        for sid, data in legacy_data.items():
            sdir = _session_dir(sid)
            sdir.mkdir(parents=True, exist_ok=True)
            messages = data.get("messages", [])
            with open(sdir / "messages.jsonl", "wb") as f:
                import orjson as _orjson
                for msg in messages:
                    f.write(_orjson.dumps(msg))
                    f.write(b"\n")
            _save_session_meta(sid, data)
            _session_index[sid] = {
                "id": sid,
                "title": data.get("title", ""),
                "created_at": data.get("created_at", ""),
            }
        _save_index()
        legacy.rename(legacy.with_suffix(".json.bak"))
    except Exception as e:
        print(f"Migration warning: {e}")


def _migrate_per_session() -> None:
    for sid_path in SESSIONS_DIR.iterdir():
        if not sid_path.is_dir():
            continue
        sid = sid_path.name
        json_file = sid_path.with_suffix(".json")
        if json_file.exists():
            try:
                import orjson as _orjson
                data = _orjson.loads(json_file.read_bytes())
                _save_session_meta(sid, data)
                if not (sid_path / "messages.jsonl").exists():
                    msgs = data.get("messages", [])
                    for msg in msgs:
                        _append_message_jsonl(sid, msg)
                json_file.unlink()
            except Exception:
                pass


_ensure_sessions_dir()
_migrate_legacy()
_migrate_per_session()
_session_index = _load_index()

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
    result = [_session_preview({"id": sid, **info}) for sid, info in _session_index.items()]
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
    if session_id not in _session_index:
        raise HTTPException(status_code=404, detail="Session not found")
    _session_index[session_id]["title"] = body.title
    data = _load_session(session_id)
    if data:
        data["title"] = body.title
        _save_session_meta(session_id, data)
    _save_index()
    return _session_preview({"id": session_id, **_session_index[session_id]})


@app.delete("/chats/{session_id}")
def delete_chat(session_id: str):
    if session_id not in _session_index:
        raise HTTPException(status_code=404, detail="Session not found")
    del _session_index[session_id]
    _delete_session_files(session_id)
    _save_index()
    return {"ok": True}


@app.get("/chats/{session_id}/messages")
def get_messages(session_id: str):
    if session_id not in _session_index:
        raise HTTPException(status_code=404, detail="Session not found")
    data = _load_session(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    return data.get("messages", [])


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


class CreateKnowledgeFolder(BaseModel):
    name: str


class ToggleKnowledgeFolder(BaseModel):
    folder_id: str


class KnowledgeSearchBody(BaseModel):
    query: str
    top_k: int = 5


@app.get("/knowledge/folders")
def list_knowledge_folders():
    folders = knowledge_service.list_folders()
    return {"folders": folders}


@app.post("/knowledge/folders")
def create_knowledge_folder(body: CreateKnowledgeFolder):
    try:
        folder = knowledge_service.create_folder(body.name)
        return {"folder": folder}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/knowledge/selected")
def get_selected_knowledge_folders():
    return {"selected_folder_ids": knowledge_service.get_selected()}


@app.post("/knowledge/select")
def select_knowledge_folder(body: ToggleKnowledgeFolder):
    try:
        knowledge_service.select_folder(body.folder_id)
        return {"ok": True, "folder_id": body.folder_id}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Folder not found")


@app.post("/knowledge/deselect")
def deselect_knowledge_folder(body: ToggleKnowledgeFolder):
    knowledge_service.deselect_folder(body.folder_id)
    return {"ok": True, "folder_id": body.folder_id}


@app.post("/knowledge/upload")
async def upload_knowledge_files(
    folder_id: str = Form(...),
    files: list[UploadFile] = File(...),
):
    parsed_files: list[tuple[str, bytes, str]] = []
    for upload in files:
        content = await upload.read()
        parsed_files.append(
            (
                upload.filename or "unnamed_file",
                content,
                upload.content_type or "application/octet-stream",
            )
        )
    try:
        result = knowledge_service.upload_files(folder_id, parsed_files)
        return {"ok": True, **result}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Folder not found")


@app.get("/knowledge/folders/{folder_id}/files")
def list_knowledge_files(folder_id: str):
    try:
        files = knowledge_service.list_files(folder_id)
        return {"files": files}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Folder not found")


@app.delete("/knowledge/files/{file_id}")
def delete_knowledge_file(file_id: str):
    try:
        result = knowledge_service.delete_file(file_id)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")


@app.get("/knowledge/files/{file_id}/preview")
def preview_knowledge_file(file_id: str):
    try:
        file_path = knowledge_service.preview_path(file_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return FileResponse(file_path)


@app.get("/knowledge/status")
def knowledge_status():
    return knowledge_service.status()


@app.post("/knowledge/search")
def knowledge_search(body: KnowledgeSearchBody):
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    top_k = max(1, min(20, body.top_k))
    results = knowledge_service.search(query=query, top_k=top_k)
    return {"results": results}


# ─── WebSocket ────────────────────────────────────────────────────────────────


@app.websocket("/ws/agent")
async def websocket_endpoint(websocket: WebSocket):
    session_id: Optional[str] = websocket.query_params.get("session_id")

    # Auto-create session if not provided or not found
    if not session_id or session_id not in _session_index:
        session = _new_session()
        session_id = session["id"]

    await websocket.accept()

    adapter = WebAdapter(
        websocket=websocket,
        session_id=session_id,
        uploads_dir=UPLOADS_DIR,
        playwright_manager=pm,
        run_agent=run_agent_loop,
        append_message_fn=lambda sid, msg: _append_message_jsonl(sid, msg),
        update_session_fn=lambda sid, data: _save_session_meta(sid, data),
        load_history_fn=_load_messages_jsonl,
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
