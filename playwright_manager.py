import asyncio
import base64
from pathlib import Path
from typing import Optional, Callable, Awaitable
from playwright.async_api import async_playwright, BrowserContext, Page

# Directory to store browser state (cookies, localStorage, etc.)
BROWSER_STATE_DIR = Path("browser_state")

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class PlaywrightManager:
    def __init__(self):
        self.playwright = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        # This event flags if the agent is blocked awaiting human interaction
        self.human_intervention_event: asyncio.Event = asyncio.Event()
        # Takeover state
        self._in_takeover: bool = False
        self._takeover_event: Optional[asyncio.Event] = None
        self._takeover_final_url: str = "about:blank"
        # Flag set by a proactive takeover request so the agent loop pauses
        self._pause_requested: bool = False

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _launch_context(self, headless: bool) -> None:
        """Launch (or relaunch) the Chromium persistent context."""
        BROWSER_STATE_DIR.mkdir(exist_ok=True)
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_STATE_DIR),
            headless=headless,
            viewport={"width": 1280, "height": 800},
            user_agent=_DEFAULT_USER_AGENT,
        )
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = await self.context.new_page()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def start(self):
        self.playwright = await async_playwright().start()
        await self._launch_context(headless=True)

    async def stop(self):
        try:
            if self.page:
                await self.page.close()
        except Exception:
            pass
        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass
        if self.playwright:
            await self.playwright.stop()

    # ── Utilities ──────────────────────────────────────────────────────────────

    async def get_page_screenshot_base64(self) -> str:
        if not self.page:
            return ""
        try:
            screenshot_bytes = await self.page.screenshot(type="jpeg", quality=60)
            return base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception:
            return ""

    async def check_if_login_required(self) -> bool:
        """
        Custom logic to detect simple login states. E.g. look for common login text or URL patterns.
        For Bilibili, it could be checking if "登录" (Login) button is prominent, or if we are redirected to passport.bilibili.com
        """
        if not self.page:
            return False
        try:
            url = self.page.url
            if "passport/login" in url or "login" in url:
                return True
            return False
        except Exception:
            return False

    # ── Human-in-the-loop (agent-initiated) ───────────────────────────────────

    async def block_for_human(
        self, callback: Callable[[str, str], Awaitable[None]], reason: str = "Login Required"
    ):
        """
        Captures a screenshot, triggers the WebSocket callback to send it to the
        frontend, and pauses execution until resume_from_human() is called
        (either via the plain 'Resume' button or after a takeover completes).
        """
        self.human_intervention_event.clear()

        screenshot_b64 = await self.get_page_screenshot_base64()
        await callback(reason, screenshot_b64)

        print(f"Agent blocked. Reason: {reason}. Waiting for human signal…")
        await self.human_intervention_event.wait()
        print("Human signal received. Agent resuming…")

    def resume_from_human(self):
        """Called when the frontend sends a 'resume' or takeover-complete signal."""
        self.human_intervention_event.set()

    # ── Proactive-pause flag (for the always-visible Takeover button) ──────────

    def request_pause(self):
        """
        Ask the agent loop to pause at the beginning of its next step.
        The loop will block on human_intervention_event until resume_from_human()
        is called (which happens automatically when a takeover completes).
        """
        # Clear the event first so the loop will block when it checks
        self.human_intervention_event.clear()
        self._pause_requested = True

    def check_and_clear_pause_request(self) -> bool:
        """
        Return True (and clear the flag) if a proactive pause was requested.
        Called once per agent-loop step before the observe phase.
        """
        if self._pause_requested:
            self._pause_requested = False
            return True
        return False

    # ── Takeover flow ──────────────────────────────────────────────────────────

    @property
    def in_takeover(self) -> bool:
        return self._in_takeover

    async def start_takeover(self) -> str:
        """
        Close the headless browser and launch a headed (visible) browser at the
        same URL so the user can interact directly.

        Returns the URL that was open when the takeover started.
        """
        if self._in_takeover:
            return self._takeover_final_url

        # Remember where the agent was
        current_url: str = "about:blank"
        try:
            if self.page and not self.page.is_closed():
                current_url = self.page.url
        except Exception:
            pass

        self._takeover_final_url = current_url

        # Close the headless context
        try:
            if self.page:
                await self.page.close()
                self.page = None
        except Exception:
            pass
        try:
            if self.context:
                await self.context.close()
                self.context = None
        except Exception:
            pass

        self._in_takeover = True
        self._takeover_event = asyncio.Event()

        # Launch headed context
        await self._launch_context(headless=False)

        # Navigate to the same page
        if current_url and current_url != "about:blank":
            try:
                await self.page.goto(current_url, timeout=15000)
            except Exception as e:
                print(f"Takeover: could not navigate to {current_url}: {e}")

        # Wire up close detection so we unblock wait_for_takeover_complete()
        # even when the user closes the browser window manually.
        # Capture URL in a local variable now so the callbacks don't need to
        # access self.page after it may have been closed.
        captured_url: list[str] = [current_url]

        def _on_page_close():
            try:
                # page.url is still readable during the close event
                captured_url[0] = self.page.url
                self._takeover_final_url = captured_url[0]
            except Exception:
                pass

        def _on_context_close():
            if self._takeover_event and not self._takeover_event.is_set():
                self._takeover_event.set()

        self.page.on("close", lambda: _on_page_close())
        self.context.on("close", lambda: _on_context_close())

        return current_url

    async def wait_for_takeover_complete(self) -> tuple[str, str]:
        """
        Block until the user closes the headed browser or signal_takeover_done()
        is called.  Returns (final_url, final_screenshot_b64).
        """
        if not self._takeover_event:
            return self._takeover_final_url, ""

        await self._takeover_event.wait()

        # Try to grab a last screenshot before anything is fully torn down
        final_url = self._takeover_final_url
        final_screenshot = ""
        try:
            if self.page and not self.page.is_closed():
                final_url = self.page.url
                final_screenshot = await self.get_page_screenshot_base64()
                self._takeover_final_url = final_url
        except Exception:
            pass

        return final_url, final_screenshot

    def signal_takeover_done(self):
        """
        Called when the frontend sends a 'takeover_done' signal — the user
        pressed "Done" in the UI without closing the browser window.
        """
        if self._takeover_event and not self._takeover_event.is_set():
            self._takeover_event.set()

    async def end_takeover(self, final_url: str) -> str:
        """
        Close the headed browser (if still open) and relaunch headless.
        Navigates back to *final_url* so the agent can continue from where
        the user left off.  Returns the final URL.
        """
        self._in_takeover = False
        self._takeover_event = None

        # Close headed context
        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
                self.page = None
        except Exception:
            pass
        try:
            if self.context:
                await self.context.close()
                self.context = None
        except Exception:
            pass

        # Relaunch headless
        await self._launch_context(headless=True)

        if final_url and final_url != "about:blank":
            try:
                await self.page.goto(final_url, timeout=15000)
                await asyncio.sleep(1)
            except Exception as e:
                print(f"end_takeover: could not navigate to {final_url}: {e}")

        return final_url
