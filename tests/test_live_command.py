"""
make bot-chat prints the chat with a bot one message per line.
"""

from datetime import datetime
from types import SimpleNamespace

from live_command import chat_line


def test_chat_line_marks_the_sender_and_keeps_one_line():
    sent = SimpleNamespace(out=True, date=datetime(2026, 11, 15, 13, 43, 11), raw_text="/watch x")
    received = SimpleNamespace(out=False, date=datetime(2026, 11, 15, 13, 43, 12), raw_text="Which product?\n(/cancel)")

    assert chat_line(sent) == "13:43:11 ME  /watch x"
    assert chat_line(received) == "13:43:12 BOT Which product? ⏎ (/cancel)"
