"""
Database configuration and migrations.
"""

import logging
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import create_engine, inspect, text
from config import Config as config

log = logging.getLogger(__name__)

DATABASE_URL = config.DATABASE_URL

_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)

Base = declarative_base()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def run_migrations():
    """Add missing columns to existing tables (SQLite)."""
    inspector = inspect(engine)
    with engine.begin() as conn:
        # users.paused
        if "users" in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns("users")]
            if "paused" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN paused BOOLEAN NOT NULL DEFAULT 0"))
                log.info("Migration: added column users.paused")

        # users.lang_code
        if "users" in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns("users")]
            if "lang_code" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN lang_code VARCHAR NOT NULL DEFAULT 'en'"))
                log.info("Migration: added column users.lang_code")

        # products.category
        if "products" in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns("products")]
            if "category" not in cols:
                conn.execute(text("ALTER TABLE products ADD COLUMN category VARCHAR"))
                log.info("Migration: added column products.category")

        # channels.title
        if "channels" in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns("channels")]
            if "title" not in cols:
                conn.execute(text("ALTER TABLE channels ADD COLUMN title VARCHAR"))
                log.info("Migration: added column channels.title")
