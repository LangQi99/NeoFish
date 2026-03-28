import os
import json
import asyncio
import logging
import time
import re
from pathlib import Path
from dotenv import load_dotenv
from anthropic import AsyncAnthropic
from playwright_manager import PlaywrightManager
from workspace_manager import WorkspaceManager
from task_manager import task_manager
from background_manager import background_manager

logger = logging.getLogger(__name__)

load_dotenv()

client = AsyncAnthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"), base_url=os.getenv("ANTHROPIC_BASE_URL")
)
model_name = os.getenv("MODEL_NAME", "claude-3-7-sonnet-20250219")

# Configuration
WORKDIR = Path(os.getenv("WORKDIR", "./workspace")).resolve()
TOKEN_THRESHOLD = int(os.getenv("TOKEN_THRESHOLD", "800000"))
MAX_TOKEN = int(os.getenv("MAX_TOKEN", "1000000"))
TRANSCRIPT_DIR = Path(os.getenv("TRANSCRIPT_DIR", "./.transcripts")).resolve()
KEEP_RECENT = 3  # For microcompact

# Initialize managers
workspace = WorkspaceManager(WORKDIR, strict=False)

SYSTEM_PROMPT = """You are NeoFish, an autonomous agent that can:
1. **Browse the web** - Navigate, click, type, extract information
2. **Manage files** - Read, write, edit files in the workspace
3. **Execute commands** - Run shell commands (blocking or background)
4. **Track tasks** - Create, update, and manage persistent tasks
5. **Send files** - Send files to the user

## CRITICAL: Working Directory
Your workspace is located at: {workdir}
- ALL file operations MUST be relative to this directory
- When reading/writing files, use relative paths like `src/main.py` or `data/config.json`
- The system will automatically resolve them to the correct absolute path
- NEVER use absolute paths like `/Users/...` or `C:\\...` unless specifically required
- If you need to check the current directory, use `run_bash` with `pwd`

## Observing the page
You have two complementary ways to observe the current state of the page:
1. **Screenshots** – visual snapshots that arrive automatically each step.
2. **snapshot** tool – returns an ARIA accessibility snapshot of the page, listing
   every interactive element with a stable ref ID, e.g.:
     - button "提交" [ref=e1]
     - textbox "用户名" [ref=e2]
     - link "忘记密码" [ref=e3]

## Interacting with elements
**Always prefer ref-based interaction** over CSS / XPath selectors:
- Call `snapshot` to get the current element list with refs.
- Pass `ref=e1` (or whichever ref) to `click` or `type_text` – the engine
  will locate the element by its ARIA role and accessible name, which is far
  more reliable than brittle CSS selectors.
- Only fall back to a CSS/XPath `selector` when no suitable ref is available.

## File Operations
- Use `read_file` to read file contents
- Use `write_file` to create or overwrite files
- Use `edit_file` to make precise changes to existing files
- Use `send_file` to send a file to the user (images, documents, etc.)
- Use `run_bash` to execute shell commands (blocking, with timeout)
- Use `background_run` for long-running commands (non-blocking)

## Task Management
Tasks persist across context compression. Use them to track progress on complex tasks:
- `task_create` - Create a new task with subject and description
- `task_list` - List all tasks with their status
- `task_get` - Get full details of a specific task
- `task_update` - Update task status or dependencies
- For non-trivial multi-step requests, maintain persistent task state proactively.
- If the system tells you a root task was auto-created, do not create a duplicate root task.
- When such a root task exists, keep it updated and mark it completed before `finish_task`.

## Background Tasks
For commands that take a long time:
- `background_run` - Start a background command, returns task_id immediately
- `check_background` - Check status of background tasks

If you ever encounter a strict login wall, CAPTCHA, or require the user to scan a QR code, you must call the `request_human_assistance` tool. Do NOT give up easily; only ask for help when absolutely necessary.
When the task is completely finished, call `finish_task`.
""".format(workdir=WORKDIR)

