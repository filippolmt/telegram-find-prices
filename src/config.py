"""
Bot configuration loaded from environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Project directory (one level above src/)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Create data/ if it doesn't exist (for local execution without Docker)
DATA_DIR.mkdir(exist_ok=True)

# Load environment variables from .env at project root
load_dotenv(BASE_DIR / ".env")


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
    ALLOWED_USERS = [
        int(uid.strip())
        for uid in os.getenv("ALLOWED_USERS", "").split(",")
        if uid.strip().isdigit()
    ]
    TIMEZONE = os.getenv("TIMEZONE", "UTC")
    DAILY_SUMMARY_HOUR = int(os.getenv("DAILY_SUMMARY_HOUR", "21"))
