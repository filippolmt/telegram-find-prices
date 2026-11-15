"""
make replay scores every post against candidate names with the matcher importable now.
"""

import asyncio

import pytest

from replay import candidate_names, prices_by_post_name
from user_session import channel_entity


def test_candidate_names_are_the_first_words_of_each_line():
    assert candidate_names("🎧 BOSE QuietComfort cuffie wireless\n📉 A 161,46€\nok") == {"bose quietcomfort cuffie", "a 161,46€"}


def test_prices_rebuild_hidden_links_and_price_each_name():
    post = {
        "channel": "deals",
        "id": 1,
        "message": "TCL soundbar 340W\nA 79€\n\nBOSE QuietComfort cuffie\nA 161€ Apri link",
        "entities": [[len("TCL soundbar 340W\nA 79€\n\nBOSE QuietComfort cuffie\nA 161€ "), 9, "https://amzn.eu/d/x"]],
        "buttons": ["https://t.me/share/url?text=euro%20"],
    }
    prices = prices_by_post_name([post])
    assert prices["deals", 1, "tcl soundbar 340w"] == 79.0
    assert prices["deals", 1, "bose quietcomfort cuffie"] == 161.0


def test_dev_scripts_reject_an_invalid_channel_before_telegram():
    """Channel identifiers are validated before they reach the Telegram API, numeric ids included."""
    class Client:
        async def get_entity(self, ref):
            return ref

    assert asyncio.run(channel_entity(Client(), "-1001795509166")) == -1001795509166
    assert asyncio.run(channel_entity(Client(), "@pallok")) == "pallok"
    with pytest.raises(SystemExit, match="Invalid channel"):
        asyncio.run(channel_entity(Client(), "pallok; drop"))
