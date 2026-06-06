import os
import json
import asyncio
import logging
import time
import re
from pathlib import Path
from anthropic import AsyncAnthropic
from playwright_manager import PlaywrightManager
from workspace_manager import WorkspaceManager
from planner import plan_manager
from background_manager import background_manager
from memory.session_memory import SessionMemory
from knowledge_service import KnowledgeService
from message_center import MessageCenter
from tool_registry import ToolExecutionResult, ToolRegistry
from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_BASE_URL,
    MODEL_NAME,
    WORKDIR,
    TOKEN_THRESHOLD,
    MAX_TOKEN,
    TRANSCRIPT_DIR,
)

logger = logging.getLogger(__name__)

model_name = MODEL_NAME

_client: AsyncAnthropic | None = None
_client_lock = asyncio.Lock()


async def _get_client() -> AsyncAnthropic:
    """Return the shared AsyncAnthropic client, creating it lazily once."""
    global _client
    if _client is not None:
        return _client
    async with _client_lock:
        if _client is not None:
            return _client
        import httpx as _httpx
        _http = _httpx.AsyncClient(timeout=120.0, http2=False, verify=True)
        _client = AsyncAnthropic(
            api_key=ANTHROPIC_API_KEY,
            base_url=ANTHROPIC_BASE_URL,
            timeout=120.0,
            max_retries=4,
            http_client=_http,
        )
        return _client


def _reset_client():
    """Discard cached client so the next call re-reads env vars."""
    global _client
    _client = None
KEEP_RECENT = 3  # For microcompact

# Initialize managers
workspace = WorkspaceManager(WORKDIR, strict=False)
knowledge_service = KnowledgeService(WORKDIR)

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

## Planning
Maintain a dynamic plan that persists across context compression:
- `plan_write` - Create or fully rewrite the ordered list of steps. Re-plan freely whenever the situation changes.
- `plan_update_step` - Mark a single step in_progress/completed/skipped, or edit its content.
- `plan_read` - Read the current plan.
- For non-trivial multi-step requests, write a plan first and keep step statuses up to date as you work.
- If the system says a plan was auto-initialized for this request, build on it with `plan_write` instead of starting from scratch. Mark all steps completed before `finish_task`.
- Never expose internal plan/step IDs or status bookkeeping in user-facing reports.

## Background Tasks
For commands that take a long time:
- `background_run` - Start a background command, returns task_id immediately
- `check_background` - Check status of background tasks

## Knowledge Base
Use knowledge tools to retrieve information from selected knowledge folders:
- `knowledge_search` - Semantic search over selected knowledge folders (FAISS-backed)

If you ever encounter a strict login wall, CAPTCHA, or require the user to scan a QR code, you must call the `request_human_assistance` tool. Do NOT give up easily; only ask for help when absolutely necessary.
When the task is completely finished, call `finish_task`.

## Session Memory
Throughout the conversation, you must maintain an accurate picture of where you are in the task.
Whenever you complete a meaningful step, make progress, encounter an error, or the user's request changes direction,
output a Memory Update block at the END of your response (after all tool calls and text).

Format:
```
[Memory Update]
current_state: <what is happening right now, in one clear sentence>
task_spec: <the user's core request - keep the original intent>
important_files: <key files created or modified>
errors_corrections: <errors encountered and how they were resolved>
pending_tasks: <genuinely unfinished tasks>
[/Memory Update]
```

