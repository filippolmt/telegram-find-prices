"""
Tests for the /add_channel conversation, through the registered command and an in-memory conversation.
"""

from unittest.mock import AsyncMock

from tests.fakes import conversation_event, registered_bot
from translations import t


async def test_add_channel_takes_the_channel_given_with_the_command(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory)
    bot.client_commands.join_channel = AsyncMock(return_value=(False, "join failed", None))
    event = conversation_event([])

    await bot.bot_client.dispatch("/add_channel @offerte_test", event)

    bot.client_commands.join_channel.assert_awaited_once_with("offerte_test", 1, lang="en")
    assert event.replies == ["join failed"]


async def test_add_channel_validates_the_channel_given_with_the_command(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory)
    bot.client_commands.join_channel = AsyncMock()
    event = conversation_event([])

    await bot.bot_client.dispatch("/add_channel not a channel!", event)

    bot.client_commands.join_channel.assert_not_awaited()
    assert event.replies == [t("invalid_channel_id", "en")]


async def test_add_channel_without_argument_asks_for_the_channel(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory)
    bot.client_commands.join_channel = AsyncMock(return_value=(False, "join failed", None))
    event = conversation_event(["@offerte_test"])

    await bot.bot_client.dispatch("/add_channel", event)

    bot.client_commands.join_channel.assert_awaited_once_with("offerte_test", 1, lang="en")
    assert event.replies == [t("add_channel_prompt", "en"), "join failed"]


async def test_add_channel_takes_an_invite_link_given_with_the_command(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory)
    bot.client_commands.join_channel = AsyncMock(return_value=(False, "join failed", None))
    event = conversation_event([])

    await bot.bot_client.dispatch("/add_channel https://t.me/+AbCdEfGhIjKlMnOp", event)

    bot.client_commands.join_channel.assert_awaited_once_with("", 1, invite_hash="AbCdEfGhIjKlMnOp", lang="en")
    assert event.replies == ["join failed"]


async def test_add_channel_cancelled_with_the_command_joins_nothing(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory)
    bot.client_commands.join_channel = AsyncMock()
    event = conversation_event([])

    await bot.bot_client.dispatch("/add_channel cancel", event)

    bot.client_commands.join_channel.assert_not_awaited()
    assert event.replies == [t("operation_cancelled", "en")]
