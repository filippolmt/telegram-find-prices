"""
Database configuration and migrations.
"""

import logging
import sqlite3

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import Config as config

log = logging.getLogger(__name__)

DATABASE_URL = config.DATABASE_URL


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_conn, _record):
    """SQLite ignores foreign keys (and ON DELETE CASCADE) unless enabled per connection.

    Bound to the Engine class so every engine, test engines included, enforces them.
    """
    if isinstance(dbapi_conn, sqlite3.Connection):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")


_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)

Base = declarative_base()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def run_migrations():
    """Add missing columns and remove orphaned rows in existing tables (SQLite)."""
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
            if "asin" not in cols:
                conn.execute(text("ALTER TABLE products ADD COLUMN asin VARCHAR"))
                log.info("Migration: added column products.asin")

        # channels.title
        if "channels" in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns("channels")]
            if "title" not in cols:
                conn.execute(text("ALTER TABLE channels ADD COLUMN title VARCHAR"))
                log.info("Migration: added column channels.title")

        # user_channels.from_folder
        if "user_channels" in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns("user_channels")]
            if "from_folder" not in cols:
                conn.execute(text("ALTER TABLE user_channels ADD COLUMN from_folder BOOLEAN NOT NULL DEFAULT 0"))
                log.info("Migration: added column user_channels.from_folder")

        # Rows with dangling references, left before foreign keys were enforced.
        # One pass suffices: every foreign key cascades, so deleting a row cannot orphan another.
        # A future foreign key without CASCADE would make these deletes fail at startup instead.
        if engine.dialect.name == "sqlite":
            removed = 0
            # A row with two dangling references is listed twice; the second delete matches nothing.
            for table, rowid, _parent, _fkid in conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
                # table comes from SQLite's own schema, not from user input
                removed += conn.exec_driver_sql(f'DELETE FROM "{table}" WHERE rowid = ?', (rowid,)).rowcount
            if removed:
                log.info("Migration: removed %d orphaned rows (plus their cascaded rows)", removed)
