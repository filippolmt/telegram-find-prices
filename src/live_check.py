"""
Live check: run real channel messages through Backfill and Realtime.

Uses the local user-client session against real channels, a throwaway SQLite DB
and a bot client that prints notifications instead of sending them, so the real
DB and real users stay untouched. Every product is watched by two users, since
monitored channels are shared: exits 1 if Backfill and Realtime disagree, or if
the two users' matches differ.

Run it with `make live-check` (see the Makefile for the arguments).
"""

import argparse
import asyncio
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from channel_listener import ChannelListener
from client_commands import ClientCommands
from config import Config
from database import Base
from models import Channel, ChannelIdentifier, MatchSource, PriceHistory, Product, User
from user_session import channel_entity, user_client

USERS = (1, 2)


class PrintBot:
    async def send_message(self, user_id, text, parse_mode=None):
        print(f"\n--- notification to user {user_id} ---\n{text}\n---")


def _parse_product(spec: str, user_id: int) -> Product:
    name, _, target = spec.partition("=")
    name, _, asin = name.partition("#")
    return Product(user_id=user_id, name=name.strip(), asin=asin.strip().upper() or None, target_price=float(target) if target else None)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--channel", action="append", required=True, help="username or numeric id (-100...)")
    parser.add_argument("--product", action="append", required=True, help="'name', 'name=target_price', optionally 'name#ASIN=target_price'")
    parser.add_argument("--limit", type=int, default=50, help="recent messages per channel")
    parser.add_argument("--lang", default="it")
    args = parser.parse_args()

    db_path = os.path.join(tempfile.mkdtemp(), "live_check.sqlite3")
    session_factory = sessionmaker(bind=create_engine(f"sqlite:///{db_path}"))
    Base.metadata.create_all(session_factory.kw["bind"])

    async with user_client() as client:
        entities = [await channel_entity(client, identifier) for identifier in args.channel]

        Config.ALLOWED_USERS, Config.ALLOW_ALL_USERS = list(USERS), False
        with session_factory() as session:
            session.add_all(User(user_id=user_id, lang_code=args.lang) for user_id in USERS)
            session.flush()
            session.add_all(_parse_product(spec, user_id) for user_id in USERS for spec in args.product)
            # Same identifier join_channel stores: username, else the bare channel id
            session.add_all(Channel(identifier=ChannelIdentifier.of(entity), title=entity.title)
                            for entity in entities)
            session.commit()

        bot = PrintBot()
        commands = ClientCommands(client, session_factory, bot)
        handlers = []
        fake_listener_client = MagicMock()
        fake_listener_client.on = lambda _event: lambda fn: handlers.append(fn) or fn
        fake_listener_client.get_me = client.get_me  # the owner, for private channels' post links
        ChannelListener(fake_listener_client, bot, session_factory).register()

        for identifier, entity in zip(args.channel, entities, strict=True):
            print(f"\n===== {entity.title} =====")
            await commands.backfill_channel(identifier, limit=args.limit)
            # Replay the same messages through the Realtime handler, as NewMessage events would arrive
            async for message in client.iter_messages(entity, limit=args.limit):
                event = SimpleNamespace(message=message, id=message.id, get_chat=lambda e=entity: _resolved(e))
                await handlers[0](event)

    with session_factory() as session:
        rows = session.query(PriceHistory.user_id, PriceHistory.source, PriceHistory.product_id,
                             PriceHistory.message_link, PriceHistory.price).all()
        names = dict(session.query(Product.id, Product.name))
    by_user = {user_id: {source: {(names[p], link, price) for u, s, p, link, price in rows if u == user_id and s == source}
                         for source in MatchSource} for user_id in USERS}
    found = by_user[USERS[0]]

    print("\n===== matches =====")
    for name, link, price in sorted(found[MatchSource.BACKFILL] | found[MatchSource.REALTIME], key=str):
        sources = [s.value for s in MatchSource if (name, link, price) in found[s]]
        print(f"{name!r:30} price={price} {link} [{', '.join(sources)}]")
    if found[MatchSource.BACKFILL] != found[MatchSource.REALTIME]:
        print("\nFAIL: Backfill and Realtime disagree on the same messages")
        return 1
    if by_user[USERS[1]] != found:
        print(f"\nFAIL: user {USERS[1]} watching the same products got other matches than user {USERS[0]}")
        return 1
    print(f"\nOK: {len(found[MatchSource.BACKFILL])} matches for each of {len(USERS)} users, Backfill and Realtime agree")
    return 0


async def _resolved(value):
    return value


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
