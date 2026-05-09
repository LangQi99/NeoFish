import os
import json
import asyncio
import logging
import time
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from anthropic import AsyncAnthropic
from playwright_manager import PlaywrightManager
from workspace_manager import WorkspaceManager
from task_manager import task_manager
from background_manager import background_manager
from memory.session_memory import SessionMemory
from knowledge_service import KnowledgeService
from message_center import MessageCenter
from tool_registry import ToolExecutionResult, ToolRegistry

logger = logging.getLogger(__name__)

load_dotenv()

client = AsyncAnthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"), base_url=os.getenv("ANTHROPIC_BASE_URL")
)
model_name = os.getenv("MODEL_NAME", "MiniMax-M2.7")

# Configuration
WORKDIR = Path(os.getenv("WORKDIR", "./workspace")).resolve()
TOKEN_THRESHOLD = int(os.getenv("TOKEN_THRESHOLD", "800000"))
MAX_TOKEN = int(os.getenv("MAX_TOKEN", "1000000"))
TRANSCRIPT_DIR = Path(os.getenv("TRANSCRIPT_DIR", "./.transcripts")).resolve()
KEEP_RECENT = 3  # For microcompact

# Initialize managers
workspace = WorkspaceManager(WORKDIR, strict=False)
knowledge_service = KnowledgeService(WORKDIR)