TOOLS = [
    # Browser tools
    {
        "name": "snapshot",
        "description": (
            "Return an ARIA accessibility snapshot of the current page. "
            "Each interactive element (button, textbox, link, etc.) is tagged with a "
            "stable ref ID such as [ref=e1]. Use the refs with the `click` and "
            "`type_text` tools instead of fragile CSS/XPath selectors."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "navigate",
        "description": "Navigate the browser to a specific URL.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "click",
        "description": (
            "Click an element on the page. "
            'Prefer passing a `ref` obtained from the `snapshot` tool (e.g. ref="e1"). '
            "Fall back to a CSS or XPath `selector` only when no ref is available."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": 'Ref ID from the snapshot (e.g. "e1"). Takes priority over selector.',
                },
                "selector": {
                    "type": "string",
                    "description": "CSS or XPath selector (fallback when ref is not available).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "type_text",
        "description": (
            "Type text into an input element. "
            'Prefer passing a `ref` obtained from the `snapshot` tool (e.g. ref="e2"). '
            "Fall back to a CSS or XPath `selector` only when no ref is available."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": 'Ref ID from the snapshot (e.g. "e2"). Takes priority over selector.',
                },
                "selector": {
                    "type": "string",
                    "description": "CSS or XPath selector (fallback when ref is not available).",
                },
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "scroll",
        "description": "Scroll the page down.",
        "input_schema": {
            "type": "object",
            "properties": {"direction": {"type": "string", "enum": ["down", "up"]}},
            "required": [],
        },
    },
    {
        "name": "extract_info",
        "description": "Extract specific information from the current page content based on observation.",
        "input_schema": {
            "type": "object",
            "properties": {"info_summary": {"type": "string"}},
            "required": ["info_summary"],
        },
    },
    {
        "name": "request_human_assistance",
        "description": "Pause execution to ask the user to manually solve a login, CAPTCHA, or verification. Use this when you are blocked.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why you need human help"}
            },
            "required": ["reason"],
        },
    },
    {
        "name": "send_screenshot",
        "description": "Capture and send the current page screenshot to the user. ONLY use this when: (1) showing final results, (2) User ask you to show something. Do NOT use for routine navigation or intermediate steps. Be selective.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "A brief description of what the screenshot shows",
                }
            },
            "required": ["description"],
        },
    },
    {
        "name": "finish_task",
        "description": "Call this tool when the final objective is fully accomplished. Pass the final report to the user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "report": {
                    "type": "string",
                    "description": "Markdown formatted summary",
                }
            },
            "required": ["report"],
        },
    },
    # File operation tools
    {
        "name": "read_file",
        "description": "Read the contents of a file. Path can be relative to workspace or absolute.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read"},
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read (optional)",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Creates parent directories if needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace exact text in a file. Only replaces the first occurrence.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to edit"},
                "old_text": {
                    "type": "string",
                    "description": "Text to find and replace",
                },
                "new_text": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "send_file",
        "description": "Send a file to the user. Use this to share images, documents, or any file from the workspace. The file must exist in the workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to workspace (e.g. 'output/report.pdf')",
                },
                "description": {
                    "type": "string",
                    "description": "Optional description of the file",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_bash",
        "description": "Execute a shell command. Blocks until completion with timeout (default 120s). Dangerous commands are blocked. You can use python code execution for complex logic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 120)",
                },
            },
            "required": ["command"],
        },
    },
    # Task management tools
    {
        "name": "task_create",
        "description": "Create a new task that persists across context compression.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Brief task title"},
                "description": {
                    "type": "string",
                    "description": "Detailed task description (optional)",
                },
            },
            "required": ["subject"],
        },
    },
    {
        "name": "task_get",
        "description": "Get full details of a task by ID.",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "task_update",
        "description": "Update a task's status or dependencies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed"],
                },
                "addBlockedBy": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Task IDs this task depends on",
                },
                "addBlocks": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Task IDs that depend on this task",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "task_list",
        "description": "List all tasks with their status.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # Background task tools
    {
        "name": "background_run",
        "description": "Run a command in the background. Returns immediately with a task_id. Results will be delivered in next turn.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to run in background",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 300)",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "check_background",
        "description": "Check status of background tasks. Omit task_id to list all.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Specific task ID (optional)",
                }
            },
            "required": [],
        },
    },
    # Context management
    {
        "name": "compact",
        "description": "Trigger manual context compression. Use when conversation is getting too long or switching a inrelevant topic and no longer needs the old context. ",
        "input_schema": {
            "type": "object",
            "properties": {
                "focus": {
                    "type": "string",
                    "description": "What to preserve in the summary",
                }
            },
            "required": [],
        },
    },
]


