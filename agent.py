import os
import json
import asyncio
from dotenv import load_dotenv
from anthropic import AsyncAnthropic
from playwright_manager import PlaywrightManager

load_dotenv()

client = AsyncAnthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url=os.getenv("ANTHROPIC_BASE_URL")
)
model_name = os.getenv("MODEL_NAME", "claude-3-7-sonnet-20250219")

SYSTEM_PROMPT = """You are NeoFish, an autonomous web browser agent.
Your core task is to complete the user's instructions on the web.

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

If you ever encounter a strict login wall, CAPTCHA, or require the user to scan a QR code, you must call the `request_human_assistance` tool. Do NOT give up easily; only ask for help when absolutely necessary.
When the task is completely finished, call `finish_task`.
"""

TOOLS = [
    {
        "name": "snapshot",
        "description": (
            "Return an ARIA accessibility snapshot of the current page. "
            "Each interactive element (button, textbox, link, etc.) is tagged with a "
            "stable ref ID such as [ref=e1]. Use the refs with the `click` and "
            "`type_text` tools instead of fragile CSS/XPath selectors."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "navigate",
        "description": "Navigate the browser to a specific URL.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"]
        }
    },
    {
        "name": "click",
        "description": (
            "Click an element on the page. "
            "Prefer passing a `ref` obtained from the `snapshot` tool (e.g. ref=\"e1\"). "
            "Fall back to a CSS or XPath `selector` only when no ref is available."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "Ref ID from the snapshot (e.g. \"e1\"). Takes priority over selector."
                },
                "selector": {
                    "type": "string",
                    "description": "CSS or XPath selector (fallback when ref is not available)."
                }
            },
            "required": []
        }
    },
    {
        "name": "type_text",
        "description": (
            "Type text into an input element. "
            "Prefer passing a `ref` obtained from the `snapshot` tool (e.g. ref=\"e2\"). "
            "Fall back to a CSS or XPath `selector` only when no ref is available."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "Ref ID from the snapshot (e.g. \"e2\"). Takes priority over selector."
                },
                "selector": {
                    "type": "string",
                    "description": "CSS or XPath selector (fallback when ref is not available)."
                },
                "text": {"type": "string"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "scroll",
        "description": "Scroll the page down.",
        "input_schema": {
            "type": "object",
            "properties": {"direction": {"type": "string", "enum": ["down", "up"]}},
            "required": []
        }
    },
    {
        "name": "extract_info",
        "description": "Extract specific information from the current page content based on observation.",
        "input_schema": {
            "type": "object",
            "properties": {"info_summary": {"type": "string"}},
            "required": ["info_summary"]
        }
    },
    {
        "name": "request_human_assistance",
        "description": "Pause execution to ask the user to manually solve a login, CAPTCHA, or verification. Use this when you are blocked.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "Why you need human help"}},
            "required": ["reason"]
        }
    },
    {
        "name": "send_screenshot",
        "description": "Capture and send the current page screenshot to the user. ONLY use this when: (1) showing final results, (2) User ask you to show something. Do NOT use for routine navigation or intermediate steps. Be selective.",
        "input_schema": {
            "type": "object",
            "properties": {"description": {"type": "string", "description": "A brief description of what the screenshot shows"}},
            "required": ["description"]
        }
    },
    {
        "name": "finish_task",
        "description": "Call this tool when the final objective is fully accomplished. Pass the final report to the user.",
        "input_schema": {
            "type": "object",
            "properties": {"report": {"type": "string", "description": "Markdown formatted summary"}},
            "required": ["report"]
        }
    }
]

