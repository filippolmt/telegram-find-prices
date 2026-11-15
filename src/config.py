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


def tighten_permissions(data_dir: Path) -> None:
    """Set data_dir to 700 and its direct regular files to 600: umask misses files that already exist."""
    # Runtipi chmods app-data 777; symlinks and subdirectories are not followed
    targets = [(data_dir, 0o700)] + [
        (p, 0o600) for p in data_dir.iterdir() if p.is_file() and not p.is_symlink()
    ]
    for path, mode in targets:
        try:
            current = path.stat().st_mode & 0o777
            if current != mode:
                path.chmod(mode)
                log.warning("Tightened %s from %o to %o", path, current, mode)
        except PermissionError:
            log.warning("Cannot chmod %s: permission denied", path)


tighten_permissions(DATA_DIR)

# Load environment variables from .env at project root
load_dotenv(BASE_DIR / ".env")


def parse_allowed_users(raw: str) -> list[int]:
    """Parse comma-separated numeric Telegram user IDs, warning about invalid entries."""
    entries = [e.strip() for e in raw.split(",") if e.strip()]
    invalid = [e for e in entries if not e.isdigit()]
    if invalid:
        log.warning("ALLOWED_USERS: ignoring non-numeric entries %s (use numeric user IDs)", invalid)
    return [int(e) for e in entries if e.isdigit()]


def is_authorized(user_id: int | None, allowed_users: list[int], allow_all: bool) -> bool:
    """Fail closed: an empty ALLOWED_USERS rejects everyone unless ALLOW_ALL_USERS is explicitly enabled."""
    if user_id is None:
        return False
    if allowed_users:
        return user_id in allowed_users
    return allow_all


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
    # Name of the user client account's folder whose channels are monitored for that account; empty: off
    CHANNEL_FOLDER = os.getenv("CHANNEL_FOLDER", "").strip()
