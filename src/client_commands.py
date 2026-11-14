"""
Telegram user client commands (join/leave channels, backfill).
"""

import logging

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


class ClientCommands:
    """Telegram user client operations (channel management, backfill)."""

    def __init__(self, client: TelegramClient, db_session_factory: sessionmaker, bot_client: TelegramClient = None):
        self.client = client
        self._session_factory = db_session_factory
        self._recorder = MatchRecorder(bot_client, db_session_factory)

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
                except Exception:
                    pass
        except RPCError as e:
            target = channel_identifier or f"invite {invite_hash[:4]}…"
            log.error("JoinChannel error for '%s': %s", target, e)
            return False, t("join_channel_failed", lang), ""

        with self._session_factory() as session:
            channel_db = session.query(Channel).filter_by(
                identifier=db_identifier).one_or_none()
            if channel_db is None:
                channel_db = Channel(identifier=db_identifier, title=channel_title)
                session.add(channel_db)
                session.flush()
            elif channel_title and not channel_db.title:
                channel_db.title = channel_title

            link_exists = (
                session.query(UserChannel)
                .filter_by(user_id=user_id, channel_id=channel_db.id)
                .first()
            )
            if link_exists is None:
                session.add(UserChannel(user_id=user_id, channel_id=channel_db.id))

            session.commit()

        return True, t("join_channel_success", lang, channel=display_name), db_identifier

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

            async for message in self.client.iter_messages(entity, limit=limit):
                text = message_text(message)
                if not text.match:
                    continue
                message_link = build_message_link(channel_username, channel_id, message.id)
                for product in products:
                    if await self._recorder.record(product, text, channel_name, message_link, MatchSource.BACKFILL):
                        matches_found += 1

        except FloodWaitError as e:
            log.warning("FloodWait during backfill: waiting %ds", e.seconds)
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
