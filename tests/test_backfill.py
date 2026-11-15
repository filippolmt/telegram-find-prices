"""
Tests for ClientCommands.backfill_channel().
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from telethon.errors import FloodWaitError
from telethon.tl.custom.message import Message
from telethon.tl.types import PeerChannel

import client_commands
from client_commands import ClientCommands
from models import PriceHistory, Product, User


def _msg(id, text):
    return Message(id=id, peer_id=PeerChannel(123), message=text)


MESSAGES = [
    _msg(1, "iPhone 15 a 499€"),
    _msg(2, "unrelated offer"),
]


def _fake_client():
    async def iter_messages(entity, limit, offset_id=0):
        for m in MESSAGES:
            yield m

    client = MagicMock()
    client.get_entity = AsyncMock(return_value=SimpleNamespace(title="Deals", username="deals", id=123))
    client.iter_messages = iter_messages
    return client


async def _run_backfill(db_session_factory, paused):
    with db_session_factory() as session:
        session.add(User(user_id=100, paused=paused))
        session.flush()
        session.add(Product(user_id=100, name="iPhone 15", target_price=600))
        session.commit()

    bot_client = MagicMock()
    bot_client.send_message = AsyncMock()
    found = await ClientCommands(_fake_client(), db_session_factory, bot_client).backfill_channel("deals", 100)

    with db_session_factory() as session:
        history = session.query(PriceHistory).all()
        assert [(h.source, h.price, h.message_link) for h in history] == [("backfill", 499, "https://t.me/deals/1")]
    assert found == 1
    return bot_client


async def test_backfill_paused_user_records_without_notifying(db_session_factory):
    bot_client = await _run_backfill(db_session_factory, paused=True)
    bot_client.send_message.assert_not_awaited()


async def test_backfill_active_user_is_notified(db_session_factory):
    bot_client = await _run_backfill(db_session_factory, paused=False)
    bot_client.send_message.assert_awaited_once()
    assert bot_client.send_message.await_args.args[0] == 100


async def test_backfill_skips_product_unwatched_during_scan(db_session_factory):
    with db_session_factory() as session:
        session.add(User(user_id=100))
        session.flush()
        session.add(Product(user_id=100, name="iPhone 15", target_price=600))
        session.add(Product(user_id=100, name="AirPods"))
        session.commit()

    client = _fake_client()

    async def iter_messages(entity, limit, offset_id=0):
        # The user unwatches iPhone 15 after the backfill read its products.
        with db_session_factory() as session:
            session.query(Product).filter_by(name="iPhone 15").delete()
            session.commit()
        yield _msg(1, "iPhone 15 a 499€")
        yield _msg(2, "AirPods a 99€")

    client.iter_messages = iter_messages
    bot_client = MagicMock()
    bot_client.send_message = AsyncMock()

    found = await ClientCommands(client, db_session_factory, bot_client).backfill_channel("deals", 100)

    with db_session_factory() as session:
        assert [h.message_link for h in session.query(PriceHistory)] == ["https://t.me/deals/2"]
    assert found == 1
    bot_client.send_message.assert_awaited_once()


async def test_backfill_resumes_after_flood_wait(db_session_factory, monkeypatch):
    with db_session_factory() as session:
        session.add(User(user_id=100))
        session.flush()
        session.add(Product(user_id=100, name="iPhone 15"))
        session.commit()

    newest_first = [_msg(3, "iPhone 15 a 499€"), _msg(2, "unrelated"), _msg(1, "iPhone 15 a 450€")]
    calls = []

    async def iter_messages(entity, limit, offset_id=0):
        calls.append((limit, offset_id))
        for m in newest_first:
            if offset_id and m.id >= offset_id:
                continue
            yield m
            if len(calls) == 1:
                raise FloodWaitError(None, capture=30)

    client = _fake_client()
    client.iter_messages = iter_messages
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(client_commands.asyncio, "sleep", fake_sleep)

    found = await ClientCommands(client, db_session_factory, MagicMock(send_message=AsyncMock())).backfill_channel(
        "deals", 100, limit=3)

    assert found == 2
    assert slept.count(30) == 1  # other sleeps: the notification throttle
    assert calls == [(3, 0), (2, 3)]
