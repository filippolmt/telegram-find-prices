"""
Listen to monitored channel messages and notify users on product matches.
"""

import logging

from sqlalchemy import func
from sqlalchemy.orm import sessionmaker
from telethon import TelegramClient, events

from match_recorder import MatchRecorder, build_message_link, message_text
from models import Channel, MatchSource, Product, UserChannel

log = logging.getLogger(__name__)


class ChannelListener:
    """Listen to new messages in channels and check for product matches."""

    def __init__(
        self,
        client: TelegramClient,
        bot_client: TelegramClient,
        db_session_factory: sessionmaker,
    ):
        self.client = client
        self._session_factory = db_session_factory
        self._recorder = MatchRecorder(bot_client, db_session_factory, client)

    def register(self):
        """Register the handler for new channel messages."""

        @self.client.on(events.NewMessage(func=lambda e: e.is_channel))
        async def on_channel_message(event):
            text = message_text(event.message)
            if not text.match:
                return

            chat = await event.get_chat()
            channel_name = getattr(chat, "title", None) or getattr(chat, "username", None) or "Unknown channel"
            channel_username = getattr(chat, "username", None)
            channel_id = getattr(chat, "id", None)
            message_id = event.id
            log.info("Message from channel '%s' (@%s): %s", channel_name, channel_username, text.quote[:80])

            message_link = build_message_link(channel_username, channel_id, message_id)

            with self._session_factory() as session:
                # Products of users subscribed to this channel; the recorder skips notifying paused users
                # Match by username or numeric channel ID
                possible_ids = []
                if channel_username:
                    possible_ids.append(channel_username)
                if channel_id:
                    possible_ids.append(str(channel_id))

                if possible_ids:
                    products = (
                        session.query(Product)
                        .join(UserChannel, UserChannel.user_id == Product.user_id)
                        .join(Channel, Channel.id == UserChannel.channel_id)
                        # Usernames are case-insensitive; older rows hold them as the user typed them
                        .filter(func.lower(Channel.identifier).in_([i.lower() for i in possible_ids]))
                        .order_by(Product.id)
                        .all()
                    )
                else:
                    products = []
                # Detached so the recorder can read them after this session closes.
                session.expunge_all()

            for product in products:
                await self._recorder.record(product, text, channel_name, message_link, MatchSource.REALTIME)
