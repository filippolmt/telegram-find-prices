"""
Live command: talk to a bot from the local user account, to verify or diagnose a command conversation.

`chat` prints the recent messages between the user account and a bot (any bot: read-only).
`send` starts the dev bot (BOT_TOKEN of .env) with the working tree's commands and a throwaway DB, sends
each message in turn from the user account and prints the reply. Bot and user client run in this one
process: the bot service is paused, so no session runs twice. Never point .env at production's BOT_TOKEN:
two processes on one bot token split every conversation.

The user client presents itself in --lang: the bot stores the sender's language on every message.

Run it with `make bot-chat` and `make live-command` (see the Makefile for the arguments).
"""

import argparse
import asyncio
import os
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from telethon import TelegramClient
from telethon.sessions import StringSession

from bot_commands import BotCommands
from client_commands import ClientCommands
from config import Config
from database import Base
from models import Product
from user_session import user_client


def chat_line(message) -> str:
    """One message as 'HH:MM:SS ME|BOT text', newlines shown as ⏎."""
    who = "ME " if message.out else "BOT"
    return f"{message.date:%H:%M:%S} {who} {(message.raw_text or '').replace(chr(10), ' ⏎ ')}"


async def chat(bot: str, limit: int, lang: str) -> int:
    async with user_client(lang) as client:
        messages = [m async for m in client.iter_messages(bot, limit=limit)]
    for message in reversed(messages):
        print(chat_line(message))
    return 0


async def send(texts: list[str], timeout: int, lang: str) -> int:
    db_path = os.path.join(tempfile.mkdtemp(), "live_command.sqlite3")
    session_factory = sessionmaker(bind=create_engine(f"sqlite:///{db_path}"))
    Base.metadata.create_all(session_factory.kw["bind"])

    async with user_client(lang) as user:
        # An in-memory bot session: the dev bot's session file stays with the paused bot service
        bot = TelegramClient(StringSession(), Config.API_ID, Config.API_HASH)
        await bot.start(bot_token=Config.BOT_TOKEN)
        try:
            me = await bot.get_me()
            print(f"dev bot: @{me.username}")
            BotCommands(bot, ClientCommands(user, session_factory, bot), session_factory).register_commands(me.username)
            async with user.conversation(me.username, timeout=timeout) as conv:
                for text in texts:
                    await conv.send_message(text)
                    print(f">> {text}")
                    try:
                        print(f"<< {(await conv.get_response()).raw_text}")
                    except TimeoutError:
                        print(f"!! no reply in {timeout}s")
                        return 1
        finally:
            await bot.disconnect()

    with session_factory() as session:
        for product in session.query(Product):
            print(f"saved: name={product.name!r} asin={product.asin} target={product.target_price} category={product.category}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--lang", default="it", help="language the user client presents to Telegram")
    commands = parser.add_subparsers(dest="command", required=True)
    chat_args = commands.add_parser("chat", parents=[common], help="print the recent messages with a bot")
    chat_args.add_argument("--bot", required=True, help="bot username")
    chat_args.add_argument("--limit", type=int, default=40)
    send_args = commands.add_parser("send", parents=[common], help="send messages to the dev bot and print its replies")
    send_args.add_argument("--send", action="append", required=True, help="a message; repeat in conversation order")
    send_args.add_argument("--timeout", type=int, default=20, help="seconds to wait for each reply")
    args = parser.parse_args()

    if args.command == "chat":
        return asyncio.run(chat(args.bot, args.limit, args.lang))
    return asyncio.run(send(args.send, args.timeout, args.lang))


if __name__ == "__main__":
    raise SystemExit(main())