# ============== Context Compression Functions ==============


def estimate_tokens(messages: list) -> int:
    """Rough token count estimation: ~4 chars per token."""
    return len(str(messages)) // 4


def microcompact(messages: list) -> list:
    """
    Layer 1: Replace old tool_result content with placeholders.
    Keeps only the last KEEP_RECENT tool results intact.
    """
    # Collect all tool_result entries
    tool_results = []
    for msg_idx, msg in enumerate(messages):
        if msg["role"] == "user" and isinstance(msg.get("content"), list):
            for part_idx, part in enumerate(msg["content"]):
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    tool_results.append((msg_idx, part_idx, part))

    if len(tool_results) <= KEEP_RECENT:
        return messages

    # Build tool_name map from assistant messages
    tool_name_map = {}
    for msg in messages:
        if msg["role"] == "assistant":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if hasattr(block, "type") and block.type == "tool_use":
                        tool_name_map[block.id] = block.name
                    elif isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_name_map[block.get("id", "")] = block.get(
                            "name", "unknown"
                        )

    # Clear old results (keep last KEEP_RECENT)
    to_clear = tool_results[:-KEEP_RECENT]
    for _, _, result in to_clear:
        if isinstance(result.get("content"), str) and len(result["content"]) > 100:
            tool_id = result.get("tool_use_id", "")
            tool_name = tool_name_map.get(tool_id, "unknown")
            result["content"] = f"[Previous: used {tool_name}]"

    return messages


def _process_queued_message(
    messages: list, user_content: list, qtext: str, qimages: list
) -> None:
    """Process a queued message and append to conversation."""
    messages.append({"role": "user", "content": f"[New message from user]: {qtext}"})
    for qimg in qimages:
        user_content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": qimg.split(",", 1)[-1] if "," in qimg else qimg,
                },
            }
        )
    messages.append(
        {
            "role": "assistant",
            "content": "I received your new message. I'll incorporate it into my current task.",
        }
    )


async def auto_compact(messages: list, focus: str = None) -> list:
    """
    Layer 2: Save transcript, summarize with LLM, replace messages.
    """
    # Ensure transcript directory exists
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    # Save full transcript
    timestamp = int(time.time())
    transcript_path = TRANSCRIPT_DIR / f"transcript_{timestamp}.jsonl"
    with open(transcript_path, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str, ensure_ascii=False) + "\n")

    # Get current task state for context
    task_summary = task_manager.list_all()

    # Build summary prompt
    conversation_text = json.dumps(messages, default=str, ensure_ascii=False)[:80000]
    focus_text = f"\n\nFocus on preserving: {focus}" if focus else ""

    summary_prompt = (
        "Summarize this conversation for continuity. CRITICAL - YOU MUST:\n\n"
        "1) **EXACT Original User Request** - Quote the user's original request verbatim. "
        "This is THE MOST IMPORTANT thing. Never forget or modify this.\n\n"
        "2) **Completed Work Checklist** - List each item that has been DONE. "
        "Mark as [DONE]. These MUST NOT be repeated.\n\n"
        "3) **Remaining Work Checklist** - List items still pending. Mark as [TODO]. "
        "This is what you should continue with.\n\n"
        "4) **Current Position** - Where exactly are you now? (URL, file being edited, step number, etc.)\n\n"
        "5) **Key Context** - URLs visited, files created/modified, important data extracted.\n\n"
        "Current task system state:\n"
        f"{task_summary}\n\n"
        "WARNING: After compression, DO NOT restart from the beginning. "
        "Continue from where you left off. Items marked [DONE] should NOT be repeated.\n"
        f"{focus_text}\n\n{conversation_text}"
    )

    try:
        response = await client.messages.create(
            model=model_name,
            max_tokens=2000,
            messages=[{"role": "user", "content": summary_prompt}],
        )
        # Extract text from response, handling ThinkingBlock etc.
        text_parts = []
        for block in response.content:
            if hasattr(block, "text") and block.type == "text":
                text_parts.append(block.text)
        summary = "\n".join(text_parts) if text_parts else "No summary generated."
    except Exception as e:
        summary = f"Error generating summary: {str(e)}"

    # Replace all messages with compressed summary
    return [
        {
            "role": "user",
            "content": (
                f"[Conversation compressed. Full transcript: {transcript_path}]\n\n"
                f"## CRITICAL INSTRUCTIONS:\n"
                f"- DO NOT restart from the beginning\n"
                f"- DO NOT repeat any work marked as [DONE] in the summary\n"
                f"- Continue from the current position described in the summary\n"
                f"- Your workspace directory is: {WORKDIR}\n\n"
                f"## Summary:\n{summary}"
            ),
        },
        {
            "role": "assistant",
            "content": (
                "I understand. I will NOT restart from the beginning. "
                "I will continue from where we left off, skipping any [DONE] items. "
                "Proceeding with the remaining [TODO] items."
            ),
        },
    ]


