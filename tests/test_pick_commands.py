"""
Tests for the commands that pick one item from a numbered list, through the registered command.
"""

from models import Channel, PriceHistory, Product, User, UserChannel
from tests.fakes import conversation_event, registered_bot
from translations import t


def _seed_products(db_session_factory, *names):
    with db_session_factory() as session:
        session.add(User(id=1, user_id=1, username="owner"))
        session.flush()
        products = [Product(user_id=1, name=n, target_price=10.0 if i == 0 else None) for i, n in enumerate(names)]
        session.add_all(products)
        session.commit()
        return [p.id for p in products]


async def test_unwatch_removes_chosen_product(monkeypatch, db_session_factory):
    _seed_products(db_session_factory, "iphone", "kindle")
    bot = registered_bot(monkeypatch, db_session_factory)
    event = conversation_event(["2"])

    await bot.bot_client.dispatch("/unwatch", event)

    assert event.replies == [
        t("unwatch_prompt", "en", items="1. iphone (≤10.00)\n2. kindle (any price)"),
        t("unwatched", "en", product="kindle"),
    ]
    with db_session_factory() as session:
        assert [p.name for p in session.query(Product)] == ["iphone"]


async def test_history_of_chosen_product(monkeypatch, db_session_factory):
    _, kindle_id = _seed_products(db_session_factory, "iphone", "kindle")
    with db_session_factory() as session:
        session.add(PriceHistory(product_id=kindle_id, user_id=1, price=89.0, channel="deals", message_text="m"))
        session.commit()
    bot = registered_bot(monkeypatch, db_session_factory)
    event = conversation_event(["2"])

    await bot.bot_client.dispatch("/history", event)

    assert event.replies[0] == t("history_prompt", "en", items="1. iphone\n2. kindle")
    assert event.replies[1].startswith(t("history_header", "en", product="kindle", count=1))
    assert "89.00 | deals" in event.replies[1]


async def test_remove_channel_unlinks_chosen_channel(monkeypatch, db_session_factory):
    with db_session_factory() as session:
        session.add(User(id=1, user_id=1, username="owner"))
        session.add_all([Channel(id=1, identifier="deals", title="Deals"), Channel(id=2, identifier="offers")])
        session.flush()
        session.add_all([UserChannel(user_id=1, channel_id=1), UserChannel(user_id=1, channel_id=2)])
        session.commit()
    bot = registered_bot(monkeypatch, db_session_factory)
    event = conversation_event(["1"])

    await bot.bot_client.dispatch("/remove_channel", event)

    assert event.replies == [
        t("remove_channel_prompt", "en", items="1. Deals (deals)\n2. offers"),
        t("remove_channel_removed", "en", channel="Deals (deals)"),
    ]
    with db_session_factory() as session:
        assert [uc.channel_id for uc in session.query(UserChannel)] == [2]


async def test_unwatch_list_labels_prices_in_user_language(monkeypatch, db_session_factory):
    _seed_products(db_session_factory, "iphone", "kindle")
    bot = registered_bot(monkeypatch, db_session_factory)
    event = conversation_event(["annulla"], lang="it")

    await bot.bot_client.dispatch("/unwatch", event)

    assert event.replies[0] == t("unwatch_prompt", "it", items="1. iphone (≤10.00)\n2. kindle (qualsiasi prezzo)")
