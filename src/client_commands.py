"""
Telegram user client commands (join/leave channels, backfill).
"""

import asyncio
import logging

from sqlalchemy import func
from sqlalchemy.orm import sessionmaker
from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError, UserAlreadyParticipantError
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import (
    CheckChatInviteRequest,
    ImportChatInviteRequest,
)

from config import Config
from match_recorder import (
    MatchRecorder,
    authorized_products,
    build_message_link,
    message_text,
)
from models import Channel, MatchSource, channel_label

log = logging.getLogger(__name__)

BACKFILL_FLOOD_RETRIES = 3


def peer_key(identifier: str) -> str | int:
    """What Telethon resolves a Channel.identifier by: a username, or a private channel's bare numeric id."""
    return int(identifier) if identifier.isdigit() else identifier


class ClientCommands:
    """Telegram user client operations (channel management, backfill)."""

    def __init__(self, client: TelegramClient, db_session_factory: sessionmaker, bot_client: TelegramClient = None):
        self.client = client
        self._session_factory = db_session_factory
        self._recorder = MatchRecorder(bot_client, db_session_factory, client)

    async def owner_id(self) -> int | None:
        """The owner: the account of the user client, when listed in ALLOWED_USERS (ALLOW_ALL_USERS is not enough).

        None, nobody, if it is not or the account cannot be read.
        """
        try:
            owner = (await self.client.get_me()).id
        except Exception as e:
            log.error("Owner lookup failed, nobody is owner: %s", e)
            return None
        return owner if owner in Config.ALLOWED_USERS else None

    def list_channels(self) -> list[str]:
        """Labels of the monitored channels: 'title (identifier)', or the identifier alone."""
        with self._session_factory() as session:
            return [channel_label(c.identifier, c.title) for c in session.query(Channel).order_by(Channel.id)]

    async def join_channel(self, channel_identifier: str, invite_hash: str = None) -> tuple[str, str | None] | None:
        """Join a channel (by username or invite hash) without monitoring it.

        Returns (identifier as Channel.identifier stores it, title), None if Telegram refused.
        """
        db_identifier = channel_identifier
        channel_title = None

        try:
            if invite_hash:
                try:
                    updates = await self.client(ImportChatInviteRequest(invite_hash))
                    chat = updates.chats[0]
                except UserAlreadyParticipantError:
                    result = await self.client(CheckChatInviteRequest(invite_hash))
                    chat = result.chat

                db_identifier = getattr(chat, "username", None) or str(chat.id)
                channel_title = getattr(chat, "title", None)
            else:
                await self.client(JoinChannelRequest(channel_identifier))
                try:
                    entity = await self.client.get_entity(channel_identifier)
                    channel_title = getattr(entity, "title", None)
                    # Telegram's spelling, not the user's: the listener compares it with chat.username
                    db_identifier = getattr(entity, "username", None) or db_identifier
                except Exception:
                    pass
        except RPCError as e:
            target = channel_identifier or f"invite {invite_hash[:4]}…"
            log.error("JoinChannel error for '%s': %s", target, e)
            return None
        return db_identifier, channel_title

    async def check_invite(self, invite_hash: str) -> tuple[str | None, str | None] | None:
        """The channel behind an invite, without joining it: (identifier if the account is in it, title).

        None if Telegram refused the invite (invalid, expired).
        """
        try:
            result = await self.client(CheckChatInviteRequest(invite_hash))
        except RPCError as e:
            log.error("CheckChatInvite error for invite %s…: %s", invite_hash[:4], e)
            return None
        chat = getattr(result, "chat", None)
        if chat is None:
            return None, getattr(result, "title", None)
        return getattr(chat, "username", None) or str(chat.id), getattr(chat, "title", None)

    def find_channel(self, identifier: str) -> Channel | None:
        """The monitored channel with this identifier, detached."""
        with self._session_factory() as session:
            channel = self._find(session, identifier)
            if channel:
                session.expunge(channel)
            return channel

    @staticmethod
    def _find(session, identifier: str) -> Channel | None:
        # Usernames are case-insensitive on Telegram
        return (
            session.query(Channel)
            .filter(func.lower(Channel.identifier) == identifier.lower())
            .order_by(Channel.id)  # rows saved before this check may differ only in case: take the oldest
            .first()
        )

    def monitor(self, identifier: str, title: str | None) -> bool:
        """Make a channel monitored; return whether it was not already."""
        with self._session_factory() as session:
            channel = self._find(session, identifier)
            if channel is None:
                session.add(Channel(identifier=identifier, title=title))
            elif title and not channel.title:
                channel.title = title
            session.commit()
            return channel is None

    def unmonitor(self, identifier: str) -> bool:
        """Stop monitoring a channel, the account stays in it; return whether it was monitored."""
        with self._session_factory() as session:
            deleted = session.query(Channel).filter(func.lower(Channel.identifier) == identifier.lower()).delete()
            session.commit()
            return deleted > 0

    def monitor_exactly(self, identifiers: list[str]) -> None:
        """Stop monitoring every channel but these."""
        with self._session_factory() as session:
            session.query(Channel).filter(
                func.lower(Channel.identifier).not_in([i.lower() for i in identifiers])
            ).delete(synchronize_session=False)
            session.commit()

    async def backfill_channel(self, channel_identifier: str, limit: int = 200) -> int:
        """Scan the last N messages of a channel for every authorized user's products.

        Returns the number of matches found.
        """
        with self._session_factory() as session:
            products = authorized_products(session)
            # Detached so the recorder can read them after this session closes.
            session.expunge_all()
        if not products:
            return 0

        matches_found = 0
        try:
            # Resolve entity: numeric ID or username
            try:
                entity = await self.client.get_entity(int(channel_identifier))
            except (ValueError, TypeError):
                entity = await self.client.get_entity(channel_identifier)
            channel_name = getattr(entity, "title", channel_identifier)
            channel_username = getattr(entity, "username", None)
            channel_id = getattr(entity, "id", None)

            remaining, offset_id, flood_waits = limit, 0, 0
            while remaining > 0:
                try:
                    # offset_id: resume below the last message read before a FloodWait
                    async for message in self.client.iter_messages(entity, limit=remaining, offset_id=offset_id):
                        remaining -= 1
                        offset_id = message.id
                        text = message_text(message)
                        if not text.match:
                            continue
                        message_link = build_message_link(channel_username, channel_id, message.id)
                        for product in products:
                            if await self._recorder.record(product, text, channel_name, message_link,
                                                           MatchSource.BACKFILL):
                                matches_found += 1
                    break
                except FloodWaitError as e:
                    flood_waits += 1
                    log.warning("FloodWait during backfill of '%s' (%d/%d): waiting %ds",
                                channel_identifier, flood_waits, BACKFILL_FLOOD_RETRIES, e.seconds)
                    await asyncio.sleep(e.seconds)
                    if flood_waits == BACKFILL_FLOOD_RETRIES:
                        # A partial backfill beats holding the Channel folder's lock indefinitely
                        log.warning("Backfill of '%s' stopped after %d FloodWaits",
                                    channel_identifier, flood_waits)
                        break

        except FloodWaitError as e:
            # Resolving the channel failed; waiting keeps the next sequential backfill (Channel folder) from hitting it
            log.warning("FloodWait during backfill of '%s': waiting %ds", channel_identifier, e.seconds)
            await asyncio.sleep(e.seconds)
        except RPCError as e:
            log.error("Backfill error for channel '%s': %s", channel_identifier, e)

        log.info("Backfill '%s': %d matches", channel_identifier, matches_found)
        return matches_found

    async def leave_channel(self, channel_identifier: str) -> bool:
        """Make the account leave a channel; False (logged) if Telegram refused."""
        try:
            await self.client(LeaveChannelRequest(peer_key(channel_identifier)))
            return True
        except RPCError as e:
            log.error("LeaveChannel error for '%s': %s", channel_identifier, e)
            return False
