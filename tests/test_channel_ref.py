"""
Tests for channel references: user-supplied ones (/add_channel trust boundary) and stored identifiers.
"""

from types import SimpleNamespace

import pytest

from bot_commands import parse_channel_ref
from models import ChannelIdentifier


@pytest.mark.parametrize(
    "text, expected",
    [
        ("offertepazze", ("username", "offertepazze")),
        ("@offertepazze", ("username", "offertepazze")),
        ("https://t.me/offertepazze", ("username", "offertepazze")),
        ("http://t.me/offertepazze", ("username", "offertepazze")),
        ("https://telegram.me/offertepazze", ("username", "offertepazze")),
        ("http://telegram.me/offertepazze", ("username", "offertepazze")),
        ("t.me/offertepazze", ("username", "offertepazze")),
        ("telegram.me/offertepazze", ("username", "offertepazze")),
        ("tg://resolve?domain=offertepazze", ("username", "offertepazze")),
        ("https://t.me/@offertepazze", ("username", "offertepazze")),
        ("  @offertepazze  ", ("username", "offertepazze")),
        ("https://t.me/+AbC_d-1", ("invite", "AbC_d-1")),
        ("+AbC_d-1", ("invite", "AbC_d-1")),
        ("https://t.me/joinchat/AbC_d-1", ("invite", "AbC_d-1")),
        ("joinchat/AbC_d-1", ("invite", "AbC_d-1")),
        # invalid usernames
        ("abc", ("invalid_username", None)),
        ("1abcd", ("invalid_username", None)),
        ("a" * 33, ("invalid_username", None)),
        ("off erte", ("invalid_username", None)),
        ("offerte/123", ("invalid_username", None)),
        ("", ("invalid_username", None)),
        ("https://evil.com/offerte", ("invalid_username", None)),
        # invalid invite hashes
        ("+", ("invalid_username", None)),  # empty hash: not an invite, as before #32
        ("joinchat/", ("invalid_username", None)),
        ("+abc/def", ("invalid_invite", None)),
        ("joinchat/a b", ("invalid_invite", None)),
        ("+abc\ndef", ("invalid_invite", None)),
    ],
)
def test_parse_channel_ref(text, expected):
    assert parse_channel_ref(text) == expected


@pytest.mark.parametrize("identifier, peer", [
    ("deals", "deals"),  # username
    ("1795509166", 1795509166),  # private channel, stored as its bare id
    ("-1001795509166", -1001795509166),  # marked id, as given on the command line
])
def test_channel_identifier_peer(identifier, peer):
    assert ChannelIdentifier(identifier).peer == peer


def test_channel_identifier_of_a_chat_is_its_username_else_its_id():
    assert ChannelIdentifier.of(SimpleNamespace(username="deals", id=1)) == "deals"
    assert ChannelIdentifier.of(SimpleNamespace(username=None, id=1795509166)) == "1795509166"
