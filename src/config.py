"""
Bot configuration loaded from environment variables.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger(__name__)

# Session files and the DB grant account access: create every runtime file owner-only (600/700)
os.umask(0o077)

# Project directory (one level above src/)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Create data/ if it doesn't exist (for local execution without Docker)
DATA_DIR.mkdir(exist_ok=True)

# Load environment variables from .env at project root
load_dotenv(BASE_DIR / ".env")


def parse_allowed_users(raw: str) -> list[int]:
    """Parse comma-separated numeric Telegram user IDs, warning about invalid entries."""
    entries = [e.strip() for e in raw.split(",") if e.strip()]
    invalid = [e for e in entries if not e.isdigit()]
    if invalid:
        log.warning("ALLOWED_USERS: ignoring non-numeric entries %s (use numeric user IDs)", invalid)
    return [int(e) for e in entries if e.isdigit()]


class Config:
    """Bot configuration from environment variables."""
    API_HASH = os.getenv("API_HASH", "")
    API_ID = int(os.getenv("API_ID", "0"))
    BOT_SESSION_NAME = str(DATA_DIR / os.getenv("BOT_SESSION_NAME", "bot_session"))
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    CLIENT_SESSION_NAME = str(DATA_DIR / os.getenv("CLIENT_SESSION_NAME", "client_session"))
    CLIENT_SESSION_STRING = os.getenv("CLIENT_SESSION_STRING", "")
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'db.sqlite3'}")
    PHONE_NUMBER = os.getenv("PHONE_NUMBER", "")
    USERNAME = os.getenv("USERNAME", "")
    ALLOWED_USERS = parse_allowed_users(os.getenv("ALLOWED_USERS", ""))
    # Explicit opt-in to an open bot; an empty ALLOWED_USERS alone rejects everyone
    ALLOW_ALL_USERS = os.getenv("ALLOW_ALL_USERS", "").strip().lower() == "true"
    TIMEZONE = os.getenv("TIMEZONE", "UTC")
    DAILY_SUMMARY_HOUR = int(os.getenv("DAILY_SUMMARY_HOUR", "21"))
