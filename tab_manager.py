"""
Multi-tab browser session management for NeoFish.

Each conversation session gets its own browser tab while sharing
a single BrowserContext (cookies, localStorage shared across sessions).
"""

import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional, Dict

from playwright.async_api import BrowserContext, Page

logger = logging.getLogger(__name__)

DEFAULT_MAX_TABS = 10
DEFAULT_TAB_TTL = 3600
CLEANUP_INTERVAL = 300


@dataclass
class TabSession:
    session_id: str
    page: Optional[Page]
    last_url: str = "about:blank"
    last_active: float = field(default_factory=time.time)
    is_active: bool = True

    def touch(self):
        self.last_active = time.time()

    def has_live_page(self) -> bool:
        return self.page is not None and not self.page.is_closed()

    def is_expired(self, ttl: int) -> bool:
        if self.is_active or not self.has_live_page():
            return False
        return (time.time() - self.last_active) > ttl


class TabManager:
    def __init__(
        self,
        context: BrowserContext,
        max_tabs: int = DEFAULT_MAX_TABS,
        tab_ttl: int = DEFAULT_TAB_TTL,
    ):
        self.context = context
        self.max_tabs = max_tabs
        self.tab_ttl = tab_ttl
        self._tabs: Dict[str, TabSession] = {}
        self._lru_order: OrderedDict[str, None] = OrderedDict()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        self._running = False
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        for session_id in list(self._tabs.keys()):
            await self._close_tab_internal(session_id, save_url=True)

    @property
    def active_count(self) -> int:
        return sum(1 for t in self._tabs.values() if t.is_active and t.has_live_page())

    @property
    def total_count(self) -> int:
        return sum(1 for t in self._tabs.values() if t.has_live_page())

    def has_tab(self, session_id: str) -> bool:
        return session_id in self._tabs

    def get_active_page(self, session_id: str) -> Optional[Page]:
        tab = self._tabs.get(session_id)
        if tab and tab.has_live_page():
            tab.touch()
            self._update_lru(session_id)
            return tab.page
        return None

    async def get_or_create_tab(self, session_id: str) -> Page:
        tab = self._tabs.get(session_id)

        if tab and tab.has_live_page():
            tab.is_active = True
            tab.touch()
            self._update_lru(session_id)
            return tab.page

        if self.total_count >= self.max_tabs:
            await self._evict_lru_tab()

        if tab:
            page = await self.context.new_page()
            tab.page = page
            tab.is_active = True
            tab.touch()
            self._update_lru(session_id)

            if tab.last_url and tab.last_url != "about:blank":
                try:
                    await page.goto(
                        tab.last_url, timeout=15000, wait_until="domcontentloaded"
                    )
                except Exception as e:
                    logger.warning("Failed to restore URL %s: %s", tab.last_url, e)

            return page

        page = await self.context.new_page()
        self._tabs[session_id] = TabSession(
            session_id=session_id,
            page=page,
            is_active=True,
        )
        self._update_lru(session_id)

        return page

    async def close_tab(
        self,
        session_id: str,
        save_url: bool = True,
        preserve_session: bool = True,
    ):
        await self._close_tab_internal(
            session_id, save_url=save_url, preserve_session=preserve_session
        )

    def deactivate_tab(self, session_id: str):
        tab = self._tabs.get(session_id)
        if tab:
            tab.is_active = False
            try:
                if tab.has_live_page():
                    tab.last_url = tab.page.url
            except Exception:
                pass
            tab.touch()

    def activate_tab(self, session_id: str):
        tab = self._tabs.get(session_id)
        if tab:
            tab.is_active = True
            tab.touch()
            self._update_lru(session_id)

    def save_tab_url(self, session_id: str):
        tab = self._tabs.get(session_id)
        if tab:
            try:
                if tab.has_live_page():
                    tab.last_url = tab.page.url
            except Exception:
                pass

    async def _close_tab_internal(
        self,
        session_id: str,
        save_url: bool = True,
        preserve_session: bool = True,
    ):
        tab = self._tabs.get(session_id)
        if not tab:
            return

        if save_url:
            try:
                if tab.has_live_page():
                    tab.last_url = tab.page.url
            except Exception:
                pass

        try:
            if tab.has_live_page():
                await tab.page.close()
        except Exception as e:
            logger.warning("Error closing page for %s: %s", session_id, e)

        self._lru_order.pop(session_id, None)

        if preserve_session:
            tab.page = None
            tab.is_active = False
            tab.touch()
            return

        del self._tabs[session_id]

    def _update_lru(self, session_id: str):
        self._lru_order.pop(session_id, None)
        self._lru_order[session_id] = None

    async def _evict_lru_tab(self):
        if not self._lru_order:
            return

        lru_session = None
        for session_id in self._lru_order:
            tab = self._tabs.get(session_id)
            if tab and tab.has_live_page() and not tab.is_active:
                lru_session = session_id
                break

        if not lru_session:
            for session_id in self._lru_order:
                tab = self._tabs.get(session_id)
                if tab and tab.has_live_page():
                    lru_session = session_id
                    break

        if lru_session:
            logger.info("Evicting LRU tab for session %s", lru_session)
            await self._close_tab_internal(
                lru_session, save_url=True, preserve_session=True
            )

    async def _cleanup_loop(self):
        while self._running:
            try:
                await asyncio.sleep(CLEANUP_INTERVAL)
                await self._cleanup_expired_tabs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("TabManager cleanup error: %s", e)

    async def _cleanup_expired_tabs(self):
        to_close = []
        for session_id, tab in self._tabs.items():
            if tab.is_expired(self.tab_ttl):
                to_close.append(session_id)

        for session_id in to_close:
            logger.info("TTL expired for session %s", session_id)
            await self._close_tab_internal(
                session_id, save_url=True, preserve_session=True
            )

    def get_stats(self) -> dict:
        return {
            "total_tabs": self.total_count,
            "active_tabs": self.active_count,
            "max_tabs": self.max_tabs,
            "tab_ttl": self.tab_ttl,
            "sessions": [
                {
                    "session_id": sid,
                    "has_open_page": tab.has_live_page(),
                    "is_active": tab.is_active,
                    "last_url": tab.last_url[:100] if tab.last_url else "",
                    "last_active_ago": int(time.time() - tab.last_active),
                }
                for sid, tab in self._tabs.items()
            ],
        }
