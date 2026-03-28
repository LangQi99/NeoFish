import re
import asyncio
import base64
import logging
from pathlib import Path
from typing import Optional, Callable, Awaitable
from playwright.async_api import async_playwright, BrowserContext, Page, Locator

logger = logging.getLogger(__name__)

from tab_manager import TabManager, DEFAULT_MAX_TABS, DEFAULT_TAB_TTL

BROWSER_STATE_DIR = Path("browser_state")

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_INTERACTIVE_ROLES = {
    "button",
    "link",
    "textbox",
    "checkbox",
    "radio",
    "combobox",
    "listbox",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "option",
    "searchbox",
    "switch",
    "tab",
    "treeitem",
    "slider",
    "spinbutton",
    "gridcell",
}


class PlaywrightManager:
    def __init__(
        self,
        max_tabs: int = DEFAULT_MAX_TABS,
        tab_ttl: int = DEFAULT_TAB_TTL,
    ):
        self.playwright = None
        self.context: Optional[BrowserContext] = None
        self.tab_manager: Optional[TabManager] = None
        self.max_tabs = max_tabs
        self.tab_ttl = tab_ttl

        self._current_session_id: Optional[str] = None
        self.human_intervention_event: asyncio.Event = asyncio.Event()

        self._in_takeover: bool = False
        self._takeover_session_id: Optional[str] = None
        self._takeover_event: Optional[asyncio.Event] = None
        self._takeover_final_url: str = "about:blank"
        self._pause_requested: dict[str, bool] = {}  # session_id -> pause requested
        self._pause_events: dict[str, asyncio.Event] = {}  # session_id -> event
        self._ref_map: dict[str, dict[str, tuple[str, str]]] = {}

        self._stream_running: bool = False
        self._stream_task: Optional[asyncio.Task] = None
        self._stream_callback: Optional[Callable] = None
        self.viewport_width: int = 1280
        self.viewport_height: int = 800

    @property
    def page(self) -> Optional[Page]:
        if self.tab_manager and self._current_session_id:
            return self.tab_manager.get_active_page(self._current_session_id)
        return None

    async def _launch_context(self, headless: bool) -> None:
        BROWSER_STATE_DIR.mkdir(exist_ok=True)
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_STATE_DIR),
            headless=headless,
            viewport={"width": 1280, "height": 800},
            user_agent=_DEFAULT_USER_AGENT,
        )
        self.tab_manager = TabManager(
            context=self.context,
            max_tabs=self.max_tabs,
            tab_ttl=self.tab_ttl,
        )
        await self.tab_manager.start()

    async def start(self):
        self.playwright = await async_playwright().start()
        await self._launch_context(headless=True)

    async def stop(self):
        if self.tab_manager:
            await self.tab_manager.stop()
            self.tab_manager = None
        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass
        if self.playwright:
            await self.playwright.stop()

    def set_current_session(self, session_id: str):
        self._current_session_id = session_id
        if self.tab_manager:
            self.tab_manager.activate_tab(session_id)

    async def get_or_create_page(self, session_id: str) -> Page:
        self.set_current_session(session_id)
        if self.tab_manager:
            return await self.tab_manager.get_or_create_tab(session_id)
        raise RuntimeError("TabManager not initialized")

    async def close_tab(self, session_id: str):
        if self.tab_manager:
            await self.tab_manager.close_tab(session_id)

    def deactivate_tab(self, session_id: str):
        if self.tab_manager:
            self.tab_manager.deactivate_tab(session_id)
        if self._current_session_id == session_id:
            self._current_session_id = None

    async def get_page_screenshot_base64(self, session_id: Optional[str] = None) -> str:
        page = self._get_page(session_id)
        if not page:
            return ""
        try:
            screenshot_bytes = await page.screenshot(type="jpeg", quality=60)
            return base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception:
            return ""

    async def get_aria_snapshot(self, session_id: Optional[str] = None) -> str:
        page = self._get_page(session_id)
        if not page:
            return ""
        try:
            raw_yaml = await page.locator("body").aria_snapshot()
        except Exception:
            return ""

        effective_session = session_id or self._current_session_id
        if not effective_session:
            return raw_yaml

        session_ref_map: dict[str, tuple[str, str]] = {}
        self._ref_map[effective_session] = session_ref_map
        counter = 0
        annotated_lines: list[str] = []

        for line in raw_yaml.splitlines():
            m = re.match(r'^(\s*- )(\w+)((?:\s+"[^"]*")?)(.*)?$', line)
            if m:
                indent_dash, role, quoted_name, rest = m.groups()
                if role in _INTERACTIVE_ROLES:
                    counter += 1
                    ref = f"e{counter}"
                    name = quoted_name.strip(' "') if quoted_name else ""
                    session_ref_map[ref] = (role, name)
                    annotated_lines.append(
                        f"{indent_dash}{role}{quoted_name} [ref={ref}]{rest}"
                    )
                    continue
            annotated_lines.append(line)

        return "\n".join(annotated_lines)

    async def locate_by_ref(
        self, ref: str, session_id: Optional[str] = None
    ) -> Locator:
        effective_session = session_id or self._current_session_id
        session_ref_map = self._ref_map.get(effective_session or "", {})

        if ref not in session_ref_map:
            raise ValueError(
                f"Unknown ref '{ref}'. Call the snapshot tool first, then use the "
                "ref IDs shown in the output."
            )
        page = self._get_page(session_id)
        if not page:
            raise RuntimeError("No active page")
        role, name = session_ref_map[ref]
        if name:
            return page.get_by_role(role, name=name)
        return page.get_by_role(role)

    async def check_if_login_required(self, session_id: Optional[str] = None) -> bool:
        page = self._get_page(session_id)
        if not page:
            return False
        try:
            url = page.url
            if "passport/login" in url or "login" in url:
                return True
            return False
        except Exception:
            return False

    def _get_page(self, session_id: Optional[str] = None) -> Optional[Page]:
        if self._in_takeover and self._takeover_session_id:
            effective_session = self._takeover_session_id
        else:
            effective_session = session_id or self._current_session_id

        if self.tab_manager and effective_session:
            return self.tab_manager.get_active_page(effective_session)
        return None

    async def block_for_human(
        self,
        callback: Callable[[str, str], Awaitable[None]],
        reason: str = "Login Required",
        session_id: Optional[str] = None,
    ):
        effective_session = session_id or self._current_session_id
        if effective_session and effective_session not in self._pause_events:
            self._pause_events[effective_session] = asyncio.Event()
        if effective_session:
            self._pause_events[effective_session].clear()

        screenshot_b64 = await self.get_page_screenshot_base64(session_id)
        await callback(reason, screenshot_b64)

        logger.info("Agent blocked. Reason: %s. Waiting for human signal…", reason)
        if effective_session:
            await self._pause_events[effective_session].wait()
        else:
            await self.human_intervention_event.wait()
        logger.info("Human signal received. Agent resuming…")

    def resume_from_human(self):
        self.human_intervention_event.set()

    def request_pause(self, session_id: str):
        self._pause_requested[session_id] = True
        if session_id not in self._pause_events:
            self._pause_events[session_id] = asyncio.Event()
        self._pause_events[session_id].clear()

    def check_and_clear_pause_request(self, session_id: str) -> bool:
        if self._pause_requested.get(session_id, False):
            self._pause_requested[session_id] = False
            return True
        return False

    async def wait_for_resume(self, session_id: str):
        if session_id in self._pause_events:
            await self._pause_events[session_id].wait()

    def signal_resume(self, session_id: str):
        if session_id in self._pause_events:
            self._pause_events[session_id].set()

    def is_waiting_for_human(self, session_id: str) -> bool:
        """Return True if the agent for *session_id* is blocked waiting for human intervention."""
        event = self._pause_events.get(session_id)
        return event is not None and not event.is_set()

    @property
    def in_takeover(self) -> bool:
        return self._in_takeover

    async def start_takeover(self, session_id: Optional[str] = None) -> str:
        effective_session = session_id or self._current_session_id
        if not effective_session:
            return "about:blank"

        if self._in_takeover:
            return self._takeover_final_url

        self._takeover_session_id = effective_session

        current_url: str = "about:blank"
        page = self._get_page(effective_session)
        try:
            if page and not page.is_closed():
                current_url = page.url
        except Exception:
            pass

        self._takeover_final_url = current_url

        if self.tab_manager:
            await self.tab_manager.close_tab(effective_session, save_url=True)
        try:
            if self.context:
                await self.context.close()
                self.context = None
        except Exception:
            pass

        self._in_takeover = True
        self._takeover_event = asyncio.Event()

        BROWSER_STATE_DIR.mkdir(exist_ok=True)
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_STATE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 800},
            user_agent=_DEFAULT_USER_AGENT,
        )

        self.tab_manager = TabManager(
            context=self.context,
            max_tabs=self.max_tabs,
            tab_ttl=self.tab_ttl,
        )
        await self.tab_manager.start()

        takeover_page = await self.tab_manager.get_or_create_tab(effective_session)

        if current_url and current_url != "about:blank":
            try:
                await takeover_page.goto(current_url, timeout=15000)
            except Exception as e:
                logger.warning("Takeover: could not navigate to %s: %s", current_url, e)

        captured_url: list[str] = [current_url]

        def _on_page_close():
            try:
                captured_url[0] = takeover_page.url
                self._takeover_final_url = captured_url[0]
            except Exception:
                pass

        def _on_context_close():
            if self._takeover_event and not self._takeover_event.is_set():
                self._takeover_event.set()

        takeover_page.on("close", lambda: _on_page_close())
        self.context.on("close", lambda: _on_context_close())

        return current_url

    async def wait_for_takeover_complete(self) -> tuple[str, str]:
        if not self._takeover_event:
            return self._takeover_final_url, ""

        await self._takeover_event.wait()

        final_url = self._takeover_final_url
        final_screenshot = ""
        page = self._get_page(self._takeover_session_id)
        try:
            if page and not page.is_closed():
                final_url = page.url
                final_screenshot = await self.get_page_screenshot_base64(
                    self._takeover_session_id
                )
                self._takeover_final_url = final_url
        except Exception:
            pass

        return final_url, final_screenshot

    def signal_takeover_done(self):
        if self._takeover_event and not self._takeover_event.is_set():
            self._takeover_event.set()

    async def end_takeover(self, final_url: str) -> str:
        session_id = self._takeover_session_id
        self._in_takeover = False
        self._takeover_event = None
        self._takeover_session_id = None

        if self.tab_manager:
            await self.tab_manager.stop()
            self.tab_manager = None
        try:
            if self.context:
                await self.context.close()
                self.context = None
        except Exception:
            pass

        await self._launch_context(headless=True)

        self.set_current_session(session_id)
        page = await self.get_or_create_page(session_id)

        if final_url and final_url != "about:blank":
            try:
                await page.goto(final_url, timeout=15000)
                await asyncio.sleep(1)
            except Exception as e:
                logger.warning("end_takeover: could not navigate to %s: %s", final_url, e)

        return final_url

    async def start_takeover_stream(
        self,
        frame_callback: Callable,
        stream_interval: float = 0.5,
        session_id: Optional[str] = None,
    ) -> None:
        self._takeover_session_id = session_id or self._current_session_id
        self._stream_callback = frame_callback
        self._stream_running = True
        self._stream_task = asyncio.create_task(self._stream_loop(stream_interval))

    async def _stream_loop(self, interval: float) -> None:
        while self._stream_running:
            try:
                page = self._get_page(self._takeover_session_id)
                if page and not page.is_closed():
                    screenshot = await self.get_page_screenshot_base64(
                        self._takeover_session_id
                    )
                    url = page.url
                    if screenshot and self._stream_callback:
                        await self._stream_callback(screenshot, url)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Takeover stream error: %s", e)
            await asyncio.sleep(interval)

    def stop_takeover_stream(self) -> None:
        self._stream_running = False
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
        self._stream_task = None
        self._stream_callback = None

    def begin_embedded_takeover(
        self, session_id: Optional[str] = None
    ) -> asyncio.Event:
        self._takeover_session_id = session_id or self._current_session_id
        self._in_takeover = True
        self._takeover_event = asyncio.Event()
        return self._takeover_event

    def end_embedded_takeover(self) -> None:
        self.stop_takeover_stream()
        self._in_takeover = False
        self._takeover_event = None
        self._takeover_session_id = None

    async def handle_takeover_click(
        self, x: float, y: float, button: str = "left"
    ) -> None:
        page = self._get_page(self._takeover_session_id)
        if page and not page.is_closed():
            await page.mouse.click(x, y, button=button)

    async def handle_takeover_double_click(self, x: float, y: float) -> None:
        page = self._get_page(self._takeover_session_id)
        if page and not page.is_closed():
            await page.mouse.dblclick(x, y)

    async def handle_takeover_mouse_move(self, x: float, y: float) -> None:
        page = self._get_page(self._takeover_session_id)
        if page and not page.is_closed():
            await page.mouse.move(x, y)

    async def handle_takeover_key(self, key: str) -> None:
        page = self._get_page(self._takeover_session_id)
        if page and not page.is_closed():
            await page.keyboard.press(key)

    async def handle_takeover_type(self, text: str) -> None:
        page = self._get_page(self._takeover_session_id)
        if page and not page.is_closed():
            await page.keyboard.type(text)

    async def handle_takeover_scroll(self, delta_x: float, delta_y: float) -> None:
        page = self._get_page(self._takeover_session_id)
        if page and not page.is_closed():
            await page.mouse.wheel(delta_x, delta_y)

    async def handle_takeover_navigate(self, url: str) -> None:
        page = self._get_page(self._takeover_session_id)
        if page and not page.is_closed():
            try:
                await page.goto(url, timeout=15000)
            except Exception as e:
                logger.warning("Takeover navigate error: %s", e)

    def get_tab_stats(self) -> dict:
        if self.tab_manager:
            return self.tab_manager.get_stats()
        return {"total_tabs": 0, "active_tabs": 0}
