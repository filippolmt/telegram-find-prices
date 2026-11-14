"""
Tests for ChannelListener's realtime handler.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from channel_listener import ChannelListener
from models import Channel, PriceHistory, Product, User, UserChannel


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
        session.add(UserChannel(user_id=100, channel_id=session.query(Channel).one().id))
        iphone = Product(user_id=100, name="iPhone 15", target_price=600)
        session.add_all([iphone, Product(user_id=100, name="AirPods")])
        session.commit()
        iphone_id = iphone.id

    async def unwatch_airpods(*_args):
        # The user unwatches AirPods while the iPhone 15 notification is being sent.
        with db_session_factory() as session:
            session.query(Product).filter_by(name="AirPods").delete()
            session.commit()

    bot_client = MagicMock()
    bot_client.send_message = AsyncMock(side_effect=unwatch_airpods)
    handler = _registered_handler(db_session_factory, bot_client)

    event = SimpleNamespace(
        raw_text="iPhone 15 a 499€ e AirPods a 99€",
        id=7,
        get_chat=AsyncMock(return_value=SimpleNamespace(title="Deals", username="deals", id=123)),
    )
    await handler(event)

    with db_session_factory() as session:
        assert [h.product_id for h in session.query(PriceHistory)] == [iphone_id]
    bot_client.send_message.assert_awaited_once()
