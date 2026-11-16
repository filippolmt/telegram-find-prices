"""
The Channel folder (CHANNEL_FOLDER): it holds exactly the monitored channels.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from telethon import TelegramClient, events
from telethon.errors import ChannelPrivateError, RPCError
from telethon.tl.functions.messages import (
    GetDialogFiltersRequest,
    UpdateDialogFilterRequest,
)
from telethon.tl.types import (
    DialogFilter,
    InputPeerChannel,
    UpdateDialogFilter,
    UpdateDialogFilters,
)

from client_commands import ClientCommands, peer_key

log = logging.getLogger(__name__)

# DialogFilter flags that include chats by kind rather than by listing them
_RULE_FLAGS = ("contacts", "non_contacts", "groups", "broadcasts", "bots")

POLL_SECONDS = 600


class FolderMissingError(Exception):
    """The account has no folder with the configured name."""


class ChannelFolder:
    """Keep the monitored channels equal to the folder's channels."""

    def __init__(self, client: TelegramClient, client_commands: ClientCommands, folder_name: str):
        self.client = client
        self._commands = client_commands
        # Awaited with the channels a sync found new in the folder
        self.on_entered: Callable[[list[str]], Awaitable[None]] | None = None
        self.folder_name = folder_name
        self._lock = asyncio.Lock()

    def register(self):
        """Read the folder again whenever the account's folders change, and every POLL_SECONDS.

        Polling covers folder updates that never reach the user client (not verified that they do).
        """
        self.client.on(events.Raw(types=[UpdateDialogFilter, UpdateDialogFilters]))(lambda _update: self.sync())
        # Kept on self: the event loop holds tasks only weakly
        self._poll_task = asyncio.create_task(self._poll())

    async def _poll(self):
        while True:
            await asyncio.sleep(POLL_SECONDS)
            await self.sync()

    async def sync(self) -> int | None:
        """Read the folder and update the monitored channels; return its channel count, None if it was not read."""
        # A folder update while the folder is being read (e.g. at startup) must not backfill a channel twice
        async with self._lock:
            try:
                return await self._sync()
            except RPCError as e:
                # Nothing was removed: a partial channel list must never pass for the whole folder
                log.error("Channel folder '%s': update failed: %s", self.folder_name, e)
            except Exception:
                # Awaited at startup: a failure here must not take the bot down
                log.exception("Channel folder '%s': update failed", self.folder_name)

    async def add(self, identifier: str, title: str | None) -> bool:
        """Put a channel the account has joined into the folder and monitor it; return whether it was not monitored.

        Raises FolderMissingError or RPCError (e.g. the folder is full), and then nothing changed.
        """
        async with self._lock:
            await self._write(identifier, include=True)
            return self._commands.monitor(identifier, title)

    async def remove(self, identifier: str) -> bool:
        """Take a channel out of the folder and stop monitoring it; return whether it was monitored. Raises as add()."""
        async with self._lock:
            await self._write(identifier, include=False)
            return self._commands.unmonitor(identifier)

    async def _write(self, identifier: str, include: bool) -> None:
        folder = await self._read()
        if folder is None:
            raise FolderMissingError(self.folder_name)
        peer = await self.client.get_input_entity(peer_key(identifier))

        def others(peers):
            # Peers that are not this channel, bots and groups included, go back unchanged
            return [p for p in peers if not (isinstance(p, InputPeerChannel) and p.channel_id == peer.channel_id)]

        listed = len(others(folder.pinned_peers + folder.include_peers)) < len(folder.pinned_peers + folder.include_peers)
        if listed == include:
            return
        folder.pinned_peers = others(folder.pinned_peers)
        folder.include_peers = others(folder.include_peers) + ([peer] if include else [])
        # The request replaces the whole folder: everything else is sent back as read
        await self.client(UpdateDialogFilterRequest(id=folder.id, filter=folder))

    async def _sync(self) -> int | None:
        folder = await self._read()
        if folder is None:
            return None

        rules = [r for r in _RULE_FLAGS if getattr(folder, r, None)]
        if rules:
            log.warning("Channel folder '%s': ignoring its rules (%s), only its listed channels count",
                        self.folder_name, ", ".join(rules))

        channels = {}
        # A chat pinned inside the folder is listed in pinned_peers instead of include_peers
        for peer in folder.pinned_peers + folder.include_peers:
            if not isinstance(peer, InputPeerChannel):
                continue
            try:
                entity = await self.client.get_entity(peer)
            except ChannelPrivateError:
                log.warning("Channel folder '%s': skipping channel %s, no longer accessible",
                            self.folder_name, peer.channel_id)
                continue
            # Same identifier join_channel() stores, so ChannelListener matches it
            channels[entity.username or str(entity.id)] = entity.title

        entered = [identifier for identifier, title in channels.items() if self._commands.monitor(identifier, title)]
        # The account stays in a channel taken out of the folder by hand: only the bot's removals leave
        self._commands.monitor_exactly(list(channels))
        log.info("Channel folder '%s': %d channels, %d new", self.folder_name, len(channels), len(entered))
        if entered and self.on_entered:
            await self.on_entered(entered)
        # Sequential: a large folder read for the first time would otherwise hit FloodWait at once
        for identifier in entered:
            await self._commands.backfill_channel(identifier)
        return len(channels)

    async def _read(self) -> DialogFilter | None:
        """The folder as Telegram holds it, None (logged) if the account has none with this name."""
        result = await self.client(GetDialogFiltersRequest())
        # DialogFilterDefault ("All chats") has no title
        folder = next((f for f in result.filters
                       if getattr(f, "title", None) and f.title.text == self.folder_name), None)
        if folder is None:
            log.warning("Channel folder '%s': the account has no folder with this name, nothing changed",
                        self.folder_name)
        return folder
