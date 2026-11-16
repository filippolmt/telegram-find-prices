"""
The bot publishes its own command list at startup: the commands it registered, described in every language.
"""

from telethon.errors import RPCError
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.types import BotCommandScopeUsers

from tests.fakes import registered_bot
from translations import t

REGISTERED = ["start", "add_channel", "list_channels", "requests", "remove_channel", "watch", "list_products",
              "unwatch", "history", "pause", "resume", "stats", "list_categories"]


async def test_command_list_is_the_registered_commands_in_every_language(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory)

    await bot.publish_commands()

    sent = {r.lang_code: r for r in bot.bot_client.requests if isinstance(r, SetBotCommandsRequest)}
    assert sorted(sent) == ["", "it"]  # "" is the default: English
    for lang_code, lang in (("", "en"), ("it", "it")):
        assert isinstance(sent[lang_code].scope, BotCommandScopeUsers)
        assert [(c.command, c.description) for c in sent[lang_code].commands] == [
            (name, t(f"command_{name}", lang)) for name in REGISTERED]


async def test_command_list_refused_by_telegram_is_logged(monkeypatch, db_session_factory, caplog):
    bot = registered_bot(monkeypatch, db_session_factory)

    async def refuse(_request):
        raise RPCError(None, "BOT_COMMAND_INVALID", 400)

    monkeypatch.setattr(type(bot.bot_client), "__call__", lambda self, request: refuse(request))

    await bot.publish_commands()

    assert "Command list not published" in caplog.text
