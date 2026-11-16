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

from match_recorder import MatchRecorder, build_message_link, message_text
from models import Channel, MatchSource, Product, UserChannel
from translations import DEFAULT_LANGUAGE, t

log = logging.getLogger(__name__)

BACKFILL_FLOOD_RETRIES = 3


class ClientCommands:
    """Telegram user client operations (channel management, backfill)."""

    def __init__(self, client: TelegramClient, db_session_factory: sessionmaker, bot_client: TelegramClient = None):
        self.client = client
        self._session_factory = db_session_factory
        self._recorder = MatchRecorder(bot_client, db_session_factory, client)

    async def list_channels(self, user_id: int) -> list[str]:
        """Return the list of channels associated with the given user."""
        with self._session_factory() as session:
            user_channels = (
                session.query(Channel.identifier, Channel.title)
                .join(UserChannel, UserChannel.channel_id == Channel.id)
                .filter(UserChannel.user_id == user_id)
                .all()
            )
            result = []
            for ch in user_channels:
                if ch.title:
                    result.append(f"{ch.title} ({ch.identifier})")
                else:
                    result.append(ch.identifier)
            return result

    async def join_channel(self, channel_identifier: str, user_id: int, invite_hash: str = None, lang: str = DEFAULT_LANGUAGE) -> tuple[bool, str, str]:
        """Join a channel (by username or invite hash).

        Returns (success, status_message, db_identifier).
        """
        db_identifier = channel_identifier
        display_name = channel_identifier
        channel_title = None

        try:
            if invite_hash:
                try:
                    updates = await self.client(ImportChatInviteRequest(invite_hash))
                    chat = updates.chats[0]
                except UserAlreadyParticipantError:
                    result = await self.client(CheckChatInviteRequest(invite_hash))
                    chat = result.chat

                db_identifier = str(chat.id)
                channel_title = getattr(chat, "title", None)
                display_name = channel_title or f"Channel {db_identifier}"
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
            return False, t("join_channel_failed", lang), ""

        self.link_channel(user_id, db_identifier, channel_title)

        return True, t("join_channel_success", lang, channel=display_name), db_identifier

    def link_channel(self, user_id: int, identifier: str, title: str | None, from_folder: bool = False) -> bool:
        """Link a channel to the user, creating it if unknown; return whether the link is new.

        A link made by hand (from_folder=False) is never unlinked by the Channel folder, even if the folder made it.
        """
        with self._session_factory() as session:
            # Usernames are case-insensitive on Telegram
            channel = (
                session.query(Channel)
                .filter(func.lower(Channel.identifier) == identifier.lower())
                .order_by(Channel.id)  # rows saved before this check may differ only in case: take the oldest
                .first()
            )
            if channel is None:
                channel = Channel(identifier=identifier, title=title)
                session.add(channel)
                session.flush()
            elif title and not channel.title:
                channel.title = title

            link = session.get(UserChannel, (user_id, channel.id))
            if link is None:
                session.add(UserChannel(user_id=user_id, channel_id=channel.id, from_folder=from_folder))
            elif not from_folder:
                link.from_folder = False
            session.commit()
            return link is None

    async def backfill_channel(self, channel_identifier: str, user_id: int, limit: int = 200) -> int:
        """Scan the last N messages of a channel for product matches.

        Returns the number of matches found.
        """
        with self._session_factory() as session:
            products = session.query(Product).filter_by(user_id=user_id).all()
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

        log.info("Backfill '%s' for user_id=%s: %d matches", channel_identifier, user_id, matches_found)
        return matches_found

    async def leave_channel(self, channel_identifier: str, lang: str = DEFAULT_LANGUAGE) -> str:
        """Leave a channel."""
        try:
            await self.client(LeaveChannelRequest(channel_identifier))
            return t("leave_channel_success", lang, channel=channel_identifier)
        except RPCError as e:
            log.error("LeaveChannel error for '%s': %s", channel_identifier, e)
            return t("leave_channel_failed", lang)
