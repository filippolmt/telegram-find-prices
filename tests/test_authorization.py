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
from translations import t


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

    sender = await bot.register_user_if_not_exists(_event(2))

    assert (sender.username, sender.user_id) == ("stranger", 2)
    with db_session_factory() as session:
        assert session.query(User).count() == 0


async def test_authorized_user_is_registered(monkeypatch, db_session_factory):
    bot = _make_bot(monkeypatch, db_session_factory, [1], False)

    await bot.register_user_if_not_exists(_event(1, "owner"))

    with db_session_factory() as session:
        assert session.query(User).filter_by(user_id=1).one().username == "owner"


def _gate_event(user_id, username="stranger"):
    event = _event(user_id, username)
    event.replies = []

    async def respond(text):
        event.replies.append(text)

    event.respond = respond
    return event


def _recording_flow():
    calls = []

    async def flow(event, ctx):
        calls.append(ctx)

    return flow, calls


async def test_gate_rejects_unauthorized_sender_without_persisting(monkeypatch, db_session_factory):
    bot = _make_bot(monkeypatch, db_session_factory, [1], False)
    flow, calls = _recording_flow()
    event = _gate_event(2)

    await bot._gate(flow)(event)

    assert event.replies == [t("not_authorized", "en")]
    assert calls == []
    with db_session_factory() as session:
        assert session.query(User).count() == 0


async def test_gate_asks_sender_without_username_to_start_first(monkeypatch, db_session_factory):
    bot = _make_bot(monkeypatch, db_session_factory, [1], False)
    flow, calls = _recording_flow()
    event = _gate_event(1, username=None)

    await bot._gate(flow)(event)

    assert event.replies == [t("start_first", "en")]
    assert calls == []


async def test_gate_runs_flow_with_context_for_authorized_sender(monkeypatch, db_session_factory):
    bot = _make_bot(monkeypatch, db_session_factory, [1], False)
    flow, calls = _recording_flow()
    event = _gate_event(1, "owner")

    await bot._gate(flow)(event)

    assert event.replies == []
    assert [(c.user_id, c.username, c.lang) for c in calls] == [(1, "owner", "en")]
    with db_session_factory() as session:
        assert session.query(User).filter_by(user_id=1).one().username == "owner"


class _FakeBotClient:
    """Records handlers by event builder, as TelegramClient.on would."""

    def __init__(self):
        self.handlers = []

    def on(self, builder):
        def add(handler):
            self.handlers.append((builder, handler))
            return handler

        return add

    async def dispatch(self, text, event):
        matched = [h for b, h in self.handlers if b.pattern(text)]
        assert len(matched) == 1, f"{text!r} matched {len(matched)} handlers"
        await matched[0](event)


def _registered_bot(monkeypatch, db_session_factory):
    bot = _make_bot(monkeypatch, db_session_factory, [1], False)
    bot.bot_client = _FakeBotClient()
    bot.register_commands()
    return bot


async def test_start_without_username_is_not_authorized(monkeypatch, db_session_factory):
    bot = _registered_bot(monkeypatch, db_session_factory)
    event = _gate_event(1, username=None)

    await bot.bot_client.dispatch("/start", event)

    assert event.replies == [t("not_authorized", "en")]


async def test_registered_command_runs_flow_for_authorized_sender(monkeypatch, db_session_factory):
    bot = _registered_bot(monkeypatch, db_session_factory)

    await bot.bot_client.dispatch("/pause", _gate_event(1, "owner"))

    with db_session_factory() as session:
        assert session.query(User).filter_by(user_id=1).one().paused is True
