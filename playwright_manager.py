import asyncio
import base64
from typing import Optional, Callable, Awaitable
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

class PlaywrightManager:
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        # This event flags if the agent is blocked awaiting human interaction
        self.human_intervention_event: asyncio.Event = asyncio.Event()

    async def start(self):
        self.playwright = await async_playwright().start()
        # Use Chromium; running headless=False makes debugging easier, but we can turn it True in production
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.page = await self.context.new_page()

    async def stop(self):
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def get_page_screenshot_base64(self) -> str:
        if not self.page:
            return ""
        screenshot_bytes = await self.page.screenshot(type="jpeg", quality=60)
        return base64.b64encode(screenshot_bytes).decode("utf-8")

    async def check_if_login_required(self) -> bool:
        """
        Custom logic to detect simple login states. E.g. look for common login text or URL patterns.
        For Bilibili, it could be checking if "登录" (Login) button is prominent, or if we are redirected to passport.bilibili.com
        """
        if not self.page: return False
        try:
            url = self.page.url
            if "passport/login" in url or "login" in url:
                return True
            # Example element check: 
            # is_login_btn = await self.page.locator("text='登录'").count() > 0
            return False
        except Exception:
            return False

    async def block_for_human(self, callback: Callable[[str, str], Awaitable[None]], reason="Login Required"):
        """
        Captures screenshot, triggers the websocket callback to send to frontend,
        and pauses execution until resume() is called.
        """
        self.human_intervention_event.clear()
        
        screenshot_b64 = await self.get_page_screenshot_base64()
        
        # Call the websocket callback sending the screenshot to frontend
        await callback(reason, screenshot_b64)
        
        print(f"Agent blocked. Reason: {reason}. Waiting for human signal...")
        await self.human_intervention_event.wait()
        print("Human signal received. Agent resuming...")

    def resume_from_human(self):
        """
        Called when frontend sends "resume" signal
        """
        self.human_intervention_event.set()