_SIMPLE_CHAT_INPUTS = {
    "hi",
    "hello",
    "hey",
    "你好",
    "您好",
    "嗨",
    "在吗",
}

_TASK_ACTION_HINTS = (
    "打开",
    "访问",
    "搜索",
    "查找",
    "点击",
    "输入",
    "浏览",
    "分析",
    "总结",
    "整理",
    "生成",
    "制作",
    "发送",
    "读取",
    "提取",
    "下载",
    "截图",
    "navigate",
    "search",
    "open ",
    "visit ",
    "analyze",
    "summarize",
    "generate",
)

_EXPLICIT_TASK_HINTS = (
    "task_create",
    "task_update",
    "task_get",
    "task_list",
    "创建一个任务",
    "创建任务",
    "更新任务",
    "标记为 completed",
    "标记这个任务",
)


def _contains_explicit_task_request(text: str) -> bool:
    lowered = text.lower()
    return any(hint.lower() in lowered for hint in _EXPLICIT_TASK_HINTS)


def _should_auto_create_task(
    instruction: str, images: list, uploaded_files: list
) -> bool:
    text = (instruction or "").strip()
    if not text:
        return False

    lowered = text.lower()
    if lowered in _SIMPLE_CHAT_INPUTS:
        return False

    if _contains_explicit_task_request(text):
        return False

    signal_score = 0

    if images or uploaded_files:
        signal_score += 1

    if "http://" in lowered or "https://" in lowered:
        signal_score += 2

    if any(hint.lower() in lowered for hint in _TASK_ACTION_HINTS):
        signal_score += 1

    if any(token in text for token in ("，", "。", "然后", "并且", "最后", "\n")):
        signal_score += 1

    if len(text) >= 18:
        signal_score += 1

    return signal_score >= 2


def _build_auto_task_subject(instruction: str) -> str:
    clean = re.sub(r"https?://\S+", lambda m: m.group(0)[:28], instruction).strip()
    clean = re.sub(r"^(请|帮我|麻烦|请帮我|帮忙)\s*", "", clean)
    clean = re.sub(r"\s+", " ", clean)
    first_sentence = re.split(r"[。！？\n]", clean, maxsplit=1)[0]
    subject = first_sentence[:28].strip()
    if len(first_sentence) > 28:
        subject += "…"
    return subject or "执行用户请求"


def _auto_create_root_task(
    instruction: str, images: list, uploaded_files: list
) -> dict | None:
    if not _should_auto_create_task(instruction, images, uploaded_files):
        return None

    created = task_manager.create(
        subject=_build_auto_task_subject(instruction),
        description=instruction.strip(),
    )
    task = json.loads(created)
    task_manager.update(task["id"], status="in_progress")
    task["status"] = "in_progress"
    return task


# ============== Main Agent Loop ==============


