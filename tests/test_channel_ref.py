"""
Tests for parsing user-supplied channel references (/add_channel trust boundary).
"""

import pytest

from bot_commands import parse_channel_ref


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
        ("+", ("invalid_invite", None)),
        ("+abc/def", ("invalid_invite", None)),
        ("joinchat/a b", ("invalid_invite", None)),
        ("+abc\ndef", ("invalid_invite", None)),
    ],
)
def test_parse_channel_ref(text, expected):
    assert parse_channel_ref(text) == expected