SYSTEM_PROMPT = """# Identity
You are NeoFish, a browser-first general-purpose digital labor agent. Your job is to help ordinary users get real work done across websites, web apps, and connected platforms by carrying out actions, extracting information, and coordinating multi-step tasks on their behalf.

You can:
1. Browse the web and operate pages
2. Click, type, navigate, scroll, inspect, and extract information
3. Pause for human takeover when the task truly needs human intervention
4. Manage persistent tasks across long conversations
5. Read, write, and edit files when the task needs file handling
6. Run commands or search knowledge folders when they genuinely help complete the task
7. Send files or screenshots back to the user

## Primary Goal
- Be useful, accurate, and persistent.
- Prefer completing the user's real-world task over giving abstract advice.
- Default to acting as an execution agent, not just a conversational assistant.
- Treat browser interaction, information retrieval, and digital task completion as the primary workflow.
- When blocked, identify the real blocker and choose the next best action instead of looping blindly.

## Safety Boundaries
- Operate inside the current browser session, connected platform session, and workspace boundaries.
- Do not perform destructive or high-risk actions unless they are clearly necessary and appropriately justified.
- Do not assume one approval implies future approval for unrelated risky actions.
- If you hit a login wall, CAPTCHA, QR-code scan, or user-only verification step, call `request_human_assistance`.
- Do not fabricate having run tools, changed files, or verified results when you have not.

## Behavior Guidelines
- First understand what the user is actually trying to get done in the digital world: browse, search, compare, summarize, submit, collect, monitor, or produce.
- Prefer completing tasks directly in the browser or platform when that is the natural path.
- Use files, shell commands, and workspace editing as support capabilities, not as the default center of the task.
- Prefer fixing the cause of a problem over repeatedly retrying the same failing action.
- If something is ambiguous, gather evidence with tools before making assumptions.
- For multi-step work, maintain task state proactively and keep the root task accurate.
- Do not restart solved work after context compression; continue from the latest known state.

## Tool Use Guidelines
- Prefer dedicated tools over generic shell commands whenever a dedicated tool exists.
- Prefer browser tools before workspace tools when the task is fundamentally web-based.
- Use `read_file`, `write_file`, and `edit_file` for file operations instead of shell-based file manipulation.
- Use `snapshot` before `click` or `type_text` whenever you need reliable page references.
- Prefer ref-based interaction (`ref=e1`) over CSS/XPath selectors.
- Use `background_run` only for genuinely long-running commands. Use `run_bash` for short blocking commands.
- Use `knowledge_search` only when relevant knowledge folders may contain useful information for the task.

## Browser Workflow
The browser is your main working surface.

You observe the page in two ways:
1. Screenshots attached automatically during the loop
2. `snapshot`, which returns an ARIA accessibility tree with stable refs

When interacting with the page:
- Prefer `snapshot` + `ref`
- Fall back to selectors only when refs are unavailable
- Re-observe the page after meaningful navigation or interaction if the state may have changed
- When collecting information, extract what matters to the user's goal instead of copying noise
- When a user asks for a web task, keep moving the task forward until the result is delivered or human help is required

## Human Collaboration
- NeoFish is allowed to pause and ask the user to take over when the task requires human identity, verification, or judgment that cannot be automated safely.
- When takeover is needed, explain the blocker clearly and preserve continuity so execution can resume smoothly afterward.

## File And Command Safety
- Files and commands are auxiliary capabilities. Use them when they help the user's end goal, not just because they are available.
- Read before editing when the file content matters.
- Make precise edits when possible instead of rewriting large files unnecessarily.
- Use relative workspace paths like `src/main.py` or `data/config.json`.
- Avoid absolute paths unless they are explicitly required.
- If you need to confirm location or inspect the workspace, use safe shell commands such as `pwd`, `ls`, or similar read-only inspection.
- Treat shell as a power tool: use it deliberately, keep commands scoped, and avoid risky patterns unless the user explicitly wants them.

## Task Management
Tasks persist across context compression. Use them for non-trivial work.
- If the system says a root task was auto-created, do not create a duplicate.
- Update relevant tasks as the work moves from planning to execution to completion.
- Mark the root task completed before calling `finish_task`.
- Use task tracking to keep long-running browsing or multi-platform workflows coherent.

## Plan Mode
You support a dedicated planning workflow:
- Use `enter_plan_mode` when the task needs investigation, scoping, design, workflow planning, or user approval before execution.
- While planning, do not modify project files or browser state outside the dedicated plan file.
- `enter_plan_mode` may be called again while planning to overwrite the plan file with a refined version.
- The plan should be concrete and execution-ready, not vague brainstorming.
- Use `exit_plan_mode` only when the plan is ready for review.
- After calling `exit_plan_mode`, stop execution and wait for approval or revision feedback.

## Completion And Communication
- When the task is fully completed, call `finish_task`.
- If the user asked for a deliverable such as a summary, screenshot, structured result, or file, make sure you actually provide it.
- If you need more user input, ask for the minimum missing information clearly.
- If you are waiting for approval, do not continue implementation.

## Output Style
- Be concise between tool calls.
- Do not narrate obvious actions with unnecessary filler.
- Prefer short, factual updates while working.
- Give fuller explanations only when presenting results, blockers, or decisions.

__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__

## Environment
Workspace root: {workdir}
- All file operations must stay within this workspace unless explicitly instructed otherwise.
- The system resolves relative paths against this workspace automatically.

## Session Memory
You will be given structured Session Memory. Treat it as the canonical summary of this conversation's current state.
- Use it to avoid forgetting task progress, important files, errors, and pending work.
- Respect it when context has been compressed.
- Update it when meaningful progress happens.

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
- `current_state` is the most important field.
- Keep each field concise.
- Do not output the block if nothing meaningful changed.
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
                    "enum": [
                        "pending",
                        "planning",
                        "awaiting_approval",
                        "in_progress",
                        "completed",
                    ],
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
    {
        "name": "enter_plan_mode",
        "description": (
            "Enter planning mode and create or overwrite the session plan file. "
            "Use this before implementation when you need to investigate first or "
            "present a plan for approval. You may call it again while planning to "
            "replace the plan file with refined markdown."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "Planning goal or scope summary (optional)",
                },
                "plan_markdown": {
                    "type": "string",
                    "description": "Full markdown content to write into the plan file (optional)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "exit_plan_mode",
        "description": (
            "Submit the current plan for user approval and pause execution. "
            "Only use this after the plan file is ready."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Short summary of the proposed plan (optional)",
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

_PLAN_MODES = {"execution", "planning", "awaiting_approval"}
_PLAN_ALLOWED_TOOLS = {
    "snapshot",
    "read_file",
    "extract_info",
    "knowledge_search",
    "task_list",
    "task_get",
    "run_bash",
    "compact",
    "request_human_assistance",
    "send_screenshot",
    "enter_plan_mode",
    "exit_plan_mode",
}
_PLAN_READ_ONLY_COMMAND_PREFIXES = (
    "pwd",
    "ls",
    "dir",
    "get-location",
    "get-childitem",
    "rg ",
    "rg.exe ",
    "type ",
    "cat ",
    "git status",
    "git diff --stat",
    "git diff --name-only",
)
_PLAN_DISALLOWED_COMMAND_SNIPPETS = (
    ">>",
    ">",
    "set-content",
    "add-content",
    "out-file",
    "new-item",
    "remove-item",
    "rename-item",
    "move-item",
    "copy-item",
    "del ",
    "rm ",
    "mv ",
    "cp ",
    "mkdir ",
    "touch ",
)


def _default_plan_file(session_id: str | None) -> str:
    suffix = session_id or "current"
    return f".plans/plan-{suffix}.md"


def _normalize_plan_state(
    plan_state: dict | None, session_id: str | None
) -> dict[str, str | bool]:
    state = dict(plan_state or {})
    mode = str(state.get("mode") or "execution").strip().lower()
    if mode not in _PLAN_MODES:
        mode = "execution"
    state["mode"] = mode
    state["awaiting_approval"] = mode == "awaiting_approval"
    state["plan_file"] = str(state.get("plan_file") or _default_plan_file(session_id))
    return state


def _get_tools_for_mode(mode: str) -> list[dict]:
    if mode == "planning":
        return [tool for tool in TOOLS if tool["name"] in _PLAN_ALLOWED_TOOLS]
    if mode == "awaiting_approval":
        return [tool for tool in TOOLS if tool["name"] in {"enter_plan_mode", "exit_plan_mode"}]
    return TOOLS


def _is_read_only_bash_command(command: str) -> bool:
    normalized = (command or "").strip().lower()
    if not normalized:
        return False
    if any(snippet in normalized for snippet in _PLAN_DISALLOWED_COMMAND_SNIPPETS):
        return False
    return any(normalized.startswith(prefix) for prefix in _PLAN_READ_ONLY_COMMAND_PREFIXES)


def _merge_memory_line(existing: str, line: str) -> str:
    clean_line = (line or "").strip()
    if not clean_line:
        return existing
    lines = [item.strip() for item in existing.splitlines() if item.strip()]
    if clean_line not in lines:
        lines.append(clean_line)
    return "\n".join(lines)


def _build_plan_template(goal: str, plan_file: str) -> str:
    safe_goal = goal.strip() or "Plan the requested work"
    return (
        f"# Execution Plan\n\n"
        f"Plan file: `{plan_file}`\n\n"
        f"## Goal\n{safe_goal}\n\n"
        f"## Current Understanding\n- ...\n\n"
        f"## Risks\n- ...\n\n"
        f"## Implementation Steps\n1. ...\n\n"
        f"## Validation\n- ...\n\n"
        f"## User Confirmation Needed\n- ...\n"
    )


def _build_mode_system_prompt(plan_state: dict) -> str:
    mode = str(plan_state.get("mode") or "execution")
    plan_file = str(plan_state.get("plan_file") or "")
    lines = [
        "## Runtime Plan State",
        f"- Current mode: {mode}",
        f"- Plan file: {plan_file or '(none)'}",
    ]
    if mode == "planning":
        lines.extend(
            [
                "- You are in planning mode.",
                "- Research and analyze only; do not implement changes yet.",
                "- Use `enter_plan_mode` to create or overwrite the plan markdown.",
                "- When the plan is ready for review, call `exit_plan_mode`.",
            ]
        )
    elif mode == "awaiting_approval":
        lines.extend(
            [
                "- A plan has already been submitted for approval.",
                "- Do not continue work until the user approves it or requests changes.",
            ]
        )
    elif plan_file:
        lines.append(
            f"- If an approved plan exists in `{plan_file}`, follow it during execution unless the user changes direction."
        )
    return "\n".join(lines)


def _load_existing_root_task(task_id: int | None) -> dict | None:
    if not task_id:
        return None
    raw = task_manager.get(int(task_id))
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if isinstance(data, dict) and "id" in data:
        return data
    return None


def _task_status_for_plan_mode(mode: str) -> str:
    if mode == "planning":
        return "planning"
    if mode == "awaiting_approval":
        return "awaiting_approval"
    return "in_progress"


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


def _normalize_info_payload(msg) -> dict:
    if isinstance(msg, dict):
        return msg
    return {"message": str(msg)}


def _create_tool_registry(
    *,
    pm: PlaywrightManager,
    page,
    effective_session_id: str,
    auto_root_task: dict | None,
    emit_info,
    emit_action_required,
    emit_image,
    emit_file,
    session_memory: SessionMemory,
    save_session_memory_fn=None,
    plan_state: dict | None = None,
    save_plan_state_fn=None,
    emit_task_status=None,
) -> ToolRegistry:
    registry = ToolRegistry()
    if plan_state is None:
        current_plan_state = _normalize_plan_state(None, effective_session_id)
    else:
        previous_state = dict(plan_state)
        current_plan_state = plan_state
        current_plan_state.clear()
        current_plan_state.update(
            _normalize_plan_state(previous_state, effective_session_id)
        )

    def _save_plan_state() -> None:
        if save_plan_state_fn:
            save_plan_state_fn(current_plan_state)

    def _save_session_memory() -> None:
        if save_session_memory_fn:
            save_session_memory_fn()

    async def _set_runtime_plan_mode(mode: str) -> None:
        current_plan_state["mode"] = mode
        current_plan_state["awaiting_approval"] = mode == "awaiting_approval"
        current_plan_state["updated_at"] = datetime.now().isoformat()
        if emit_task_status:
            await emit_task_status("planning" if mode == "planning" else mode)
        _save_plan_state()

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
        if ref:
            locator = await pm.locate_by_ref(ref, effective_session_id)
            await locator.click(timeout=5000)
        elif selector:
            await page.click(selector, timeout=5000)
        else:
            raise ValueError("click requires either 'ref' or 'selector'")
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
        if auto_root_task:
            task_manager.update(auto_root_task["id"], status="completed")
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
        command = args["command"]
        if current_plan_state.get("mode") == "planning" and not _is_read_only_bash_command(
            command
        ):
            return ToolExecutionResult(
                output=(
                    "Error: run_bash is restricted in planning mode. "
                    "Only read-only commands like pwd, ls/dir, rg, type/cat, or git status/diff are allowed."
                )
            )
        return ToolExecutionResult(
            output=await workspace.run_bash(command, args.get("timeout", 120))
        )

    async def _task_create(args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(
            output=task_manager.create(args["subject"], args.get("description", ""))
        )

    async def _task_get(args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(output=task_manager.get(args["task_id"]))

    async def _task_update(args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(
            output=task_manager.update(
                args["task_id"],
                args.get("status"),
                args.get("addBlockedBy"),
                args.get("addBlocks"),
            )
        )

    async def _task_list(args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(output=task_manager.list_all())

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

    async def _enter_plan_mode(args: dict) -> ToolExecutionResult:
        goal = str(args.get("goal") or session_memory.get("task_spec") or "").strip()
        plan_file = str(current_plan_state.get("plan_file") or _default_plan_file(effective_session_id))
        current_plan_state["plan_file"] = plan_file
        await _set_runtime_plan_mode("planning")

        plan_markdown = str(args.get("plan_markdown") or "").strip()
        plan_abs = (WORKDIR / plan_file).resolve()
        should_seed_template = not plan_abs.exists() and not plan_markdown
        if should_seed_template:
            plan_markdown = _build_plan_template(goal, plan_file)
        if plan_markdown:
            await workspace.write_file(plan_file, plan_markdown)

        session_memory.update("current_state", "In planning mode")
        session_memory.update(
            "important_files",
            _merge_memory_line(session_memory.get("important_files"), plan_file),
        )
        session_memory.update(
            "pending_tasks",
            "Draft or refine the plan, then submit it for approval.",
        )
        session_memory.update(
            "workflow",
            f"Planning mode active. Maintain the proposal in {plan_file} and wait for approval before implementation.",
        )
        if auto_root_task:
            task_manager.update(auto_root_task["id"], status="planning")
        _save_session_memory()

        if plan_markdown:
            return ToolExecutionResult(
                output=(
                    f"Planning mode enabled. Plan file `{plan_file}` has been written. "
                    "Continue researching and call `enter_plan_mode` again with refined plan_markdown whenever needed."
                )
            )
        return ToolExecutionResult(
            output=(
                f"Planning mode enabled. Use the plan file `{plan_file}` for the proposal. "
                "Call `enter_plan_mode` again with `plan_markdown` to overwrite it."
            )
        )

    async def _exit_plan_mode(args: dict) -> ToolExecutionResult:
        plan_file = str(current_plan_state.get("plan_file") or _default_plan_file(effective_session_id))
        plan_abs = (WORKDIR / plan_file).resolve()
        if not plan_abs.exists():
            return ToolExecutionResult(
                output=(
                    f"Error: plan file `{plan_file}` does not exist yet. "
                    "Call `enter_plan_mode` with `plan_markdown` first."
                )
            )

        plan_text = await workspace.read_file(plan_file)
        summary = str(args.get("summary") or "").strip()
        await _set_runtime_plan_mode("awaiting_approval")
        if summary:
            current_plan_state["last_summary"] = summary

        session_memory.update("current_state", "Awaiting plan approval")
        session_memory.update(
            "important_files",
            _merge_memory_line(session_memory.get("important_files"), plan_file),
        )
        session_memory.update(
            "pending_tasks",
            f"Await user approval for the plan in {plan_file}.",
        )
        session_memory.update(
            "workflow",
            f"Plan submitted for approval. Wait for user confirmation before implementing {plan_file}.",
        )
        if auto_root_task:
            task_manager.update(auto_root_task["id"], status="awaiting_approval")
        _save_session_memory()

        approval_message = (
            "Plan ready for approval.\n\n"
            f"Plan file: `{plan_file}`\n"
        )
        if summary:
            approval_message += f"\nSummary: {summary}\n"
        approval_message += f"\n```md\n{plan_text[:12000]}\n```"
        await emit_info({"message": approval_message})
        return ToolExecutionResult(
            output=(
                f"Submitted the plan in `{plan_file}` for approval. "
                "Pause execution until the user approves it or requests revisions."
            ),
            stop_loop=True,
        )

    async def _compact(args: dict) -> ToolExecutionResult:
        focus = args.get("focus")
        return ToolExecutionResult(
            output=f"Manual compression requested{': ' + focus if focus else ''}.",
            manual_compact=True,
            compact_focus=focus,
        )

    registry.register("snapshot", _snapshot)
    registry.register("navigate", _navigate)
    registry.register("click", _click)
    registry.register("type_text", _type_text)
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
    registry.register("task_create", _task_create)
    registry.register("task_get", _task_get)
    registry.register("task_update", _task_update)
    registry.register("task_list", _task_list)
    registry.register("background_run", _background_run)
    registry.register("check_background", _check_background)
    registry.register("knowledge_search", _knowledge_search)
    registry.register("enter_plan_mode", _enter_plan_mode)
    registry.register("exit_plan_mode", _exit_plan_mode)
    registry.register("compact", _compact)

    return registry


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
    plan_state: dict | None = None,
    save_plan_state_fn=None,
    set_runtime_status_fn=None,
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

    async def emit_task_status(status: str) -> None:
        if set_runtime_status_fn:
            set_runtime_status_fn(status)
        if message_center:
            await message_center.publish("task_status", {"status": status})

    if not effective_session_id:
        await emit_info(
            {"message": "Error: No session ID provided", "message_key": "common.error"}
        )
        return

    if session_memory is None:
        session_memory = SessionMemory(session_id=effective_session_id)
    plan_state = _normalize_plan_state(plan_state, effective_session_id)
    existing_root_task = _load_existing_root_task(plan_state.get("root_task_id"))
    if not session_memory.get("task_spec"):
        session_memory.update("task_spec", user_instruction)
    if not session_memory.get("current_state"):
        if plan_state["mode"] == "planning":
            session_memory.update("current_state", "In planning mode")
        elif plan_state["mode"] == "awaiting_approval":
            session_memory.update("current_state", "Awaiting plan approval")
        else:
            session_memory.update("current_state", "Task started")
    if save_session_memory_fn:
        save_session_memory_fn()
    if save_plan_state_fn:
        save_plan_state_fn(plan_state)

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

    auto_root_task = existing_root_task or _auto_create_root_task(
        user_instruction, images, uploaded_files
    )
    if auto_root_task and not plan_state.get("root_task_id"):
        plan_state["root_task_id"] = auto_root_task["id"]
        if save_plan_state_fn:
            save_plan_state_fn(plan_state)
    if auto_root_task:
        task_manager.update(
            auto_root_task["id"], status=_task_status_for_plan_mode(plan_state["mode"])
        )

    await emit_task_status(
        "planning" if plan_state["mode"] == "planning" else (
            "awaiting_approval" if plan_state["mode"] == "awaiting_approval" else "running"
        )
    )

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
    stopped_for_plan_approval = False

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
            f"- Its current status is `{_task_status_for_plan_mode(plan_state['mode'])}`.\n"
            "- Do not create a duplicate root task for the same request.\n"
            "- Update this root task when needed and mark it `completed` before calling finish_task.\n"
            "- You may create additional sub-tasks only if they are genuinely useful."
        )

    if plan_state["mode"] == "planning":
        user_content[0]["text"] += (
            "\n\nYou are currently in planning mode."
            f"\nUse `{plan_state['plan_file']}` as the dedicated plan file."
            "\nDo not implement changes yet."
        )
    elif plan_state["mode"] == "awaiting_approval":
        user_content[0]["text"] += (
            "\n\nA plan has already been submitted and is waiting for user approval."
            "\nDo not continue until the user confirms or requests revisions."
        )
    elif plan_state.get("plan_file"):
        user_content[0]["text"] += (
            f"\n\nIf there is an approved plan, follow `{plan_state['plan_file']}` during execution."
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
            await emit_task_status("cancelled")
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

        if plan_state["mode"] == "planning":
            user_content.append(
                {
                    "type": "text",
                    "text": (
                        f"Planning reminder: stay in planning mode and keep the proposal in `{plan_state['plan_file']}`. "
                        "Do not implement changes yet. When the proposal is ready, call `exit_plan_mode`."
                    ),
                }
            )
        elif plan_state["mode"] == "awaiting_approval":
            user_content.append(
                {
                    "type": "text",
                    "text": (
                        f"Approval reminder: the submitted plan in `{plan_state['plan_file']}` is still waiting for user approval. "
                        "Do not continue implementation until the user approves it or asks for revisions."
                    ),
                }
            )

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
        await emit_info(
            {"message": "Agent is thinking...", "message_key": "common.agent_thinking"}
        )

        try:
            current_tools = _get_tools_for_mode(str(plan_state.get("mode") or "execution"))
            current_system_prompt = (
                f"{SYSTEM_PROMPT}\n\n{_build_mode_system_prompt(plan_state)}\n\n{session_memory.get_all()}"
            )
            response = await client.messages.create(
                model=model_name,
                max_tokens=4096,
                system=current_system_prompt,
                messages=messages,
                tools=current_tools,
            )
            assistant_blocks = response.content
        except Exception as e:
            err_text = str(e)
            if "image_url" in err_text or "validation errors for ValidatorIterator" in err_text:
                user_content = [
                    block for block in user_content
                    if not (isinstance(block, dict) and block.get("type") == "image")
                ]
                messages[-1] = {"role": "user", "content": user_content}
                await emit_info(
                    {
                        "message": "当前模型网关不接受图片输入，已自动切换为纯文本模式继续执行。",
                        "message_key": "common.image_input_disabled",
                    }
                )
                try:
                    response = await client.messages.create(
                        model=model_name,
                        max_tokens=4096,
                        system=current_system_prompt,
                        messages=messages,
                        tools=current_tools,
                    )
                    assistant_blocks = response.content
                except Exception as retry_error:
                    await emit_info(f"Error calling LLM: {str(retry_error)}")
                    break
            else:
                await emit_info(f"Error calling LLM: {err_text}")
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
                break
            continue

        manual_compact = False
        manual_compact_focus = None
        stop_loop = False
        tool_registry = _create_tool_registry(
            pm=pm,
            page=page,
            effective_session_id=effective_session_id,
            auto_root_task=auto_root_task,
            emit_info=emit_info,
            emit_action_required=emit_action_required,
            emit_image=emit_image,
            emit_file=emit_file,
            session_memory=session_memory,
            save_session_memory_fn=save_session_memory_fn,
            plan_state=plan_state,
            save_plan_state_fn=save_plan_state_fn,
            emit_task_status=emit_task_status,
        )

        for tool in tool_uses:
            tool_id, tool_name, args = _extract_tool_use(tool)
            result_str = ""

            await emit_info(
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
                execution = await tool_registry.execute(tool_name, args)
                result_str = execution.output
                if execution.finished:
                    is_finished = True
                if execution.manual_compact:
                    manual_compact = True
                    manual_compact_focus = execution.compact_focus
                if execution.stop_loop:
                    stop_loop = True
                    if str(plan_state.get("mode")) == "awaiting_approval":
                        stopped_for_plan_approval = True

            except Exception as e:
                result_str = f"Error executing {tool_name}: {str(e)}"

            user_content.append(
                {"type": "tool_result", "tool_use_id": tool_id, "content": result_str}
            )

        # === NEW: Handle manual compact (Layer 3) ===
        if manual_compact:
            await emit_info(
                {
                    "message": "Manual compression triggered...",
                    "message_key": "common.manual_compressing",
                }
            )
            messages[:] = await auto_compact(messages, manual_compact_focus)
            # Reset user_content after compression
            user_content = []

        if is_finished:
            break
        if stop_loop:
            break

    if not is_finished and not stopped_for_plan_approval:
        if auto_root_task:
            task_manager.update(auto_root_task["id"], status="pending")
        await emit_info(
            {
                "message": "⚠️ Task reached maximum steps without calling finish_task.",
                "message_key": "common.max_steps_error",
            }
        )

    if stopped_for_plan_approval:
        session_memory.update("current_state", "Awaiting plan approval")
        if auto_root_task:
            task_manager.update(auto_root_task["id"], status="awaiting_approval")
    elif is_finished:
        session_memory.update("current_state", "Task completed")
        if auto_root_task:
            task_manager.update(auto_root_task["id"], status="completed")
    else:
        session_memory.update("current_state", "Task ended (max steps or cancelled)")

    if save_session_memory_fn:
        save_session_memory_fn()

    pm.deactivate_tab(effective_session_id)
    if stopped_for_plan_approval:
        return "awaiting_approval"
    if is_finished:
        return "completed"
    return "cancelled" if cancel_event and cancel_event.is_set() else "completed"
