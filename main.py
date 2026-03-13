from dotenv import load_dotenv
load_dotenv()

import json
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from playwright_manager import PlaywrightManager
from agent import run_agent_loop

pm = PlaywrightManager()

# Prefixes used to tag assistant messages that carry structured data.
# Keep this list in sync with the matching stripping logic in the WS handler.
_ASSISTANT_MSG_PREFIXES = (
    "[Image] ",
    "[Action Required] ",
    "[Takeover] ",
    "[Takeover Ended] ",
)

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
        json.dumps(sessions, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

sessions: dict = _load_sessions()   # {session_id: {title, created_at, messages: [...]}}

def _new_session(title: str = "") -> dict:
    sid = str(uuid.uuid4())
    sessions[sid] = {
        "id": sid,
        "title": title,
        "created_at": datetime.now().isoformat(),
        "messages": []
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
    await websocket.send_text(json.dumps({
        "type": "info",
        "message": "Connected to NeoFish Agent WebSocket",
        "message_key": "common.connected_ws",
        "session_id": session_id,
    }))

    def _append_message(role: str, content: str, images: list = [], image_data: str = ""):
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "images": images,
        }
        if image_data:
            msg["image_data"] = image_data
        sessions[session_id]["messages"].append(msg)
        # Auto-title: use first user message (truncated)
        if role == "user" and not sessions[session_id]["title"]:
            sessions[session_id]["title"] = (content or "📷 Image")[:40]
        _save_sessions()

    async def request_human_action(reason: str, b64_image: str):
        payload = {
            "type": "action_required",
            "reason": reason,
            "image": b64_image
        }
        await websocket.send_text(json.dumps(payload))
        _append_message("assistant", f"[Action Required] {reason}", image_data=b64_image)

    async def send_image(description: str, b64_image: str):
        payload = {
            "type": "image",
            "description": description,
            "image": b64_image
        }
        await websocket.send_text(json.dumps(payload))
        _append_message("assistant", f"[Image] {description}", image_data=b64_image)

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            msg_type = payload.get("type")

            if msg_type == "resume":
                pm.resume_from_human()
                await websocket.send_text(json.dumps({
                    "type": "info",
                    "message": "Agent resumed execution.",
                    "message_key": "common.agent_resumed"
                }))

            elif msg_type == "takeover":
                # User clicked "Take Control" — open a visible browser window.
                # Works both during action_required blocks and proactively.
                if pm.in_takeover:
                    await websocket.send_text(json.dumps({
                        "type": "info",
                        "message": "Takeover is already in progress.",
                        "message_key": "common.takeover_already_active"
                    }))
                else:
                    # Request agent loop to pause at next safe point
                    pm.request_pause()

                    async def do_takeover():
                        # Notify frontend that the headed browser is opening
                        await websocket.send_text(json.dumps({
                            "type": "takeover_started",
                            "message": "Browser opened for manual interaction. Close it when you are done.",
                            "message_key": "common.takeover_started"
                        }))
                        _append_message("assistant", "[Takeover] Browser opened for manual interaction.")

                        await pm.start_takeover()

                        # Block until the user closes the browser or presses "Done"
                        final_url, final_screenshot = await pm.wait_for_takeover_complete()

                        # Relaunch headless and navigate to where the user left off
                        await pm.end_takeover(final_url)

                        # Capture a fresh screenshot if we could not grab one on close
                        if not final_screenshot:
                            final_screenshot = await pm.get_page_screenshot_base64()

                        # Notify frontend
                        ended_payload: dict = {
                            "type": "takeover_ended",
                            "message": "Takeover ended. AI is resuming.",
                            "message_key": "common.takeover_ended",
                            "final_url": final_url,
                        }
                        if final_screenshot:
                            ended_payload["image"] = final_screenshot
                        await websocket.send_text(json.dumps(ended_payload))
                        if final_screenshot:
                            _append_message(
                                "assistant",
                                f"[Takeover Ended] Resumed at: {final_url}",
                                image_data=final_screenshot,
                            )

                        # Unblock agent loop (resumes both block_for_human waits and
                        # the proactive-pause check at the top of each step)
                        pm.resume_from_human()

                    asyncio.create_task(do_takeover())

            elif msg_type == "takeover_done":
                # User pressed "Done" in the UI without closing the browser window
                pm.signal_takeover_done()

            elif msg_type == "user_input":
                user_msg = payload.get("message", "")
                user_images = payload.get("images", [])  # list of base64 data-URLs
                _append_message("user", user_msg, images=user_images)

                # Build conversation history from session messages
                history_messages = []
                for m in sessions[session_id]["messages"][:-1]:  # Exclude current message
                    role = m.get("role", "user")
                    content = m.get("content", "")
                    if role == "user":
                        history_messages.append({"role": "user", "content": content or "(user sent an image)"})
                    else:
                        # Assistant messages - clean up markers like [Image], [Action Required]
                        clean_content = content
                        for prefix in _ASSISTANT_MSG_PREFIXES:
                            if clean_content.startswith(prefix):
                                clean_content = clean_content[len(prefix):]
                        if clean_content:
                            history_messages.append({"role": "assistant", "content": clean_content})

                async def ws_send_msg(msg):
                    """Accept str or dict from agent.py and normalize to WS payload."""
                    if isinstance(msg, dict):
                        human_text = msg.get("message", "")
                        packet = {"type": "info", **msg}
                    else:
                        human_text = str(msg)
                        packet = {"type": "info", "message": human_text}
                    _append_message("assistant", human_text)
                    await websocket.send_text(json.dumps(packet))

                asyncio.create_task(run_agent_loop(pm, user_msg, ws_send_msg, request_human_action, send_image, images=user_images, history_messages=history_messages))

    except WebSocketDisconnect:
        print(f"WebSocket client disconnected (session: {session_id})")
    except Exception as e:
        print(f"WebSocket error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
