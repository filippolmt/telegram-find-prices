"""
Telegram user client commands (join/leave channels, backfill).
"""

import logging
from telethon import TelegramClient

log = logging.getLogger(__name__)
from telethon.tl.functions.channels import LeaveChannelRequest, JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from telethon.errors import RPCError, FloodWaitError, UserAlreadyParticipantError
from sqlalchemy.orm import Session, sessionmaker
from models import UserChannel, Channel, Product, PriceHistory, User
from channel_listener import check_product_match
from translations import t, DEFAULT_LANGUAGE


class ClientCommands:
    """Telegram user client operations (channel management, backfill)."""

    def __init__(self, client: TelegramClient, db_session_factory: sessionmaker, bot_client: TelegramClient = None):
        self.client = client
        self._session_factory = db_session_factory
        self.bot_client = bot_client

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
            log.error("JoinChannel error for '%s': %s", channel_identifier or invite_hash, e)
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
        import asyncio

        with self._session_factory() as session:
            products = session.query(Product).filter_by(user_id=user_id).all()
            if not products:
                return 0
            product_data = [{"id": p.id, "name": p.name, "target_price": p.target_price, "user_id": p.user_id} for p in products]
            user = session.query(User).filter_by(user_id=user_id).first()
            user_lang = user.lang_code if user else DEFAULT_LANGUAGE

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
                if not message.text:
                    continue

                for pd in product_data:
                    # Create a Product-like object for check_product_match
                    class _FakeProduct:
                        pass
                    fp = _FakeProduct()
                    fp.name = pd["name"]
                    fp.target_price = pd["target_price"]

                    result = check_product_match(fp, message.text)
                    if result is None:
                        continue

                    # Build message link
                    msg_link = None
                    if channel_username:
                        msg_link = f"https://t.me/{channel_username}/{message.id}"
                    elif channel_id:
                        clean_id = str(channel_id)
                        if clean_id.startswith("-100"):
                            clean_id = clean_id[4:]
                        msg_link = f"https://t.me/c/{clean_id}/{message.id}"

                    with self._session_factory() as session:
                        session.add(PriceHistory(
                            product_id=pd["id"],
                            user_id=pd["user_id"],
                            price=result["price_found"],
                            channel=channel_name,
                            message_text=message.text[:500],
                            message_link=msg_link,
                            source="backfill",
                        ))
                        session.commit()

                    matches_found += 1

                    # Notify via bot
                    if self.bot_client:
                        if result["price_found"] is not None:
                            price_line = t("notify_backfill_price_line", user_lang, price=result['price_found'], target=result['target_price'])
                        else:
                            price_line = ""
                        link_line = f"\n\n {msg_link}" if msg_link else ""
                        notification = t(
                            "notify_backfill_match", user_lang,
                            product=pd['name'], channel=channel_name,
                            price_line=price_line, text=message.text[:300], link_line=link_line,
                        )
                        try:
                            await self.bot_client.send_message(pd["user_id"], notification)
                            await asyncio.sleep(0.5)  # Rate limit
                        except Exception as e:
                            log.error("Error sending backfill notification: %s", e)

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