- Only output this block when there is something meaningful to record.
- current_state is the MOST important field - always include it when there's progress.
- Keep each field concise (1-2 sentences max).
- If nothing meaningful happened, do not output the block.
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
        "name": "upload_file",
        "description": (
            "Upload local file(s) to a <input type=\"file\"> element. "
            "Required for file pickers — DO NOT use type_text for file inputs, browsers block that. "
            "Prefer `ref` from snapshot; fall back to CSS/XPath `selector` pointing at the input[type=file] "
            "(it's often hidden with display:none, that's fine — set_input_files works on hidden inputs). "
            "If the site has only a custom upload button (no input[type=file] visible), set `trigger_selector` "
            "or `trigger_ref` to that button and omit ref/selector — the tool will click it and handle the "
            "native file chooser dialog."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Ref of the <input type=file>."},
                "selector": {"type": "string", "description": "CSS/XPath of the <input type=file>."},
                "trigger_ref": {
                    "type": "string",
                    "description": "Ref of a button that opens the native file chooser (use when no input[type=file] is reachable).",
                },
                "trigger_selector": {
                    "type": "string",
                    "description": "CSS/XPath of the button opening the native file chooser.",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Absolute local file paths. For single-file inputs pass one item.",
                },
            },
            "required": ["paths"],
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
        "description": "Call this tool when the final objective is fully accomplished. The report must be a user-facing summary of what was done and the results. Do NOT mention internal task IDs, root-task status, or system-level bookkeeping — the user does not share this context.",
        "input_schema": {
            "type": "object",
            "properties": {
                "report": {
                    "type": "string",
                    "description": "Markdown formatted summary",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of generated file paths (relative to workspace) to send to user",
                },
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
    # Planner tools
    {
        "name": "plan_write",
        "description": (
            "Create or completely overwrite the current plan. Use this to "
            "dynamically (re)plan at any time: pass the full ordered list of "
            "steps. Existing steps are replaced."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "Overall goal (optional)",
                },
                "title": {
                    "type": "string",
                    "description": "Short plan title (optional)",
                },
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "Step description",
                            },
                            "status": {
                                "type": "string",
                                "enum": [
                                    "pending",
                                    "in_progress",
                                    "completed",
                                    "skipped",
                                ],
                            },
                        },
                        "required": ["content"],
                    },
                },
            },
            "required": ["steps"],
        },
    },
    {
        "name": "plan_update_step",
        "description": (
            "Update a single step's status or content without rewriting the "
            "whole plan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "step_id": {"type": "integer"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "skipped"],
                },
                "content": {"type": "string"},
            },
            "required": ["step_id"],
        },
    },
    {
        "name": "plan_read",
        "description": "Read the current plan with all steps and their status.",
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
    # Knowledge tools
    {
        "name": "knowledge_search",
        "description": "Semantic search in selected knowledge folders. Use this when user asks questions about uploaded knowledge files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default 5)",
                },
            },
            "required": ["query"],
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
    # Scheduled task tools
    {
        "name": "schedule_task",
        "description": (
            "Add a scheduled/recurring task. The bot will execute the given prompt "
            "at the specified cron schedule. Results will be sent back to this conversation. "
            "Use this for reminders, daily reports, periodic checks, etc. "
            "Cron format: 'minute hour day month weekday' (e.g. '0 8 * * *' = daily at 8am)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cron": {
                    "type": "string",
                    "description": "Cron expression. e.g. '0 8 * * *' = 8am daily, '0 10 * * 1' = 10am every Monday",
                },
                "prompt": {
                    "type": "string",
                    "description": "The full prompt to send to the bot at the scheduled time. Include all necessary details for the task.",
                },
                "description": {
                    "type": "string",
                    "description": "Short human-readable description (e.g. 'Daily Bilibili report')",
                },
                "debug": {
                    "type": "boolean",
                    "description": "If true, the raw prompt will be sent to this conversation when the task triggers. Default: false",
                },
            },
            "required": ["cron", "prompt", "description"],
        },
    },
    {
        "name": "list_scheduled_tasks",
        "description": "List all scheduled tasks created in this conversation, with their status.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "cancel_scheduled_task",
        "description": "Cancel a previously scheduled task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID to cancel (from list_scheduled_tasks)",
                },
            },
            "required": ["task_id"],
        },
    },
]


def _get_block_type(block) -> str:
    if isinstance(block, dict):
        return block.get("type", "")
    return getattr(block, "type", "")


def _get_block_text(block) -> str:
    if isinstance(block, dict):
        return block.get("text", "")
    return getattr(block, "text", "")


