"""
Tests for ClientCommands.backfill_channel().
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from client_commands import ClientCommands
from models import PriceHistory, Product, User

MESSAGES = [
    SimpleNamespace(id=1, text="iPhone 15 a 499€"),
    SimpleNamespace(id=2, text="unrelated offer"),
]


def _fake_client():
    async def iter_messages(entity, limit):
        for m in MESSAGES:
            yield m

    client = MagicMock()
    client.get_entity = AsyncMock(return_value=SimpleNamespace(title="Deals", username="deals", id=123))
    client.iter_messages = iter_messages
    return client


async def _run_backfill(db_session_factory, paused):
    with db_session_factory() as session:
        session.add(User(user_id=100, paused=paused))
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
