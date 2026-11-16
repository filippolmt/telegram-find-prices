"""
Listen to monitored channel messages and notify users on product matches.
"""

import logging

from sqlalchemy.orm import sessionmaker
from telethon import TelegramClient, events

from match_recorder import (
    MatchRecorder,
    authorized_products,
    build_message_link,
    message_text,
)
from models import Channel, MatchSource, identifier_in

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
                # Match by username or numeric channel ID; usernames are case-insensitive, older rows hold them as typed
                possible_ids = [i.lower() for i in (channel_username, channel_id and str(channel_id)) if i]
                monitored = possible_ids and session.query(Channel.id).filter(
                    identifier_in(Channel.identifier, possible_ids)).first() is not None
                # The recorder skips notifying paused users
                products = authorized_products(session) if monitored else []
                # Detached so the recorder can read them after this session closes.
                session.expunge_all()

            for product in products:
                await self._recorder.record(product, text, channel_name, message_link, MatchSource.REALTIME)