def _extract_tool_use(block) -> tuple[str, str, dict]:
    if isinstance(block, dict):
        return (
            str(block.get("id", "")),
            str(block.get("name", "")),
            block.get("input", {}) or {},
        )
    return (
        str(getattr(block, "id", "")),
        str(getattr(block, "name", "")),
        getattr(block, "input", {}) or {},
    )


def _extract_text_parts(blocks: list) -> list[str]:
    text_parts: list[str] = []
    for block in blocks:
        if _get_block_type(block) == "text":
            text = _get_block_text(block)
            if text:
                text_parts.append(text)
    return text_parts


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


_MEMORY_UPDATE_RE = re.compile(
    r"\[Memory Update\]\s*\n(.*?)\n\[/Memory Update\]",
    re.DOTALL | re.IGNORECASE,
)


def _parse_memory_update(text: str) -> dict | None:
    """Extract [Memory Update] block from AI response text. Returns dict of fields or None."""
    m = _MEMORY_UPDATE_RE.search(text)
    if not m:
        return None
    block = m.group(1)
    result: dict = {}
    for line in block.split("\n"):
        line = line.strip()
        if not line or line.startswith("```"):
            continue
        if ": " in line:
            key, _, val = line.partition(": ")
            key = key.strip().lower().replace(" ", "_")
            if key in (
                "current_state",
                "task_spec",
                "important_files",
                "workflow",
                "errors_corrections",
                "learnings",
                "pending_tasks",
            ):
                result[key] = val.strip()
    return result if result else None


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

    # Get current plan state for context
    task_summary = plan_manager.render()

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
        client = await _get_client()
        response = await client.messages.create(
            model=model_name,
            max_tokens=2000,
            messages=[{"role": "user", "content": summary_prompt}],
        )
        text_parts = _extract_text_parts(response.content)
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
    "plan_write",
    "plan_update_step",
    "plan_read",
    "创建一个任务",
    "创建任务",
    "更新任务",
    "标记为 completed",
    "标记这个任务",
)


def _contains_explicit_task_request(text: str) -> bool:
    lowered = text.lower()
    return any(hint.lower() in lowered for hint in _EXPLICIT_TASK_HINTS)


