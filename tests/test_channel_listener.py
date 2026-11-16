"""
Tests for ChannelListener's realtime handler.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from telethon.tl.custom.message import Message
from telethon.tl.types import PeerChannel

from channel_listener import ChannelListener
from config import Config
from models import Channel, PriceHistory, Product, User


def _registered_handler(db_session_factory, bot_client):
    handlers = []
    client = MagicMock()
    client.on = lambda _event: lambda fn: handlers.append(fn) or fn
    ChannelListener(client, bot_client, db_session_factory).register()
    return handlers[0]


async def test_realtime_skips_product_unwatched_while_notifying(db_session_factory):
    with db_session_factory() as session:
        session.add_all([User(user_id=100), Channel(identifier="deals")])
        session.flush()
        iphone = Product(user_id=100, name="iPhone 15", target_price=600)
        session.add_all([iphone, Product(user_id=100, name="AirPods")])
        session.commit()
        iphone_id = iphone.id

    async def unwatch_airpods(*_args, **_kwargs):
        # The user unwatches AirPods while the iPhone 15 notification is being sent.
        with db_session_factory() as session:
            session.query(Product).filter_by(name="AirPods").delete()
            session.commit()

    bot_client = MagicMock()
    bot_client.send_message = AsyncMock(side_effect=unwatch_airpods)
    handler = _registered_handler(db_session_factory, bot_client)

    event = SimpleNamespace(
        message=Message(id=7, peer_id=PeerChannel(123), message="iPhone 15 a 499€ e AirPods a 99€"),
        id=7,
        get_chat=AsyncMock(return_value=SimpleNamespace(title="Deals", username="deals", id=123)),
    )
    await handler(event)

    with db_session_factory() as session:
        assert [h.product_id for h in session.query(PriceHistory)] == [iphone_id]
    bot_client.send_message.assert_awaited_once()


async def test_realtime_records_match_of_paused_user_without_notifying(db_session_factory):
    with db_session_factory() as session:
        session.add_all([User(user_id=100, paused=True), Channel(identifier="deals")])
        session.flush()
        session.add(Product(user_id=100, name="iPhone 15", target_price=600))
        session.commit()

    bot_client = MagicMock()
    bot_client.send_message = AsyncMock()
    handler = _registered_handler(db_session_factory, bot_client)

    event = SimpleNamespace(
        message=Message(id=7, peer_id=PeerChannel(123), message="iPhone 15 a 499€"),
        id=7,
        get_chat=AsyncMock(return_value=SimpleNamespace(title="Deals", username="deals", id=123)),
    )
    await handler(event)

    with db_session_factory() as session:
        assert [(h.source, h.price) for h in session.query(PriceHistory)] == [("realtime", 499)]
    bot_client.send_message.assert_not_awaited()


async def test_realtime_matches_channel_added_with_other_case(db_session_factory):
    # Rows stored before join_channel() kept Telegram's spelling hold the username as the user typed it
    with db_session_factory() as session:
        session.add_all([User(user_id=100), Channel(identifier="Deals")])
        session.flush()
        session.add(Product(user_id=100, name="iPhone 15"))
        session.commit()

    handler = _registered_handler(db_session_factory, MagicMock(send_message=AsyncMock()))
    await handler(SimpleNamespace(
        message=Message(id=7, peer_id=PeerChannel(123), message="iPhone 15 a 499€"),
        id=7,
        get_chat=AsyncMock(return_value=SimpleNamespace(title="Deals", username="deals", id=123)),
    ))

    with db_session_factory() as session:
        assert session.query(PriceHistory).count() == 1


async def test_realtime_matches_products_of_every_authorized_user(monkeypatch, db_session_factory):
    monkeypatch.setattr(Config, "ALLOWED_USERS", [100, 200])
    with db_session_factory() as session:
        session.add_all([User(user_id=100), User(user_id=200), User(user_id=300), Channel(identifier="deals")])
        session.flush()
        session.add_all([Product(user_id=uid, name="iPhone 15") for uid in (100, 200, 300)])
        session.commit()

    handler = _registered_handler(db_session_factory, MagicMock(send_message=AsyncMock()))
    await handler(SimpleNamespace(
        message=Message(id=7, peer_id=PeerChannel(123), message="iPhone 15 a 499€"),
        id=7,
        get_chat=AsyncMock(return_value=SimpleNamespace(title="Deals", username="deals", id=123)),
    ))

    with db_session_factory() as session:
        # 300 is no longer in ALLOWED_USERS: never matched
        assert sorted(h.user_id for h in session.query(PriceHistory)) == [100, 200]


async def test_realtime_ignores_channel_not_monitored(db_session_factory):
    with db_session_factory() as session:
        session.add_all([User(user_id=100), Channel(identifier="deals")])
        session.flush()
        session.add(Product(user_id=100, name="iPhone 15"))
        session.commit()

    handler = _registered_handler(db_session_factory, MagicMock(send_message=AsyncMock()))
    await handler(SimpleNamespace(
        message=Message(id=7, peer_id=PeerChannel(456), message="iPhone 15 a 499€"),
        id=7,
        get_chat=AsyncMock(return_value=SimpleNamespace(title="Owner's friends", username="friends", id=456)),
    ))

    with db_session_factory() as session:
        assert session.query(PriceHistory).count() == 0
