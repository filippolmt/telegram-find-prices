"""
Tests for database.run_migrations().
"""

import pytest
from sqlalchemy import inspect, text

import database
from database import Base
from models import PriceHistory, Product, User


def test_migration_removes_rows_with_dangling_references(db_engine, db_session_factory, monkeypatch):
    with db_session_factory() as session:
        session.add(User(user_id=100))
        session.flush()
        product = Product(user_id=100, name="airpods")
        session.add(product)
        session.flush()
        session.add(PriceHistory(product_id=product.id, user_id=100, channel="Ch", message_text="kept"))
        session.commit()
        kept_product_id = product.id

    # Orphans written before foreign keys were enforced.
    with db_engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        conn.execute(text(
            "INSERT INTO price_history (product_id, user_id, channel, message_text, source, found_at) "
            "VALUES (999, 100, 'Ch', 'orphan', 'realtime', '2026-01-01')"
        ))
        # A product of a user that no longer exists, with its own match.
        conn.execute(text("INSERT INTO products (id, user_id, name, added_at) VALUES (50, 999, 'ghost', '2026-01-01')"))
        conn.execute(text(
            "INSERT INTO price_history (product_id, user_id, channel, message_text, source, found_at) "
            "VALUES (50, 999, 'Ch', 'ghost match', 'realtime', '2026-01-01')"
        ))
        conn.commit()
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")

    monkeypatch.setattr(database, "engine", db_engine)
    database.run_migrations()

    with db_session_factory() as session:
        assert [(h.product_id, h.message_text) for h in session.query(PriceHistory)] == [(kept_product_id, "kept")]
        assert [p.name for p in session.query(Product)] == ["airpods"]


def test_every_foreign_key_cascades():
    # run_migrations() deletes orphaned parents in one pass; a key without CASCADE would fail that at startup.
    assert [str(fk.parent) for table in Base.metadata.tables.values() for fk in table.foreign_keys
            if fk.ondelete != "CASCADE"] == []


def test_migration_adds_products_asin(fresh_engine):
    with fresh_engine.begin() as conn:
        conn.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY, user_id INTEGER, name VARCHAR, category VARCHAR)"))

    database.run_migrations()

    assert "asin" in [c["name"] for c in inspect(fresh_engine).get_columns("products")]


@pytest.fixture
def old_user_links(fresh_engine):
    """A DB from before shared channels: the owner (100) linked 'deals', another user (200) 'friends_pick'."""
    with fresh_engine.begin() as conn:
        conn.execute(text("CREATE TABLE channels (id INTEGER PRIMARY KEY, identifier VARCHAR, title VARCHAR, added_at VARCHAR)"))
        conn.execute(text("CREATE TABLE user_channels (user_id INTEGER, channel_id INTEGER, from_folder BOOLEAN)"))
        conn.execute(text("INSERT INTO channels VALUES (1, 'deals', NULL, '2026-01-01'), (2, 'friends_pick', NULL, '2026-01-01')"))
        conn.execute(text("INSERT INTO user_channels VALUES (100, 1, 0), (200, 2, 0)"))
    return fresh_engine


def _state(engine):
    with engine.connect() as conn:
        channels = [r.identifier for r in conn.execute(text("SELECT identifier FROM channels ORDER BY id"))]
    return channels, "user_channels" in inspect(engine).get_table_names()


def test_shared_channels_migration_keeps_only_the_owners_channels(old_user_links):
    database.migrate_to_shared_channels(owner_id=100)

    assert _state(old_user_links) == (["deals"], False)


def test_shared_channels_migration_waits_while_nobody_is_owner(old_user_links):
    database.migrate_to_shared_channels(owner_id=None)

    assert _state(old_user_links) == (["deals", "friends_pick"], True)