def _should_auto_init_plan(
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


def _build_auto_plan_title(instruction: str) -> str:
    clean = re.sub(r"https?://\S+", lambda m: m.group(0)[:28], instruction).strip()
    clean = re.sub(r"^(请|帮我|麻烦|请帮我|帮忙)\s*", "", clean)
    clean = re.sub(r"\s+", " ", clean)
    first_sentence = re.split(r"[。！？\n]", clean, maxsplit=1)[0]
    title = first_sentence[:28].strip()
    if len(first_sentence) > 28:
        title += "…"
    return title or "执行用户请求"


def _auto_init_plan(
    instruction: str, images: list, uploaded_files: list
) -> dict | None:
    if not _should_auto_init_plan(instruction, images, uploaded_files):
        return None

    plan_manager.clear()
    return plan_manager.set_goal(
        goal=instruction.strip(),
        title=_build_auto_plan_title(instruction),
    )


def _normalize_info_payload(msg) -> dict:
    if isinstance(msg, dict):
        return msg
    return {"message": str(msg)}


def _create_tool_registry(
    *,
    pm: PlaywrightManager,
    page,
    effective_session_id: str,
    auto_plan: dict | None,
    emit_info,
    emit_action_required,
    emit_image,
    emit_file,
    scheduler_service=None,
    source_meta: dict = None,
) -> ToolRegistry:
    registry = ToolRegistry()

    async def _snapshot(args: dict) -> ToolExecutionResult:
        snapshot_text = await pm.get_aria_snapshot(effective_session_id)
        return ToolExecutionResult(
            output=snapshot_text if snapshot_text else "Could not capture aria snapshot."
        )

    async def _navigate(args: dict) -> ToolExecutionResult:
        if not page:
            raise RuntimeError("No active page")
        await page.goto(args["url"])
        await asyncio.sleep(2)
        return ToolExecutionResult(output="Successfully navigated.")

    async def _click(args: dict) -> ToolExecutionResult:
        if not page:
            raise RuntimeError("No active page")
        ref = args.get("ref")
        selector = args.get("selector")

        async def pick_visible(loc):
            vp = page.viewport_size or {"width": 1920, "height": 1080}
            count = await loc.count()
            for i in range(min(count, 20)):
                el = loc.nth(i)
                try:
                    if not await el.is_visible():
                        continue
                    box = await el.bounding_box()
                except Exception:
                    continue
                if not box:
                    continue
                if box["x"] < 0 or box["y"] < 0:
                    continue
                if box["x"] >= vp["width"] or box["y"] >= vp["height"]:
                    continue
                if box["width"] < 4 or box["height"] < 4:
                    continue
                try:
                    opacity = await el.evaluate(
                        "e => parseFloat(getComputedStyle(e).opacity)"
                    )
                    if opacity < 0.1:
                        continue
                except Exception:
                    pass
                return el
            return loc.first

        if ref:
            locator = await pm.locate_by_ref(ref, effective_session_id)
        elif selector:
            locator = await pick_visible(page.locator(selector))
        else:
            raise ValueError("click requires either 'ref' or 'selector'")

        try:
            await locator.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        box = await locator.bounding_box()
        if box and box["x"] >= 0 and box["y"] >= 0:
            cx = box["x"] + box["width"] / 2
            cy = box["y"] + box["height"] / 2
            await page.mouse.move(cx, cy, steps=8)
            await asyncio.sleep(0.05)
            await page.mouse.click(cx, cy)
        else:
            await locator.click(timeout=5000)
        await asyncio.sleep(1)
        return ToolExecutionResult(output="Successfully clicked.")

    async def _type_text(args: dict) -> ToolExecutionResult:
        if not page:
            raise RuntimeError("No active page")
        ref = args.get("ref")
        selector = args.get("selector")
        if ref:
            locator = await pm.locate_by_ref(ref, effective_session_id)
            await locator.fill(args["text"])
        elif selector:
            await page.fill(selector, args["text"])
        else:
            raise ValueError("type_text requires either 'ref' or 'selector'")
        return ToolExecutionResult(output="Successfully typed text.")

    async def _upload_file(args: dict) -> ToolExecutionResult:
        if not page:
            raise RuntimeError("No active page")
        paths = args.get("paths") or []
        if isinstance(paths, str):
            paths = [paths]
        if not paths:
            raise ValueError("upload_file requires 'paths'")
        for p in paths:
            if not os.path.isabs(p):
                raise ValueError(f"Path must be absolute: {p}")
            if not os.path.exists(p):
                raise FileNotFoundError(f"File not found: {p}")

        ref = args.get("ref")
        selector = args.get("selector")
        trigger_ref = args.get("trigger_ref")
        trigger_selector = args.get("trigger_selector")

        if ref or selector:
            if ref:
                locator = await pm.locate_by_ref(ref, effective_session_id)
            else:
                locator = page.locator(selector).first
            await locator.set_input_files(paths)
        elif trigger_ref or trigger_selector:
            async with page.expect_file_chooser(timeout=10000) as fc_info:
                if trigger_ref:
                    trig = await pm.locate_by_ref(trigger_ref, effective_session_id)
                else:
                    trig = page.locator(trigger_selector).first
                await trig.click(timeout=5000)
            file_chooser = await fc_info.value
            await file_chooser.set_files(paths)
        else:
            raise ValueError(
                "upload_file requires ref/selector (for the <input type=file>) "
                "or trigger_ref/trigger_selector (for the opener button)"
            )
        await asyncio.sleep(1)
        return ToolExecutionResult(output=f"Uploaded {len(paths)} file(s).")

    async def _scroll(args: dict) -> ToolExecutionResult:
        if not page:
            raise RuntimeError("No active page")
        direction = args.get("direction", "down")
        if direction == "down":
            await page.mouse.wheel(0, 1000)
        else:
            await page.mouse.wheel(0, -1000)
        await asyncio.sleep(1)
        return ToolExecutionResult(output="Scrolled.")

    async def _request_human_assistance(args: dict) -> ToolExecutionResult:
        reason = args.get("reason", "Login required.")
        await pm.block_for_human(emit_action_required, reason, effective_session_id)
        return ToolExecutionResult(
            output=(
                "Human has processed the request. Page might have updated. "
                "You may resume your task."
            )
        )

    async def _extract_info(args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(output=f"Extracted: {args['info_summary']}")

    async def _send_screenshot(args: dict) -> ToolExecutionResult:
        description = args.get("description", "Current page screenshot")
        screenshot_b64 = await pm.get_page_screenshot_base64(effective_session_id)
        if screenshot_b64:
            await emit_image(description, screenshot_b64)
            return ToolExecutionResult(output=f"Screenshot sent to user: {description}")
        return ToolExecutionResult(output="Failed to capture screenshot.")

    async def _finish_task(args: dict) -> ToolExecutionResult:
        report = args.get("report", "Task completed.")
        if auto_plan:
            plan_manager.mark_all("completed")
        await emit_info(
            {
                "message": f"✅ **Task Completed**:\n\n{report}",
                "message_key": "common.task_completed",
                "params": {"report": report},
            }
        )
        return ToolExecutionResult(output="Finished.", finished=True)

    async def _read_file(args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(
            output=await workspace.read_file(args["path"], args.get("limit"))
        )

    async def _write_file(args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(
            output=await workspace.write_file(args["path"], args["content"])
        )

    async def _edit_file(args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(
            output=await workspace.edit_file(args["path"], args["old_text"], args["new_text"])
        )

    async def _send_file(args: dict) -> ToolExecutionResult:
        file_path = args["path"]
        description = args.get("description", f"File: {file_path}")
        full_path = WORKDIR / file_path
        if not full_path.exists():
            return ToolExecutionResult(output=f"Error: File not found: {file_path}")
        if not str(full_path.resolve()).startswith(str(WORKDIR.resolve())):
            return ToolExecutionResult(output=f"Error: Path escapes workspace: {file_path}")
        await emit_file(file_path, description)
        return ToolExecutionResult(output=f"File sent: {file_path}")

    async def _run_bash(args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(
            output=await workspace.run_bash(args["command"], args.get("timeout", 120))
        )

    async def _plan_write(args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(
            output=plan_manager.write(
                steps=args.get("steps", []),
                goal=args.get("goal"),
                title=args.get("title"),
            )
        )

    async def _plan_update_step(args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(
            output=plan_manager.update_step(
                args["step_id"],
                args.get("status"),
                args.get("content"),
            )
        )

    async def _plan_read(args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(output=plan_manager.render())

    async def _background_run(args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(
            output=await background_manager.run(
                args["command"], args.get("timeout"), effective_session_id
            )
        )

    async def _check_background(args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(
            output=await background_manager.check(args.get("task_id"))
        )

    async def _knowledge_search(args: dict) -> ToolExecutionResult:
        query = str(args.get("query", "")).strip()
        if not query:
            return ToolExecutionResult(output="Error: query is required")
        top_k = int(args.get("top_k", 5) or 5)
        top_k = max(1, min(20, top_k))
        results = knowledge_service.search(query=query, top_k=top_k)
        if not results:
            return ToolExecutionResult(output="No relevant knowledge found in selected folders.")
        return ToolExecutionResult(
            output=json.dumps({"results": results}, ensure_ascii=False, indent=2)
        )

    async def _compact(args: dict) -> ToolExecutionResult:
        focus = args.get("focus")
        return ToolExecutionResult(
            output=f"Manual compression requested{': ' + focus if focus else ''}.",
            manual_compact=True,
            compact_focus=focus,
        )

    # ── Scheduled Task Tools ──────────────────────────────────

    async def _schedule_task(args: dict) -> ToolExecutionResult:
        if scheduler_service is None:
            return ToolExecutionResult(
                output="Error: SchedulerService is not available. "
                       "Scheduled tasks are only supported in run_all.py mode."
            )
        from scheduler_service import ScheduledTask
        import uuid

        task = ScheduledTask.new(
            cron_expr=args["cron"],
            description=args["description"],
            prompt=args["prompt"],
            source_session_id=source_meta.get("session_id", effective_session_id) if source_meta else effective_session_id,
            source_chat_id=source_meta.get("chat_id", "") if source_meta else "",
            source_platform=source_meta.get("platform", "unknown") if source_meta else "web",
            debug=args.get("debug", False),
        )
        scheduler_service.add(task)

        return ToolExecutionResult(
            output=(
                f"已添加定时任务：\n"
                f"- 描述：{task.description}\n"
                f"- Cron：{task.cron_expr}\n"
                f"- 任务ID：{task.task_id}\n"
                f"- Debug模式：{'开启' if task.debug else '关闭'}"
            )
        )

    async def _list_scheduled_tasks(args: dict) -> ToolExecutionResult:
        if scheduler_service is None:
            return ToolExecutionResult(output="SchedulerService not available.")
        tasks = scheduler_service.list_by_session(
            source_meta.get("session_id", effective_session_id) if source_meta else effective_session_id
        )
        if not tasks:
            return ToolExecutionResult(output="当前没有定时任务。")
        lines = ["当前定时任务：", ""]
        for i, t in enumerate(tasks, 1):
            status_icon = "✅" if t.last_status == "success" else ("❌" if t.last_status else "⏳")
            last_run = f"上次执行：{t.last_run_at}" if t.last_run_at else "尚未执行"
            lines.append(f"[{i}] {status_icon} {t.description}")
            lines.append(f"    Cron: {t.cron_expr} | {last_run}")
            lines.append(f"    ID: {t.task_id}")
            lines.append("")
        return ToolExecutionResult(output="\n".join(lines))

    async def _cancel_scheduled_task(args: dict) -> ToolExecutionResult:
        if scheduler_service is None:
            return ToolExecutionResult(output="SchedulerService not available.")
        ok = scheduler_service.remove(args["task_id"])
        if ok:
            return ToolExecutionResult(output=f"已取消定时任务 {args['task_id']}")
        return ToolExecutionResult(output=f"未找到定时任务 {args['task_id']}")

    registry.register("schedule_task", _schedule_task)
    registry.register("list_scheduled_tasks", _list_scheduled_tasks)
    registry.register("cancel_scheduled_task", _cancel_scheduled_task)

    registry.register("snapshot", _snapshot)
    registry.register("navigate", _navigate)
    registry.register("click", _click)
    registry.register("type_text", _type_text)
    registry.register("upload_file", _upload_file)
    registry.register("scroll", _scroll)
    registry.register("request_human_assistance", _request_human_assistance)
    registry.register("extract_info", _extract_info)
    registry.register("send_screenshot", _send_screenshot)
    registry.register("finish_task", _finish_task)
    registry.register("read_file", _read_file)
    registry.register("write_file", _write_file)
    registry.register("edit_file", _edit_file)
    registry.register("send_file", _send_file)
    registry.register("run_bash", _run_bash)
    registry.register("plan_write", _plan_write)
    registry.register("plan_update_step", _plan_update_step)
    registry.register("plan_read", _plan_read)
    registry.register("background_run", _background_run)
    registry.register("check_background", _check_background)
    registry.register("knowledge_search", _knowledge_search)
    registry.register("compact", _compact)

    return registry


# ============== LLM Call with Compatibility Retry ==============

_LLM_IMAGE_KEYWORDS = ("image_url", "validation errors for ValidatorIterator")


async def _call_llm_with_retry(model, messages, system, tools, emit_info):
    """
    Call the LLM with staged fallback for gateway/proxy compatibility issues.

    Retry stages:
      1. Strip images from the last user message (gateway rejecting vision).
      2. Strip images + send no tools (gateway/SDK type mismatch).
    Only breaks the agent loop when all stages are exhausted.
    """
    client = await _get_client()
    for stage in range(3):
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                messages=messages,
                tools=tools,
            )
            return response.content
        except Exception as e:
            err_text = str(e)
            is_image_err = any(kw in err_text for kw in _LLM_IMAGE_KEYWORDS)

            if stage == 0:
                if is_image_err:
                    _strip_images_from_last_user(messages)
                    await emit_info({
                        "message": "当前模型网关不接受图片输入，已自动切换为纯文本模式继续执行。",
                        "message_key": "common.image_input_disabled",
                    })
                    continue
                # Non-image error: try stage 1 (strip images anyway)
                _strip_images_from_last_user(messages)
                logger.warning("LLM error (stage 0), retrying without images: %s", err_text[:200])
                continue

            if stage == 1:
                tools = None
                logger.warning("LLM error (stage 1), retrying without tools: %s", err_text[:200])
                continue

            # All stages exhausted
            import traceback
            logger.error("LLM call failed after 3 retries: %s\n%s", err_text, traceback.format_exc())
            await emit_info({"message": f"LLM 调用失败: {err_text}", "message_key": "common.error"})
            return None


def _strip_images_from_last_user(messages):
    """Remove image blocks from the last user message in-place."""
    if not messages:
        return
    last = messages[-1]
    if last.get("role") != "user":
        return
    content = last.get("content")
    if not isinstance(content, list):
        return
    last["content"] = [
        block for block in content
        if not (isinstance(block, dict) and block.get("type") == "image")
    ]


# ============== Main Agent Loop ==============


async def run_agent_loop(
    pm: PlaywrightManager,
    user_instruction: str,
    ws_send_msg=None,
    ws_request_action=None,
    ws_send_image=None,
    ws_send_file=None,
    message_center: MessageCenter | None = None,
    images: list = [],
    history_messages: list = [],
    uploaded_files: list = [],
    session_store=None,
    session_id: str = None,
    web_queue_getter=None,
    web_session_id: str = None,
    cancel_event: asyncio.Event = None,
    session_memory: SessionMemory | None = None,
    save_session_memory_fn=None,
    tool_overrides: dict = None,
    scheduler_service=None,
    source_meta: dict = None,
):
    effective_session_id = web_session_id or session_id

    async def emit_info(msg) -> None:
        payload = _normalize_info_payload(msg)
        if message_center:
            await message_center.publish("info", payload)
            return
        if ws_send_msg:
            await ws_send_msg(payload)

    async def emit_action_required(reason: str, image: str | None = None) -> None:
        payload = {"reason": reason}
        if image:
            payload["image"] = image
        if message_center:
            await message_center.publish("action_required", payload)
            return
        if ws_request_action:
            await ws_request_action(reason, image)

    async def emit_image(description: str, image_b64: str) -> None:
        payload = {"description": description, "image": image_b64}
        if message_center:
            await message_center.publish("image", payload)
            return
        if ws_send_image:
            await ws_send_image(description, image_b64)

    async def emit_file(file_path: str, description: str) -> None:
        payload = {"path": file_path, "description": description}
        if message_center:
            await message_center.publish("send_file", payload)
            return
        if ws_send_file:
            await ws_send_file(file_path, description)

    if not effective_session_id:
        await emit_info(
            {"message": "Error: No session ID provided", "message_key": "common.error"}
        )
        return

    if session_memory is None:
        session_memory = SessionMemory(session_id=effective_session_id)
    if not session_memory.get("task_spec"):
        session_memory.update("task_spec", user_instruction)
    if not session_memory.get("current_state"):
        session_memory.update("current_state", "Task started")

    try:
        page = await pm.get_or_create_page(effective_session_id)
    except Exception as e:
        await emit_info(
            {
                "message": f"Error creating browser tab: {e}",
                "message_key": "common.error",
            }
        )
        return

    auto_plan = _auto_init_plan(user_instruction, images, uploaded_files)

    await emit_info(
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

    if auto_plan:
        user_content[0]["text"] += (
            "\n\nA plan has been auto-initialized for this request:\n"
            f"- goal: {auto_plan.get('goal', '')}\n"
            "- It currently has no steps. Use `plan_write` to lay out the ordered "
            "steps, then keep their status updated as you work.\n"
            "- Re-plan with `plan_write` whenever the situation changes.\n"
            "- Mark all steps completed before calling finish_task.\n"
            "- Do NOT mention internal plan/step IDs or status bookkeeping in "
            "user-facing reports."
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
            if auto_plan:
                plan_manager.pause()
            await emit_info(
                {
                    "message": "Task cancelled by user.",
                    "message_key": "common.task_cancelled",
                }
            )
            break

        if pm.check_and_clear_pause_request(effective_session_id):
            await emit_info(
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
            await emit_info(
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
        assistant_blocks = await _call_llm_with_retry(
            model_name,
            messages,
            f"{SYSTEM_PROMPT}\n\n{session_memory.get_all()}",
            TOOLS,
            emit_info,
        )
        if assistant_blocks is None:
            break

        messages.append({"role": "assistant", "content": assistant_blocks})

        assistant_text = "\n".join(_extract_text_parts(assistant_blocks))
        memory_update = _parse_memory_update(assistant_text)
        if memory_update:
            for key, value in memory_update.items():
                session_memory.update(key, value)
            if save_session_memory_fn:
                save_session_memory_fn()

        # 3. Act
        tool_uses = [block for block in assistant_blocks if _get_block_type(block) == "tool_use"]
        user_content = []

        if not tool_uses:
            text_blocks = _extract_text_parts(assistant_blocks)
            if text_blocks:
                msg = "\n".join(text_blocks)
                await emit_info(msg)
            is_finished = True
            break

        manual_compact = False
        manual_compact_focus = None
        tool_registry = _create_tool_registry(
            pm=pm,
            page=page,
            effective_session_id=effective_session_id,
            auto_plan=auto_plan,
            emit_info=emit_info,
            emit_action_required=emit_action_required,
            emit_image=emit_image,
            emit_file=emit_file,
            scheduler_service=scheduler_service,
            source_meta=source_meta,
        )
        if tool_overrides:
            for name, handler in tool_overrides.items():
                tool_registry.register(name, handler)

        for tool in tool_uses:
            tool_id, tool_name, args = _extract_tool_use(tool)
            result_str = ""

            args_json = json.dumps(args, ensure_ascii=False)
            await emit_info(
                {
                    "message": f"Executing action: `{tool_name}` with args: {args_json}",
                    "message_key": "common.executing_action",
                    "params": {"tool": tool_name, "args": args_json},
                }
            )

            try:
                execution = await tool_registry.execute(tool_name, args)
                result_str = execution.output
                if execution.finished:
                    is_finished = True
                if execution.manual_compact:
                    manual_compact = True
                    manual_compact_focus = execution.compact_focus

            except Exception as e:
                result_str = f"Error executing {tool_name}: {str(e)}"

            user_content.append(
                {"type": "tool_result", "tool_use_id": tool_id, "content": result_str}
            )

        # === NEW: Handle manual compact (Layer 3) ===
        if manual_compact:
            messages[:] = await auto_compact(messages, manual_compact_focus)
            # Reset user_content after compression
            user_content = []

        if is_finished:
            break

    if not is_finished:
        if auto_plan:
            plan_manager.pause()
        await emit_info(
            {
                "message": "⚠️ Task reached maximum steps without calling finish_task.",
                "message_key": "common.max_steps_error",
            }
        )

    if is_finished:
        session_memory.update("current_state", "Task completed")
    else:
        session_memory.update("current_state", "Task ended (max steps or cancelled)")

    if save_session_memory_fn:
        save_session_memory_fn()

    pm.deactivate_tab(effective_session_id)
