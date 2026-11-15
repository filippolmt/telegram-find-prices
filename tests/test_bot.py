"""
Tests for bot.py create_client function.
"""

from unittest.mock import MagicMock, patch

from telethon import TelegramClient

from bot import create_client, user_client_ready


@patch("bot.TelegramClient")
def test_create_client_file_session(mock_client_cls):
    """Without session_string, creates client with file-based session."""
    mock_client_cls.return_value = MagicMock(spec=TelegramClient)

    client = create_client("data/my_session", 12345, "abc123")

    mock_client_cls.assert_called_once_with("data/my_session", 12345, "abc123")
    assert client is mock_client_cls.return_value


@patch("bot.StringSession")
@patch("bot.TelegramClient")
def test_create_client_string_session(mock_client_cls, mock_string_session):
    """With session_string, creates client with StringSession."""
    mock_client_cls.return_value = MagicMock(spec=TelegramClient)
    mock_session = MagicMock()
    mock_string_session.return_value = mock_session

    client = create_client("data/my_session", 12345, "abc123", session_string="1BVtsOtest")

    mock_string_session.assert_called_once_with("1BVtsOtest")
    mock_client_cls.assert_called_once_with(mock_session, 12345, "abc123")
    assert client is mock_client_cls.return_value


@patch("bot.TelegramClient")
def test_create_client_empty_string_uses_file(mock_client_cls):
    """Empty session_string falls back to file-based session."""
    mock_client_cls.return_value = MagicMock(spec=TelegramClient)

    client = create_client("data/my_session", 12345, "abc123", session_string="")

    mock_client_cls.assert_called_once_with("data/my_session", 12345, "abc123")
    assert client is mock_client_cls.return_value


@patch("bot.TelegramClient")
def test_create_client_whitespace_string_uses_file(mock_client_cls):
    """Whitespace-only session_string falls back to file-based session."""
    mock_client_cls.return_value = MagicMock(spec=TelegramClient)

    client = create_client("data/my_session", 12345, "abc123", session_string="   ")

    mock_client_cls.assert_called_once_with("data/my_session", 12345, "abc123")
    assert client is mock_client_cls.return_value


class _UserClient:
    def __init__(self, authorized):
        self.authorized = authorized
        self.started = False

    async def connect(self):
        pass

    async def is_user_authorized(self):
        return self.authorized

    async def start(self, *args, **kwargs):
        self.started = True  # would ask Telegram for a login code and wait for it on stdin


async def test_unauthorized_user_session_never_asks_for_a_login_code(caplog):
    """In a container there is no terminal: a restart loop would send a code to the phone each time."""
    client = _UserClient(authorized=False)
    assert await user_client_ready(client) is False
    assert not client.started
    assert "CLIENT_SESSION_STRING" in caplog.text


async def test_authorized_user_session_is_ready():
    assert await user_client_ready(_UserClient(authorized=True)) is True
