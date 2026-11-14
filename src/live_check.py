"""
Live check: run real channel messages through Backfill and Realtime.

Uses the local user-client session against real channels, a throwaway SQLite DB
and a bot client that prints notifications instead of sending them, so the real
DB and real users stay untouched. Exits 1 if Backfill and Realtime disagree.

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

from bot import create_client
from channel_listener import ChannelListener
from client_commands import ClientCommands
from config import Config as cf
from database import Base
from models import Channel, MatchSource, PriceHistory, Product, User, UserChannel

USER_ID = 1


class PrintBot:
    async def send_message(self, user_id, text, parse_mode=None):
        print(f"\n--- notification to user {user_id} ---\n{text[:400]}\n---")


def _parse_product(spec: str) -> Product:
    name, _, target = spec.partition("=")
    return Product(user_id=USER_ID, name=name.strip(), target_price=float(target) if target else None)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--channel", action="append", required=True, help="username or numeric id (-100...)")
    parser.add_argument("--product", action="append", required=True, help="'name' or 'name=target_price'")
    parser.add_argument("--limit", type=int, default=50, help="recent messages per channel")
    parser.add_argument("--lang", default="it")
    args = parser.parse_args()

    db_path = os.path.join(tempfile.mkdtemp(), "live_check.sqlite3")
    session_factory = sessionmaker(bind=create_engine(f"sqlite:///{db_path}"))
    Base.metadata.create_all(session_factory.kw["bind"])

    client = create_client(cf.CLIENT_SESSION_NAME, cf.API_ID, cf.API_HASH, session_string=cf.CLIENT_SESSION_STRING)
    await client.connect()
    if not await client.is_user_authorized():
        print("User session not authorized: run `make auth` first")
        return 1

    entities = []
    for identifier in args.channel:
        try:
            entities.append(await client.get_entity(int(identifier)))
        except ValueError:
            entities.append(await client.get_entity(identifier))

    with session_factory() as session:
        session.add(User(user_id=USER_ID, lang_code=args.lang))
        session.flush()
        session.add_all(_parse_product(spec) for spec in args.product)
        for entity in entities:
            # Same identifier join_channel stores: username, else the bare channel id
            channel = Channel(identifier=getattr(entity, "username", None) or str(entity.id), title=entity.title)
            session.add(channel)
            session.flush()
            session.add(UserChannel(user_id=USER_ID, channel_id=channel.id))
        session.commit()

    bot = PrintBot()
    commands = ClientCommands(client, session_factory, bot)
    handlers = []
    fake_listener_client = MagicMock()
    fake_listener_client.on = lambda _event: lambda fn: handlers.append(fn) or fn
    ChannelListener(fake_listener_client, bot, session_factory).register()

    for identifier, entity in zip(args.channel, entities, strict=True):
        print(f"\n===== {entity.title} =====")
        await commands.backfill_channel(identifier, USER_ID, limit=args.limit)
        # Replay the same messages through the Realtime handler, as NewMessage events would arrive
        async for message in client.iter_messages(entity, limit=args.limit):
            event = SimpleNamespace(message=message, id=message.id, get_chat=lambda e=entity: _resolved(e))
            await handlers[0](event)
    await client.disconnect()

    with session_factory() as session:
        rows = session.query(PriceHistory.source, PriceHistory.product_id, PriceHistory.message_link, PriceHistory.price).all()
        names = dict(session.query(Product.id, Product.name))
    found = {source: {(names[p], link, price) for s, p, link, price in rows if s == source} for source in MatchSource}

    print("\n===== matches =====")
    for name, link, price in sorted(found[MatchSource.BACKFILL] | found[MatchSource.REALTIME], key=str):
        sources = [s.value for s in MatchSource if (name, link, price) in found[s]]
        print(f"{name!r:30} price={price} {link} [{', '.join(sources)}]")
    if found[MatchSource.BACKFILL] != found[MatchSource.REALTIME]:
        print("\nFAIL: Backfill and Realtime disagree on the same messages")
        return 1
    print(f"\nOK: {len(found[MatchSource.BACKFILL])} matches, Backfill and Realtime agree")
    return 0


async def _resolved(value):
    return value


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
