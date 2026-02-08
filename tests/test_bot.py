"""
Tests for bot.py create_client function.
"""

from unittest.mock import patch, MagicMock
from telethon import TelegramClient

from bot import create_client


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
