"""
Tests for the /watch conversation, through the registered command and an in-memory conversation.
"""

import pytest

from models import PriceHistory, Product, User
from tests.fakes import conversation_event, registered_bot
from translations import t


@pytest.mark.parametrize("answer", ["", "  ", "-", "."])
async def test_watch_rejects_product_name_without_keywords(monkeypatch, db_session_factory, answer):
    bot = registered_bot(monkeypatch, db_session_factory)
    event = conversation_event([answer])

    await bot.bot_client.dispatch("/watch", event)

    assert event.replies == [t("watch_ask_product", "en"), t("watch_name_no_keywords", "en")]
    with db_session_factory() as session:
        assert session.query(Product).count() == 0


async def test_watch_link_with_keywords_without_letters_matches_by_link_only(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory)
    event = conversation_event(["https://www.amazon.it/dp/B0TEST1234", "-", "/skip", "/skip"])

    await bot.bot_client.dispatch("/watch", event)

    with db_session_factory() as session:
        product = session.query(Product).one()
        assert (product.name, product.asin) == ("b0test1234", "B0TEST1234")


def _priced_elsewhere(db_session_factory, name, price):
    with db_session_factory() as session:
        session.add(User(id=2, user_id=2, username="other"))
        session.flush()
        product = Product(user_id=2, name=name)
        session.add(product)
        session.flush()
        session.add(PriceHistory(product_id=product.id, user_id=2, price=price, channel="c", message_text="m"))
        session.commit()


async def test_watch_accepts_suggested_price_from_history(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory)
    _priced_elsewhere(db_session_factory, "iphone", 499.0)
    event = conversation_event(["iPhone", "/skip", "/skip", "sì"])

    await bot.bot_client.dispatch("/watch", event)

    with db_session_factory() as session:
        product = session.query(Product).filter_by(user_id=1).one()
        assert product.target_price == 499.0
    assert event.conversations == 1


@pytest.mark.parametrize("answer", ["annulla", TimeoutError()])
async def test_watch_cancel_or_timeout_at_suggested_price_saves_nothing(monkeypatch, db_session_factory, answer):
    bot = registered_bot(monkeypatch, db_session_factory)
    _priced_elsewhere(db_session_factory, "iphone", 499.0)
    event = conversation_event(["iPhone", "/skip", "/skip", answer])

    await bot.bot_client.dispatch("/watch", event)

    with db_session_factory() as session:
        assert session.query(Product).filter_by(user_id=1).count() == 0
