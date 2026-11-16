"""
Tests for user authorization: ALLOWED_USERS parsing and fail-closed policy.
"""

import pytest

from config import parse_allowed_users
from models import User
from tests.fakes import chat_event, make_bot, registered_bot
from translations import t


def test_parse_allowed_users_valid():
    assert parse_allowed_users("123, 456 ,789") == [123, 456, 789]


def test_parse_allowed_users_empty():
    assert parse_allowed_users("") == []
    assert parse_allowed_users(" , ") == []


def test_parse_allowed_users_drops_invalid_and_warns(caplog):
    assert parse_allowed_users("123,@me,abc") == [123]
    assert "@me" in caplog.text and "abc" in caplog.text


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
    bot = make_bot(monkeypatch, db_session_factory, allowed, allow_all)
    assert bot._is_authorized(user_id) is expected


def _recording_flow():
    calls = []

    async def flow(event, ctx):
        calls.append(ctx)

    return flow, calls


async def test_gate_rejects_unauthorized_sender_without_persisting(monkeypatch, db_session_factory):
    bot = make_bot(monkeypatch, db_session_factory, [1], False)
    flow, calls = _recording_flow()
    event = chat_event(2)

    await bot._gate(flow)(event)

    assert event.replies == [t("not_authorized", "en")]
    assert calls == []
    with db_session_factory() as session:
        assert session.query(User).count() == 0


async def test_gate_runs_flow_for_authorized_sender_without_username(monkeypatch, db_session_factory):
    bot = make_bot(monkeypatch, db_session_factory, [1], False)
    flow, calls = _recording_flow()
    event = chat_event(1, username=None)

    await bot._gate(flow)(event)

    assert event.replies == []
    assert [(c.user_id, c.username) for c in calls] == [(1, None)]


async def test_gate_rejects_unauthorized_sender_without_username_without_persisting(monkeypatch, db_session_factory):
    bot = make_bot(monkeypatch, db_session_factory, [1], False)
    flow, calls = _recording_flow()
    event = chat_event(2, username=None)

    await bot._gate(flow)(event)

    assert event.replies == [t("not_authorized", "en")]
    assert calls == []
    with db_session_factory() as session:
        assert session.query(User).count() == 0


async def test_gate_runs_flow_with_context_for_authorized_sender(monkeypatch, db_session_factory):
    bot = make_bot(monkeypatch, db_session_factory, [1], False)
    flow, calls = _recording_flow()
    event = chat_event(1, "owner")

    await bot._gate(flow)(event)

    assert event.replies == []
    assert [(c.user_id, c.username, c.lang) for c in calls] == [(1, "owner", "en")]
    with db_session_factory() as session:
        assert session.query(User).filter_by(user_id=1).one().username == "owner"


async def test_start_without_username_registers_and_greets_by_first_name(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory)
    event = chat_event(1, username=None, first_name="Bruno")

    await bot.bot_client.dispatch("/start", event)

    assert event.replies == [t("welcome", "en", name="Bruno")]
    with db_session_factory() as session:
        assert session.query(User).filter_by(user_id=1).one().username is None


async def test_start_greets_by_user_id_without_username_or_first_name(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory)
    event = chat_event(1, username=None, first_name=None)

    await bot.bot_client.dispatch("/start", event)

    assert event.replies == [t("welcome", "en", name="1")]


async def test_gate_never_registers_a_channel_sender_even_when_all_users_are_allowed(monkeypatch, db_session_factory):
    # Anonymous group admins and linked channels send with a negative (channel) id
    bot = make_bot(monkeypatch, db_session_factory, [], True)
    flow, calls = _recording_flow()
    event = chat_event(-1001234567890, username=None)

    await bot._gate(flow)(event)

    assert event.replies == [t("users_only", "en")]
    assert calls == []
    with db_session_factory() as session:
        assert session.query(User).count() == 0


@pytest.mark.parametrize("command", ["/start", "/watch"])
async def test_command_from_a_channel_sender_says_the_bot_is_for_users_only(monkeypatch, db_session_factory, command):
    bot = registered_bot(monkeypatch, db_session_factory)
    event = chat_event(-1001234567890, username=None)

    await bot.bot_client.dispatch(command, event)

    assert event.replies == [t("users_only", "en")]
    with db_session_factory() as session:
        assert session.query(User).count() == 0


async def test_stored_username_follows_the_sender_after_changes_and_removal(monkeypatch, db_session_factory):
    bot = make_bot(monkeypatch, db_session_factory, [1], False)
    flow, _ = _recording_flow()

    for username in ["owner", "owner_renamed", None]:
        await bot._gate(flow)(chat_event(1, username=username))
        with db_session_factory() as session:
            assert session.query(User).filter_by(user_id=1).one().username == username


async def test_registered_command_runs_flow_for_authorized_sender(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory)

    await bot.bot_client.dispatch("/pause", chat_event(1, "owner"))

    with db_session_factory() as session:
        assert session.query(User).filter_by(user_id=1).one().paused is True
