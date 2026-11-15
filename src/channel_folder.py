"""
Link the owner to the channels of the Channel folder (CHANNEL_FOLDER), and unlink those that leave it.
"""

import asyncio
import logging

from sqlalchemy import func
from sqlalchemy.orm import sessionmaker
from telethon import TelegramClient, events
from telethon.errors import ChannelPrivateError, RPCError
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.types import InputPeerChannel, UpdateDialogFilter, UpdateDialogFilters

from client_commands import ClientCommands
from config import Config, is_authorized
from models import Channel, User, UserChannel

log = logging.getLogger(__name__)

# DialogFilter flags that include chats by kind rather than by listing them
_RULE_FLAGS = ("contacts", "non_contacts", "groups", "broadcasts", "bots")

POLL_SECONDS = 600


class ChannelFolder:
    """Link the folder's channels to the owner (the user client's account) and unlink those that leave it."""

    def __init__(self, client: TelegramClient, client_commands: ClientCommands,
                 db_session_factory: sessionmaker, folder_name: str):
        self.client = client
        self._commands = client_commands
        self._session_factory = db_session_factory
        self._folder_name = folder_name
        self._lock = asyncio.Lock()

    def register(self):
        """Sync again whenever the account's folders change, and every POLL_SECONDS.

        Polling covers folder updates that never reach the user client (not verified that they do)
        and an owner who sends /start after startup.
        """
        self.client.on(events.Raw(types=[UpdateDialogFilter, UpdateDialogFilters]))(lambda _update: self.sync())
        # Kept on self: the event loop holds tasks only weakly
        self._poll_task = asyncio.create_task(self._poll())

    async def _poll(self):
        while True:
            await asyncio.sleep(POLL_SECONDS)
            await self.sync()

    async def sync(self):
        # A folder update during a running sync (e.g. the startup one) must not link and backfill twice
        async with self._lock:
            try:
                await self._sync()
            except RPCError as e:
                # Nothing was unlinked: a partial channel list must never pass for the whole folder
                log.error("Channel folder '%s': update failed: %s", self._folder_name, e)
            except Exception:
                # Awaited at startup: a failure here must not take the bot down
                log.exception("Channel folder '%s': update failed", self._folder_name)

    async def _sync(self):
        owner_id = (await self.client.get_me()).id
        if not is_authorized(owner_id, Config.ALLOWED_USERS, Config.ALLOW_ALL_USERS):
            log.warning("Channel folder '%s': the account owner (user_id=%s) is not in ALLOWED_USERS, "
                        "nothing synced", self._folder_name, owner_id)
            return
        with self._session_factory() as session:
            registered = session.query(User).filter_by(user_id=owner_id).first() is not None
        if not registered:
            log.warning("Channel folder '%s': the account owner (user_id=%s) has not registered: "
                        "send /start to the bot first", self._folder_name, owner_id)
            return
        result = await self.client(GetDialogFiltersRequest())
        # DialogFilterDefault ("All chats") has no title
        folder = next((f for f in result.filters
                       if getattr(f, "title", None) and f.title.text == self._folder_name), None)
        if folder is None:
            log.warning("Channel folder '%s': the account has no folder with this name, nothing changed",
                        self._folder_name)
            return

        rules = [r for r in _RULE_FLAGS if getattr(folder, r, None)]
        if rules:
            log.warning("Channel folder '%s': ignoring its rules (%s), only its listed channels count",
                        self._folder_name, ", ".join(rules))

        channels = {}
        # A chat pinned inside the folder is listed in pinned_peers instead of include_peers
        for peer in folder.pinned_peers + folder.include_peers:
            if not isinstance(peer, InputPeerChannel):
                continue
            try:
                entity = await self.client.get_entity(peer)
            except ChannelPrivateError:
                log.warning("Channel folder '%s': skipping channel %s, no longer accessible",
                            self._folder_name, peer.channel_id)
                continue
            # Same identifier join_channel() stores, so ChannelListener matches it
            channels[entity.username or str(entity.id)] = entity.title

        entered = [identifier for identifier, title in channels.items()
                   if self._commands.link_channel(owner_id, identifier, title, from_folder=True)]
        self._unlink_left(owner_id, list(channels))
        log.info("Channel folder '%s': %d channels, %d new", self._folder_name, len(channels), len(entered))
        # Sequential: a first sync of a large folder would otherwise hit FloodWait at once
        for identifier in entered:
            await self._commands.backfill_channel(identifier, owner_id)

    def _unlink_left(self, owner_id: int, identifiers: list[str]):
        """Unlink the folder's links whose channel is no longer in it; links made by hand stay."""
        with self._session_factory() as session:
            left = (
                session.query(UserChannel)
                .join(Channel, Channel.id == UserChannel.channel_id)
                .filter(UserChannel.user_id == owner_id, UserChannel.from_folder.is_(True),
                        func.lower(Channel.identifier).not_in([i.lower() for i in identifiers]))
                .all()
            )
            for link in left:
                session.delete(link)
            session.commit()
