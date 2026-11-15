"""
Backfill and Realtime match the same Telethon message the same way.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from telethon.tl.custom.message import Message
from telethon.tl.types import (
    InlineButtonTypeUrl,
    KeyboardInlineButton,
    KeyboardInlineButtonRow,
    MessageEntityBold,
    MessageEntityTextUrl,
    PeerChannel,
    ReplyInlineMarkup,
)

from channel_listener import ChannelListener
from client_commands import ClientCommands
from models import Channel, PriceHistory, Product, User, UserChannel

TEXT = "iPhone 15 a 499€\nVisualizza offerta su Amazon"
CHAT = SimpleNamespace(title="Deals", username="deals", id=123)


def _formatted_post():
    """Product name in bold, an Amazon URL behind link text and another in a URL button."""
    return Message(
        id=7,
        peer_id=PeerChannel(123),
        message=TEXT,
        entities=[
            MessageEntityBold(offset=0, length=6),
            MessageEntityTextUrl(offset=17, length=27, url="https://www.amazon.it/dp/B0LINKTEXT"),
        ],
        reply_markup=ReplyInlineMarkup([
            KeyboardInlineButtonRow([KeyboardInlineButton("Compra", InlineButtonTypeUrl("https://amzn.eu/d/B0BUTTON"))]),
        ]),
    )


def _setup(db_session_factory):
    with db_session_factory() as session:
        session.add_all([User(user_id=100), Channel(identifier="deals")])
        session.flush()
        session.add(UserChannel(user_id=100, channel_id=session.query(Channel).one().id))
        session.add_all([
            Product(user_id=100, name="iPhone 15", target_price=600),
            Product(user_id=100, name="B0LINKTEXT"),
            Product(user_id=100, name="B0BUTTON"),
            Product(user_id=100, name="AirPods"),
        ])
        session.commit()
    bot_client = MagicMock()
    bot_client.send_message = AsyncMock()
    return bot_client


def _history(db_session_factory):
    with db_session_factory() as session:
        names = dict(session.query(Product.id, Product.name))
        return sorted((h.source, names[h.product_id], h.price, h.message_text) for h in session.query(PriceHistory))


async def test_backfill_and_realtime_match_formatted_post_the_same(db_session_factory):
    bot_client = _setup(db_session_factory)

    async def iter_messages(entity, limit, offset_id=0):
        yield _formatted_post()

    client = MagicMock()
    client.get_entity = AsyncMock(return_value=CHAT)
    client.iter_messages = iter_messages
    await ClientCommands(client, db_session_factory, bot_client).backfill_channel("deals", 100)

    handlers = []
    listener_client = MagicMock()
    listener_client.on = lambda _event: lambda fn: handlers.append(fn) or fn
    ChannelListener(listener_client, bot_client, db_session_factory).register()
    await handlers[0](SimpleNamespace(message=_formatted_post(), id=7, get_chat=AsyncMock(return_value=CHAT)))

    matches = [("iPhone 15", 499, TEXT), ("B0LINKTEXT", None, TEXT), ("B0BUTTON", None, TEXT)]
    assert _history(db_session_factory) == sorted(
        [("backfill", *m) for m in matches] + [("realtime", *m) for m in matches]
    )