async def run_agent_loop(
    pm: PlaywrightManager,
    user_instruction: str,
    ws_send_msg,
    ws_request_action,
    ws_send_image,
    ws_send_file,
    images: list = [],
    history_messages: list = [],
    uploaded_files: list = [],
    session_store=None,
    session_id: str = None,
    web_queue_getter=None,
    web_session_id: str = None,
    cancel_event: asyncio.Event = None,
):
    effective_session_id = web_session_id or session_id
    if not effective_session_id:
        await ws_send_msg(
            {"message": "Error: No session ID provided", "message_key": "common.error"}
        )
        return

    try:
        page = await pm.get_or_create_page(effective_session_id)
    except Exception as e:
        await ws_send_msg(
            {
                "message": f"Error creating browser tab: {e}",
                "message_key": "common.error",
            }
        )
        return

    auto_root_task = _auto_create_root_task(user_instruction, images, uploaded_files)

    await ws_send_msg(
        {
            "message": f"Agent starting task: {user_instruction}",
            "message_key": "common.agent_starting",
            "params": {"task": user_instruction},
        }
    )

    messages = history_messages.copy()
    max_steps = 9999999
    is_finished = False

    # Build first user message with context about uploaded files
    context_parts = []

    # Add uploaded file paths to context
    if uploaded_files:
        context_parts.append(
            f"The user has uploaded {len(uploaded_files)} file(s) which have been saved to:\n"
            + "\n".join(f"  - {path}" for path in uploaded_files)
            + "\n\nYou can use read_file, edit_file, or other file tools to work with these files."
        )

    # Handle images (base64 for LLM vision)
    if images:
        context_parts.append(
            f"The user has attached {len(images)} image(s) directly to their request. "
            "Please examine each image carefully first."
        )

    # Build the full user content
    if context_parts:
        user_content = [
            {
                "type": "text",
                "text": "\n\n".join(context_parts) + f"\n\nTask: {user_instruction}",
            }
        ]
    else:
        user_content = [
            {"type": "text", "text": f"Please execute this task: {user_instruction}"}
        ]

    if auto_root_task:
        user_content[0]["text"] += (
            "\n\nA persistent root task has already been auto-created for this request:\n"
            f"- task_id: {auto_root_task['id']}\n"
            f"- subject: {auto_root_task['subject']}\n"
            "- Its status is already `in_progress`.\n"
            "- Do not create a duplicate root task for the same request.\n"
            "- Update this root task when needed and mark it `completed` before calling finish_task.\n"
            "- You may create additional sub-tasks only if they are genuinely useful."
        )

    # Add images as base64 for vision
    if images:
        for data_url in images:
            try:
                header, b64_data = data_url.split(",", 1)
                media_type = header.split(":")[1].split(";")[0]
                user_content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_data,
                        },
                    }
                )
            except Exception as e:
                logger.warning("Failed to parse image data-URL: %s", e)

    for step in range(max_steps):
        if cancel_event and cancel_event.is_set():
            if auto_root_task:
                task_manager.update(auto_root_task["id"], status="pending")
            await ws_send_msg(
                {
                    "message": "Task cancelled by user.",
                    "message_key": "common.task_cancelled",
                }
            )
            break

        if pm.check_and_clear_pause_request(effective_session_id):
            await ws_send_msg(
                {
                    "message": "Agent paused for manual takeover. Waiting for you to finish…",
                    "message_key": "common.agent_paused_for_takeover",
                }
            )
            await pm.wait_for_resume(effective_session_id)

        # === Drain queued messages from other platforms ===
        # Handle session_store (QQ, Telegram)
        if session_store and session_id:
            queued = session_store.drain_queue_nowait(session_id)
            if queued:
                for qmsg in queued:
                    _process_queued_message(
                        messages,
                        user_content,
                        qmsg.get("text", ""),
                        qmsg.get("images", []),
                    )

        # Handle web queue
        if web_queue_getter and web_session_id:
            web_queue = web_queue_getter()
            if web_queue:
                while not web_queue.empty():
                    try:
                        qmsg = web_queue.get_nowait()
                        _process_queued_message(
                            messages,
                            user_content,
                            qmsg.get("text", ""),
                            qmsg.get("images", []),
                        )
                    except asyncio.QueueEmpty:
                        break

        # === NEW: Drain background notifications ===
        bg_notifs = await background_manager.drain_notifications(effective_session_id)
        if bg_notifs:
            notif_text = background_manager.format_notifications(bg_notifs)
            messages.append(
                {
                    "role": "user",
                    "content": f"<background-results>\n{notif_text}\n</background-results>",
                }
            )
            messages.append(
                {"role": "assistant", "content": "Noted background task results."}
            )

        # === NEW: Microcompact (Layer 1) ===
        microcompact(messages)

        # === NEW: Auto-compact check (Layer 2) ===
        if estimate_tokens(messages) > TOKEN_THRESHOLD:
            await ws_send_msg(
                {
                    "message": "Context threshold reached, compressing...",
                    "message_key": "common.context_compressing",
                }
            )
            messages[:] = await auto_compact(messages)
            # Reset user_content after compression to avoid appending old data
            user_content = []

        # 1. Observe - append observation to user_content
        if page and not page.is_closed():
            try:
                b64_img = await pm.get_page_screenshot_base64(effective_session_id)
                url = page.url
                title = await page.title()
                user_content.append(
                    {
                        "type": "text",
                        "text": f"Current URL: {url}\nTitle: {title}\nWhat is your next action?",
                    }
                )
                if b64_img:
                    user_content.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64_img,
                            },
                        }
                    )
            except Exception as e:
                user_content.append(
                    {
                        "type": "text",
                        "text": f"Observation failed: {e}. Try to continue.",
                    }
                )

        messages.append({"role": "user", "content": user_content})

        # 2. Think
        await ws_send_msg(
            {"message": "Agent is thinking...", "message_key": "common.agent_thinking"}
        )

        try:
            response = await client.messages.create(
                model=model_name,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=TOOLS,
            )
        except Exception as e:
            err_text = str(e)
            if "image_url" in err_text or "validation errors for ValidatorIterator" in err_text:
                user_content = [
                    block for block in user_content
                    if not (isinstance(block, dict) and block.get("type") == "image")
                ]
                messages[-1] = {"role": "user", "content": user_content}
                await ws_send_msg(
                    {
                        "message": "当前模型网关不接受图片输入，已自动切换为纯文本模式继续执行。",
                        "message_key": "common.image_input_disabled",
                    }
                )
                try:
                    response = await client.messages.create(
                        model=model_name,
                        max_tokens=4096,
                        system=SYSTEM_PROMPT,
                        messages=messages,
                        tools=TOOLS,
                    )
                except Exception as retry_error:
                    await ws_send_msg(f"Error calling LLM: {str(retry_error)}")
                    break
            else:
                await ws_send_msg(f"Error calling LLM: {err_text}")
                break

        messages.append({"role": "assistant", "content": response.content})

        # 3. Act
        tool_uses = [block for block in response.content if block.type == "tool_use"]
        user_content = []

        if not tool_uses:
            text_blocks = [b.text for b in response.content if b.type == "text"]
            if text_blocks:
                msg = "\n".join(text_blocks)
                await ws_send_msg(msg)
                break
            continue

        manual_compact = False

        for tool in tool_uses:
            tool_name = tool.name
            args = tool.input
            result_str = ""

            await ws_send_msg(
                {
                    "message": f"Executing action: `{tool_name}` with args: {json.dumps(args, ensure_ascii=False)}",
                    "message_key": "common.executing_action",
                    "params": {
                        "tool": tool_name,
                        "args": json.dumps(args, ensure_ascii=False),
                    },
                }
            )

            try:
                if tool_name == "snapshot":
                    snapshot_text = await pm.get_aria_snapshot(effective_session_id)
                    result_str = (
                        snapshot_text
                        if snapshot_text
                        else "Could not capture aria snapshot."
                    )

                elif tool_name == "navigate":
                    await page.goto(args["url"])
                    await asyncio.sleep(2)
                    result_str = "Successfully navigated."

                elif tool_name == "click":
                    ref = args.get("ref")
                    selector = args.get("selector")
                    if ref:
                        locator = await pm.locate_by_ref(ref, effective_session_id)
                        await locator.click(timeout=5000)
                    elif selector:
                        await page.click(selector, timeout=5000)
                    else:
                        raise ValueError("click requires either 'ref' or 'selector'")
                    await asyncio.sleep(1)
                    result_str = "Successfully clicked."

                elif tool_name == "type_text":
                    ref = args.get("ref")
                    selector = args.get("selector")
                    if ref:
                        locator = await pm.locate_by_ref(ref, effective_session_id)
                        await locator.fill(args["text"])
                    elif selector:
                        await page.fill(selector, args["text"])
                    else:
                        raise ValueError(
                            "type_text requires either 'ref' or 'selector'"
                        )
                    result_str = "Successfully typed text."

                elif tool_name == "scroll":
                    direction = args.get("direction", "down")
                    if direction == "down":
                        await page.mouse.wheel(0, 1000)
                    else:
                        await page.mouse.wheel(0, -1000)
                    await asyncio.sleep(1)
                    result_str = "Scrolled."

                elif tool_name == "request_human_assistance":
                    reason = args.get("reason", "Login required.")
                    await pm.block_for_human(
                        ws_request_action, reason, effective_session_id
                    )
                    result_str = "Human has processed the request. Page might have updated. You may resume your task."

                elif tool_name == "extract_info":
                    result_str = f"Extracted: {args['info_summary']}"

                elif tool_name == "send_screenshot":
                    description = args.get("description", "Current page screenshot")
                    screenshot_b64 = await pm.get_page_screenshot_base64(
                        effective_session_id
                    )
                    if screenshot_b64:
                        await ws_send_image(description, screenshot_b64)
                        result_str = f"Screenshot sent to user: {description}"
                    else:
                        result_str = "Failed to capture screenshot."

                elif tool_name == "finish_task":
                    report = args.get("report", "Task completed.")
                    if auto_root_task:
                        task_manager.update(auto_root_task["id"], status="completed")
                    await ws_send_msg(
                        {
                            "message": f"✅ **Task Completed**:\n\n{report}",
                            "message_key": "common.task_completed",
                            "params": {"report": report},
                        }
                    )
                    result_str = "Finished."
                    is_finished = True

                # File operation tools
                elif tool_name == "read_file":
                    result_str = await workspace.read_file(
                        args["path"], args.get("limit")
                    )

                elif tool_name == "write_file":
                    result_str = await workspace.write_file(
                        args["path"], args["content"]
                    )

                elif tool_name == "edit_file":
                    result_str = await workspace.edit_file(
                        args["path"], args["old_text"], args["new_text"]
                    )

                elif tool_name == "send_file":
                    file_path = args["path"]
                    description = args.get("description", f"File: {file_path}")
                    # Resolve path relative to workspace
                    full_path = WORKDIR / file_path
                    if not full_path.exists():
                        result_str = f"Error: File not found: {file_path}"
                    elif not str(full_path.resolve()).startswith(
                        str(WORKDIR.resolve())
                    ):
                        result_str = f"Error: Path escapes workspace: {file_path}"
                    else:
                        await ws_send_file(file_path, description)
                        result_str = f"File sent: {file_path}"

                elif tool_name == "run_bash":
                    result_str = await workspace.run_bash(
                        args["command"], args.get("timeout", 120)
                    )

                # Task management tools
                elif tool_name == "task_create":
                    result_str = task_manager.create(
                        args["subject"], args.get("description", "")
                    )

                elif tool_name == "task_get":
                    result_str = task_manager.get(args["task_id"])

                elif tool_name == "task_update":
                    result_str = task_manager.update(
                        args["task_id"],
                        args.get("status"),
                        args.get("addBlockedBy"),
                        args.get("addBlocks"),
                    )

                elif tool_name == "task_list":
                    result_str = task_manager.list_all()

                # Background task tools
                elif tool_name == "background_run":
                    result_str = await background_manager.run(
                        args["command"],
                        args.get("timeout"),
                        effective_session_id,
                    )

                elif tool_name == "check_background":
                    result_str = await background_manager.check(args.get("task_id"))

                # Context compression
                elif tool_name == "compact":
                    manual_compact = True
                    focus = args.get("focus")
                    result_str = (
                        f"Manual compression requested{': ' + focus if focus else ''}."
                    )

                else:
                    result_str = f"Unknown tool: {tool_name}"

            except Exception as e:
                result_str = f"Error executing {tool_name}: {str(e)}"

            user_content.append(
                {"type": "tool_result", "tool_use_id": tool.id, "content": result_str}
            )

        # === NEW: Handle manual compact (Layer 3) ===
        if manual_compact:
            await ws_send_msg(
                {
                    "message": "Manual compression triggered...",
                    "message_key": "common.manual_compressing",
                }
            )
            focus = None
            for tool in tool_uses:
                if tool.name == "compact" and tool.input.get("focus"):
                    focus = tool.input["focus"]
            messages[:] = await auto_compact(messages, focus)
            # Reset user_content after compression
            user_content = []

        if is_finished:
            break

    if not is_finished:
        if auto_root_task:
            task_manager.update(auto_root_task["id"], status="pending")
        await ws_send_msg(
            {
                "message": "⚠️ Task reached maximum steps without calling finish_task.",
                "message_key": "common.max_steps_error",
            }
        )

    pm.deactivate_tab(effective_session_id)
