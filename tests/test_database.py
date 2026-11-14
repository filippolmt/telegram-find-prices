"""
Tests for database.run_migrations().
"""

from sqlalchemy import text

import database
from models import PriceHistory, Product, User, UserChannel


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
        # A product of a user that no longer exists, with its own match, and a dangling channel link.
        conn.execute(text("INSERT INTO products (id, user_id, name, added_at) VALUES (50, 999, 'ghost', '2026-01-01')"))
        conn.execute(text(
            "INSERT INTO price_history (product_id, user_id, channel, message_text, source, found_at) "
            "VALUES (50, 999, 'Ch', 'ghost match', 'realtime', '2026-01-01')"
        ))
        conn.execute(text("INSERT INTO channels (id, identifier, added_at) VALUES (1, 'deals', '2026-01-01')"))
        conn.execute(text("INSERT INTO user_channels (user_id, channel_id) VALUES (100, 999)"))
        conn.execute(text("INSERT INTO user_channels (user_id, channel_id) VALUES (999, 1)"))
        conn.commit()
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")

    monkeypatch.setattr(database, "engine", db_engine)
    database.run_migrations()

    with db_session_factory() as session:
        assert [(h.product_id, h.message_text) for h in session.query(PriceHistory)] == [(kept_product_id, "kept")]
        assert [p.name for p in session.query(Product)] == ["airpods"]
        assert session.query(UserChannel).count() == 0
