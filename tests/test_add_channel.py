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
