"""
config.py - Centralised configuration for NeoFish.

All platform tokens and shared settings are loaded from environment variables
(or a .env file) in one place.  Import individual values from here instead of
calling os.getenv() scattered throughout the codebase.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Core / LLM ────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL: str = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
MODEL_NAME: str = os.getenv("MODEL_NAME", "claude-3-7-sonnet-20250219")
TOKEN_THRESHOLD: int = int(os.getenv("TOKEN_THRESHOLD", "800000"))
MAX_TOKEN: int = int(os.getenv("MAX_TOKEN", "1000000"))

# ── Storage ───────────────────────────────────────────────────────────────────

WORKDIR: Path = Path(os.getenv("WORKDIR", "./workspace")).resolve()
TRANSCRIPT_DIR: Path = Path(os.getenv("TRANSCRIPT_DIR", "./.transcripts")).resolve()
TASKS_DIR: Path = Path(os.getenv("TASKS_DIR", "./.tasks")).resolve()
BG_TASK_TIMEOUT: int = int(os.getenv("BG_TASK_TIMEOUT", "300"))

# ── Web platform ──────────────────────────────────────────────────────────────

WEB_HOST: str = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT: int = int(os.getenv("WEB_PORT", "8000"))

# ── Telegram platform ─────────────────────────────────────────────────────────

# Obtain a token from @BotFather on Telegram.
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Comma-separated list of allowed Telegram user IDs (empty = allow everyone).
# Example: TELEGRAM_ALLOWED_USERS=123456789,987654321
_telegram_allowed_raw: str = os.getenv("TELEGRAM_ALLOWED_USERS", "")
TELEGRAM_ALLOWED_USERS: list[str] = (
    [u.strip() for u in _telegram_allowed_raw.split(",") if u.strip()]
    if _telegram_allowed_raw
    else []
)

# ── QQ platform ───────────────────────────────────────────────────────────────

# Base URL for the NapCat / go-cqhttp HTTP API.
# Example: QQ_API_URL=http://127.0.0.1:3000
QQ_API_URL: str = os.getenv("QQ_API_URL", "http://127.0.0.1:3000")

# Access token for NapCat / go-cqhttp (leave empty if not configured).
QQ_ACCESS_TOKEN: str = os.getenv("QQ_ACCESS_TOKEN", "")

# WebSocket URL that NapCat / go-cqhttp pushes events to.
# Example: QQ_WS_URL=ws://127.0.0.1:3001
QQ_WS_URL: str = os.getenv("QQ_WS_URL", "ws://127.0.0.1:3001")

# Comma-separated list of allowed QQ user / group IDs (empty = allow everyone).
_qq_allowed_raw: str = os.getenv("QQ_ALLOWED_IDS", "")
QQ_ALLOWED_IDS: list[str] = (
    [u.strip() for u in _qq_allowed_raw.split(",") if u.strip()]
    if _qq_allowed_raw
    else []
)
