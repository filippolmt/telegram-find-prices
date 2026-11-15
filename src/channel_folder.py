"""
Keep the owner's links in sync with the channels of the Channel folder (CHANNEL_FOLDER).
"""

import asyncio
import logging

from sqlalchemy.orm import sessionmaker
from telethon import TelegramClient, events
from telethon.errors import ChannelPrivateError, RPCError
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.types import InputPeerChannel, UpdateDialogFilter, UpdateDialogFilters

from client_commands import ClientCommands
from models import Channel, User, UserChannel

log = logging.getLogger(__name__)

# DialogFilter flags that include chats by kind rather than by listing them
_RULE_FLAGS = ("contacts", "non_contacts", "groups", "broadcasts", "bots")


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
        """Sync again whenever the account's folders change."""
        self.client.on(events.Raw(types=[UpdateDialogFilter, UpdateDialogFilters]))(self._on_folders_changed)

    async def _on_folders_changed(self, _update):
        await self.sync()

    async def sync(self):
        # A folder update during a running sync (e.g. the startup one) must not link and backfill twice
        async with self._lock:
            try:
                await self._sync()
            except RPCError as e:
                # Nothing was unlinked: a partial channel list must never pass for the whole folder
                log.error("Channel folder: update failed: %s", e)
            except Exception:
                # Awaited at startup: a failure here must not take the bot down
                log.exception("Channel folder: update failed")

    async def _sync(self):
        owner_id = (await self.client.get_me()).id
        with self._session_factory() as session:
            registered = session.query(User).filter_by(user_id=owner_id).first() is not None
        if not registered:
            log.warning("CHANNEL_FOLDER: the account owner (user_id=%s) has not registered: "
                        "send /start to the bot first", owner_id)
            return
        result = await self.client(GetDialogFiltersRequest())
        # DialogFilterDefault ("All chats") has no title
        folder = next((f for f in result.filters
                       if getattr(f, "title", None) and f.title.text == self._folder_name), None)
        if folder is None:
            log.warning("CHANNEL_FOLDER: no folder named '%s', nothing synced", self._folder_name)
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

        entered = self._link(owner_id, channels)
        log.info("Channel folder '%s': %d channels, %d new", self._folder_name, len(channels), len(entered))
        # Sequential: a first sync of a large folder would otherwise hit FloodWait at once
        for identifier in entered:
            await self._commands.backfill_channel(identifier, owner_id)

    def _link(self, owner_id: int, channels: dict[str, str]) -> list[str]:
        """Link the folder's channels to the owner; return the identifiers newly linked."""
        entered = []
        with self._session_factory() as session:
            for identifier, title in channels.items():
                channel = session.query(Channel).filter_by(identifier=identifier).one_or_none()
                if channel is None:
                    channel = Channel(identifier=identifier, title=title)
                    session.add(channel)
                    session.flush()
                elif title and not channel.title:
                    channel.title = title
                if session.get(UserChannel, (owner_id, channel.id)) is None:
                    session.add(UserChannel(user_id=owner_id, channel_id=channel.id, from_folder=True))
                    entered.append(identifier)
            # Only links the folder brought in: channels added by hand stay
            left = (
                session.query(UserChannel)
                .join(Channel, Channel.id == UserChannel.channel_id)
                .filter(UserChannel.user_id == owner_id, UserChannel.from_folder.is_(True),
                        Channel.identifier.not_in(channels))
                .all()
            )
            for link in left:
                session.delete(link)
            session.commit()
        return entered