async def run_agent_loop(pm: PlaywrightManager, user_instruction: str, ws_send_msg, ws_request_action, ws_send_image, images: list = [], history_messages: list = []):
    await ws_send_msg({
        "message": f"Agent starting task: {user_instruction}",
        "message_key": "common.agent_starting",
        "params": {"task": user_instruction}
    })

    messages = history_messages.copy()  # Start with conversation history
    max_steps = 100
    is_finished = False
    
    # First user message: if user supplied images, present them first with an
    # explicit label so the model understands these are direct reference images
    # (not page screenshots) and should be examined before any tool use.
    if images:
        user_content = [{
            "type": "text",
            "text": (
                f"The user has attached {len(images)} image(s) directly to their request. "
                "Please examine each image carefully first, then complete the task below.\n\n"
                f"Task: {user_instruction}"
            )
        }]
        for data_url in images:
            try:
                header, b64_data = data_url.split(",", 1)
                media_type = header.split(":")[1].split(";")[0]  # e.g. image/png
                user_content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64_data}
                })
            except Exception as e:
                print(f"Failed to parse image data-URL: {e}")
        # Remind the model that the images above are user-provided
        user_content.append({
            "type": "text",
            "text": "The images above were provided by the user. Answer based on them directly if the task is about image content. Only browse the web if the task explicitly requires it."
        })
    else:
        user_content = [{"type": "text", "text": f"Please execute this task: {user_instruction}"}]

    
    for step in range(max_steps):
        # Check if a proactive takeover was requested before this step
        if pm.check_and_clear_pause_request():
            await ws_send_msg({
                "message": "Agent paused for manual takeover. Waiting for you to finish…",
                "message_key": "common.agent_paused_for_takeover"
            })
            await pm.human_intervention_event.wait()

        # 1. Observe (Append observation to the pending user_content)
        if pm.page:
            try:
                b64_img = await pm.get_page_screenshot_base64()
                url = pm.page.url
                title = await pm.page.title()
                user_content.append({"type": "text", "text": f"Current URL: {url}\\nTitle: {title}\\nWhat is your next action?"})
                if b64_img:
                    user_content.append({
                        "type": "image", 
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": b64_img}
                    })
            except Exception as e:
                user_content.append({"type": "text", "text": f"Observation failed: {e}. Try to continue."})
        
        # Add the constructed user message to history
        messages.append({"role": "user", "content": user_content})
        
        # 2. Think
        await ws_send_msg({
            "message": "Agent is thinking...",
            "message_key": "common.agent_thinking"
        })
        try:
            response = await client.messages.create(
                model=model_name,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=TOOLS
            )
        except Exception as e:
             await ws_send_msg(f"Error calling LLM: {str(e)}")
             break
             
        # Add Assistant Response to history
        messages.append({"role": "assistant", "content": response.content})
        
        # 3. Act
        tool_uses = [block for block in response.content if block.type == "tool_use"]
        
        # Prepare next user message content starting with tool results
        user_content = []
        
        if not tool_uses:
            text_blocks = [b.text for b in response.content if b.type == "text"]
            if text_blocks:
                msg = "\n".join(text_blocks)
                await ws_send_msg("🤔 " + msg)
                user_content.append({"type": "text", "text": "You didn't call any tools. Please use a tool to proceed."})
            continue
            
        for tool in tool_uses:
            tool_name = tool.name
            args = tool.input
            result_str = ""
            
            await ws_send_msg({
                "message": f"Executing action: `{tool_name}` with args: {json.dumps(args, ensure_ascii=False)}",
                "message_key": "common.executing_action",
                "params": {"tool": tool_name, "args": json.dumps(args, ensure_ascii=False)}
            })
            
            try:
                if tool_name == "snapshot":
                    snapshot_text = await pm.get_aria_snapshot()
                    if snapshot_text:
                        result_str = snapshot_text
                    else:
                        result_str = "Could not capture aria snapshot."

                elif tool_name == "navigate":
                    await pm.page.goto(args["url"])
                    await asyncio.sleep(2)
                    result_str = "Successfully navigated."
                    
                elif tool_name == "click":
                    ref = args.get("ref")
                    selector = args.get("selector")
                    if ref:
                        locator = await pm.locate_by_ref(ref)
                        await locator.click(timeout=5000)
                    elif selector:
                        await pm.page.click(selector, timeout=5000)
                    else:
                        raise ValueError("click requires either 'ref' or 'selector'")
                    await asyncio.sleep(1)
                    result_str = "Successfully clicked."
                    
                elif tool_name == "type_text":
                    ref = args.get("ref")
                    selector = args.get("selector")
                    if ref:
                        locator = await pm.locate_by_ref(ref)
                        await locator.fill(args["text"])
                    elif selector:
                        await pm.page.fill(selector, args["text"])
                    else:
                        raise ValueError("type_text requires either 'ref' or 'selector'")
                    result_str = "Successfully typed text."
                    
                elif tool_name == "scroll":
                    direction = args.get("direction", "down")
                    if direction == "down":
                        await pm.page.mouse.wheel(0, 1000)
                    else:
                        await pm.page.mouse.wheel(0, -1000)
                    await asyncio.sleep(1)
                    result_str = "Scrolled."
                    
                elif tool_name == "request_human_assistance":
                    reason = args.get("reason", "Login required.")
                    await pm.block_for_human(ws_request_action, reason)
                    result_str = "Human has processed the request. Page might have updated. You may resume your task."
                    
                elif tool_name == "extract_info":
                    result_str = f"Extracted: {args['info_summary']}"

                elif tool_name == "send_screenshot":
                    description = args.get("description", "Current page screenshot")
                    screenshot_b64 = await pm.get_page_screenshot_base64()
                    if screenshot_b64:
                        await ws_send_image(description, screenshot_b64)
                        result_str = f"Screenshot sent to user: {description}"
                    else:
                        result_str = "Failed to capture screenshot."

                elif tool_name == "finish_task":
                    report = args.get("report", "Task completed.")
                    await ws_send_msg({
                        "message": f"✅ **Task Completed**:\n\n{report}",
                        "message_key": "common.task_completed",
                        "params": {"report": report}
                    })
                    result_str = "Finished."
                    is_finished = True
                else:
                    result_str = f"Unknown tool: {tool_name}"
                    
            except Exception as e:
                result_str = f"Error executing {tool_name}: {str(e)}"
                
            user_content.append({
                "type": "tool_result",
                "tool_use_id": tool.id,
                "content": result_str
            })
            
        if is_finished:
            break

    if not is_finished:
        await ws_send_msg({
            "message": "⚠️ Task reached maximum steps without calling finish_task.",
            "message_key": "common.max_steps_error"
        })
