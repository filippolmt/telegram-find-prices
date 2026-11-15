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


async def test_watch_takes_the_product_link_given_with_the_command(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory)
    event = conversation_event(["shelly 2pm gen4", "/skip", "/skip"])

    await bot.bot_client.dispatch("/watch https://www.amazon.it/Shelly-2PM-Gen4/dp/B0F9LJFWPB/ref=sr_1_2?th=1", event)

    assert event.replies[0] == t("watch_asin_keywords", "en", asin="B0F9LJFWPB", keywords="shelly 2pm gen4")
    with db_session_factory() as session:
        product = session.query(Product).one()
        assert (product.name, product.asin) == ("shelly 2pm gen4", "B0F9LJFWPB")


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


@pytest.mark.parametrize("answer", ["annulla", TimeoutError(), "boh"])
async def test_watch_cancel_timeout_or_invalid_price_at_suggested_price_saves_nothing(monkeypatch, db_session_factory, answer):
    bot = registered_bot(monkeypatch, db_session_factory)
    _priced_elsewhere(db_session_factory, "iphone", 499.0)
    event = conversation_event(["iPhone", "/skip", "/skip", answer])

    await bot.bot_client.dispatch("/watch", event)

    with db_session_factory() as session:
        assert session.query(Product).filter_by(user_id=1).count() == 0


async def test_watch_invalid_suggested_price_answer_says_why(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory)
    _priced_elsewhere(db_session_factory, "iphone", 499.0)
    event = conversation_event(["iPhone", "/skip", "/skip", "boh"])

    await bot.bot_client.dispatch("/watch", event)

    assert event.replies[-1] == t("watch_invalid_price", "en")


@pytest.mark.parametrize("answer", ["no", "/skip"])
async def test_watch_declined_suggested_price_watches_at_any_price(monkeypatch, db_session_factory, answer):
    bot = registered_bot(monkeypatch, db_session_factory)
    _priced_elsewhere(db_session_factory, "iphone", 499.0)
    event = conversation_event(["iPhone", "/skip", "/skip", answer])

    await bot.bot_client.dispatch("/watch", event)

    assert event.replies[-1] == t("watch_active", "en", product="iPhone", price_info=" at any price", cat_info="")
    with db_session_factory() as session:
        assert session.query(Product).filter_by(user_id=1).one().target_price is None


async def test_watch_cancelled_with_the_command_saves_nothing(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory)
    event = conversation_event([])

    await bot.bot_client.dispatch("/watch annulla", event)

    assert event.replies == [t("operation_cancelled", "en")]
    with db_session_factory() as session:
        assert session.query(Product).count() == 0


async def test_watch_addressed_to_this_bot_by_username_takes_the_link(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory, bot_username="Find_Bot")
    event = conversation_event(["/skip", "/skip", "/skip"])

    await bot.bot_client.dispatch("/watch@find_bot https://www.amazon.it/dp/B0F9LJFWPB", event)

    with db_session_factory() as session:
        assert session.query(Product).one().asin == "B0F9LJFWPB"


def test_watch_addressed_to_another_bot_is_not_handled(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory, bot_username="find_bot")

    assert [h for b, h in bot.bot_client.handlers if b.pattern("/watch@other_bot x")] == []
