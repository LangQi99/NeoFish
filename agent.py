import os
import json
import asyncio
from anthropic import AsyncAnthropic
from playwright_manager import PlaywrightManager

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
model_name = os.getenv("MODEL_NAME", "claude-3-7-sonnet-20250219")

SYSTEM_PROMPT = """You are NeoFish, an autonomous web browser agent.
Your core task is to complete the user's instructions on the web.
You have the ability to observe the current page via screenshots and act using tools.
If you ever encounter a strict login wall, CAPTCHA, or require the user to scan a QR code, you must call the `request_human_assistance` tool. Do NOT give up easily; only ask for help when absolutely necessary.
When the task is completely finished, call `finish_task`.
"""

TOOLS = [
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
        "description": "Click an element on the page using a CSS or XPath selector.",
        "input_schema": {
            "type": "object",
            "properties": {"selector": {"type": "string"}},
            "required": ["selector"]
        }
    },
    {
        "name": "type_text",
        "description": "Type text into an element.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "text": {"type": "string"}
            },
            "required": ["selector", "text"]
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
        "name": "finish_task",
        "description": "Call this tool when the final objective is fully accomplished. Pass the final report to the user.",
        "input_schema": {
            "type": "object",
            "properties": {"report": {"type": "string", "description": "Markdown formatted summary"}},
            "required": ["report"]
        }
    }
]

async def run_agent_loop(pm: PlaywrightManager, user_instruction: str, ws_send_msg, ws_request_action):
    await ws_send_msg(f"Agent starting task: {user_instruction}")
    
    messages = []
    max_steps = 15
    is_finished = False
    
    # First user message includes instruction and initial observation
    user_content = [{"type": "text", "text": f"Please execute this task: {user_instruction}"}]
    
    for step in range(max_steps):
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
        await ws_send_msg("Agent is thinking...")
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
            
            await ws_send_msg(f"Executing action: `{tool_name}` with args: {json.dumps(args, ensure_ascii=False)}")
            
            try:
                if tool_name == "navigate":
                    await pm.page.goto(args["url"])
                    await asyncio.sleep(2)
                    result_str = "Successfully navigated."
                    
                elif tool_name == "click":
                    await pm.page.click(args["selector"], timeout=5000)
                    await asyncio.sleep(1)
                    result_str = "Successfully clicked."
                    
                elif tool_name == "type_text":
                    await pm.page.fill(args["selector"], args["text"])
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
                    
                elif tool_name == "finish_task":
                    report = args.get("report", "Task completed.")
                    await ws_send_msg(f"✅ **Task Completed**:\n\n{report}")
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
        await ws_send_msg("⚠️ Task reached maximum steps without calling finish_task.")
