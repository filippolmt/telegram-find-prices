"""
Tests for user authorization: ALLOWED_USERS parsing and fail-closed policy.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import bot_commands
from bot_commands import BotCommands
from config import parse_allowed_users
from models import User


def test_parse_allowed_users_valid():
    assert parse_allowed_users("123, 456 ,789") == [123, 456, 789]


def test_parse_allowed_users_empty():
    assert parse_allowed_users("") == []
    assert parse_allowed_users(" , ") == []


def test_parse_allowed_users_drops_invalid_and_warns(caplog):
    assert parse_allowed_users("123,@me,abc") == [123]
    assert "@me" in caplog.text and "abc" in caplog.text


def _make_bot(monkeypatch, db_session_factory, allowed, allow_all):
    monkeypatch.setattr(bot_commands.Config, "ALLOWED_USERS", allowed)
    monkeypatch.setattr(bot_commands.Config, "ALLOW_ALL_USERS", allow_all)
    return BotCommands(MagicMock(), MagicMock(), db_session_factory)


@pytest.mark.parametrize(
    "allowed, allow_all, user_id, expected",
    [
        ([], False, 1, False),  # fail closed: nothing configured
        ([], True, 1, True),  # explicit opt-in to open bot
        ([1], False, 1, True),
        ([1], False, 2, False),
        ([1], True, 2, False),  # an explicit list wins over ALLOW_ALL_USERS
        ([1], False, None, False),
    ],
)
def test_is_authorized(monkeypatch, db_session_factory, allowed, allow_all, user_id, expected):
    bot = _make_bot(monkeypatch, db_session_factory, allowed, allow_all)
    assert bot._is_authorized(user_id) is expected


def _event(user_id, username="stranger"):
    sender = SimpleNamespace(username=username, lang_code="en")

    async def get_sender():
        return sender

    return SimpleNamespace(sender_id=user_id, get_sender=get_sender)


async def test_unauthorized_user_is_not_registered(monkeypatch, db_session_factory):
    bot = _make_bot(monkeypatch, db_session_factory, [1], False)

    username, user_id, _, created = await bot.register_user_if_not_exists(_event(2))

    assert (username, user_id, created) == ("stranger", 2, False)
    with db_session_factory() as session:
        assert session.query(User).count() == 0


async def test_authorized_user_is_registered(monkeypatch, db_session_factory):
    bot = _make_bot(monkeypatch, db_session_factory, [1], False)

    _, _, _, created = await bot.register_user_if_not_exists(_event(1, "owner"))

    assert created is True
    with db_session_factory() as session:
        assert session.query(User).filter_by(user_id=1).one().username == "owner"

