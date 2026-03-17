"""
platforms/ - Platform adapter package for NeoFish.

Each sub-module implements PlatformAdapter for a specific messaging platform:

    web.py       — FastAPI / WebSocket (browser frontend)
    telegram.py  — Telegram Bot API (via python-telegram-bot)
    qq.py        — QQ via NapCat / go-cqhttp WebSocket API

Import the concrete adapter classes directly:

    from platforms.web import WebAdapter
    from platforms.telegram import TelegramAdapter
    from platforms.qq import QQAdapter
"""

from platforms.base import PlatformAdapter
from platforms.web import WebAdapter
from platforms.telegram import TelegramAdapter
from platforms.qq import QQAdapter

__all__ = [
    "PlatformAdapter",
    "WebAdapter",
    "TelegramAdapter",
    "QQAdapter",
]
