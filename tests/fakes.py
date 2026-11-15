"""
In-memory stand-ins for Telethon events and the bot client, shared by bot command tests.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import bot_commands
from bot_commands import BotCommands


def make_bot(monkeypatch, db_session_factory, allowed, allow_all):
    monkeypatch.setattr(bot_commands.Config, "ALLOWED_USERS", allowed)
    monkeypatch.setattr(bot_commands.Config, "ALLOW_ALL_USERS", allow_all)
    return BotCommands(MagicMock(), MagicMock(), db_session_factory)


def sender_event(user_id, username="stranger"):
    sender = SimpleNamespace(username=username, lang_code="en")

    async def get_sender():
        return sender

    return SimpleNamespace(sender_id=user_id, get_sender=get_sender)


def chat_event(user_id, username="stranger"):
    event = sender_event(user_id, username)
    event.replies = []

    async def respond(text):
        event.replies.append(text)

    event.respond = respond
    return event


def conversation_event(answers, user_id=1, username="owner"):
    """A chat event whose conversation replies with `answers` in order; an exception instance is raised instead."""
    event = chat_event(user_id, username)
    event.chat_id = user_id
    answers = iter(answers)

    async def wait_event(_builder):
        answer = next(answers)
        if isinstance(answer, BaseException):
            raise answer
        return SimpleNamespace(raw_text=answer)

    event.conversations = 0

    @asynccontextmanager
    async def conversation(_chat_id, timeout):
        event.conversations += 1
        yield SimpleNamespace(wait_event=wait_event)

    event.client = SimpleNamespace(conversation=conversation)
    return event


class FakeBotClient:
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


def registered_bot(monkeypatch, db_session_factory):
    bot = make_bot(monkeypatch, db_session_factory, [1], False)
    bot.bot_client = FakeBotClient()
    bot.register_commands()
    return bot
