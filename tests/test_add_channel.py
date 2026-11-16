"""
Tests for the /add_channel conversation: how the channel is given, through the registered command and the owner's account.
"""

from unittest.mock import AsyncMock

from bot_commands import BotCommands
from client_commands import ClientCommands
from config import Config
from tests.fakes import (
    OWNER,
    FakeBotClient,
    FakeUserClient,
    channel,
    conversation_event,
)
from translations import t

DEALS = channel(1, "offerte_test", "Offerte")


def _bot(db_session_factory, **client_args):
    Config.ALLOWED_USERS = [OWNER]  # restored by the every_user_allowed fixture
    client = FakeUserClient(channels=(DEALS,), **client_args)
    commands = ClientCommands(client, db_session_factory, None)
    commands.backfill_channel = AsyncMock(return_value=0)
    bot = BotCommands(FakeBotClient(), commands, db_session_factory)
    bot.register_commands()
    return bot, client


async def test_add_channel_takes_the_channel_given_with_the_command(db_session_factory):
    bot, client = _bot(db_session_factory)

    await bot.bot_client.dispatch("/add_channel @offerte_test", conversation_event([], user_id=OWNER))

    assert client.joined == {DEALS.id}


async def test_add_channel_validates_the_channel_given_with_the_command(db_session_factory):
    bot, client = _bot(db_session_factory)
    event = conversation_event([], user_id=OWNER)

    await bot.bot_client.dispatch("/add_channel not a channel!", event)

    assert event.replies == [t("invalid_channel_id", "en")]
    assert client.requests == []


async def test_add_channel_without_argument_asks_for_the_channel(db_session_factory):
    bot, client = _bot(db_session_factory)
    event = conversation_event(["@offerte_test"], user_id=OWNER)

    await bot.bot_client.dispatch("/add_channel", event)

    assert event.replies[0] == t("add_channel_prompt", "en")
    assert client.joined == {DEALS.id}


async def test_add_channel_takes_an_invite_link_given_with_the_command(db_session_factory):
    bot, client = _bot(db_session_factory, invites={"AbCdEfGhIjKlMnOp": DEALS})

    await bot.bot_client.dispatch("/add_channel https://t.me/+AbCdEfGhIjKlMnOp", conversation_event([], user_id=OWNER))

    assert client.joined == {DEALS.id}
    assert bot.client_commands.list_channels() == ["Offerte (offerte_test)"]


async def test_add_channel_join_refused_monitors_nothing(db_session_factory):
    bot, _ = _bot(db_session_factory)
    event = conversation_event([], user_id=OWNER)

    await bot.bot_client.dispatch("/add_channel @unknown_channel", event)

    assert event.replies == [t("join_channel_failed", "en")]
    assert bot.client_commands.list_channels() == []


async def test_add_channel_cancelled_with_the_command_joins_nothing(db_session_factory):
    bot, client = _bot(db_session_factory)
    event = conversation_event([], user_id=OWNER)

    await bot.bot_client.dispatch("/add_channel cancel", event)

    assert event.replies == [t("operation_cancelled", "en")]
    assert client.requests == []
