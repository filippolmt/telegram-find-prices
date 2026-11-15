"""
The local user-client session for dev scripts (live_check.py, replay.py). One session must never run in two
processes at once: their Makefile targets pause the bot.
"""

import re
from contextlib import asynccontextmanager

from bot import create_client
from bot_commands import ChannelRef, parse_channel_ref
from config import Config as cf


@asynccontextmanager
async def user_client():
    """The connected, authorized user client; disconnected on the way out, errors included."""
    client = create_client(cf.CLIENT_SESSION_NAME, cf.API_ID, cf.API_HASH, session_string=cf.CLIENT_SESSION_STRING)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise SystemExit("User session not authorized: run `make auth` first")
        yield client
    finally:
        await client.disconnect()


async def channel_entity(client, identifier: str):
    """A channel given as a numeric id (-100…) or a username, validated before it reaches Telegram."""
    if re.fullmatch(r"-?\d+", identifier):
        return await client.get_entity(int(identifier))
    kind, username = parse_channel_ref(identifier)
    if kind is not ChannelRef.USERNAME:
        raise SystemExit(f"Invalid channel: {identifier!r}")
    return await client.get_entity(username)
