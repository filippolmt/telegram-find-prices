"""
Listen to monitored channel messages and notify users on product matches.
"""

import re
import logging
from telethon import events, TelegramClient
from sqlalchemy.orm import Session, sessionmaker

log = logging.getLogger(__name__)

from models import Product, Channel, UserChannel, User, PriceHistory
from price_parser import extract_prices
from translations import t, DEFAULT_LANGUAGE


def _normalize(text: str) -> str:
    """Normalize text for fuzzy matching: lowercase, remove hyphens/underscores, collapse spaces."""
    text = text.lower()
    text = re.sub(r"[-_]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def check_product_match(product: Product, message_text: str) -> dict | None:
    """Check if a message matches a product.

    Returns a dict with notification info, or None if no match.
    """
    text_norm = _normalize(message_text)
    product_norm = _normalize(product.name)
    if product_norm not in text_norm:
        return None

    if product.target_price is not None:
        prices = extract_prices(message_text)
        if not prices or min(prices) > product.target_price:
            return None
        return {
            "matched": True,
            "price_found": min(prices),
            "target_price": product.target_price,
        }

    return {"matched": True, "price_found": None, "target_price": None}


def _build_message_link(channel_username: str | None, channel_id: int | None, message_id: int) -> str | None:
    """Build a direct link to a channel message."""
    if channel_username:
        return f"https://t.me/{channel_username}/{message_id}"
    if channel_id:
        # For private channels: remove the -100 prefix
        clean_id = str(channel_id)
        if clean_id.startswith("-100"):
            clean_id = clean_id[4:]
        return f"https://t.me/c/{clean_id}/{message_id}"
    return None


class ChannelListener:
    """Listen to new messages in channels and check for product matches."""

    def __init__(
        self,
        client: TelegramClient,
        bot_client: TelegramClient,
        db_session_factory: sessionmaker,
    ):
        self.client = client
        self.bot_client = bot_client
        self._session_factory = db_session_factory

    def register(self):
        """Register the handler for new channel messages."""

        @self.client.on(events.NewMessage(func=lambda e: e.is_channel))
        async def on_channel_message(event):
            text = event.raw_text
            if not text:
                return

            chat = await event.get_chat()
            channel_name = getattr(chat, "title", None) or getattr(chat, "username", None) or "Unknown channel"
            channel_username = getattr(chat, "username", None)
            channel_id = getattr(chat, "id", None)
            message_id = event.id
            log.info("Message from channel '%s' (@%s): %s", channel_name, channel_username, text[:80])

            message_link = _build_message_link(channel_username, channel_id, message_id)

            with self._session_factory() as session:
                # Filter products only for users subscribed to this channel and not paused
                # Match by username or numeric channel ID
                possible_ids = []
                if channel_username:
                    possible_ids.append(channel_username)
                if channel_id:
                    possible_ids.append(str(channel_id))

                if possible_ids:
                    products = (
                        session.query(Product, User.lang_code)
                        .join(UserChannel, UserChannel.user_id == Product.user_id)
                        .join(Channel, Channel.id == UserChannel.channel_id)
                        .join(User, User.user_id == Product.user_id)
                        .filter(Channel.identifier.in_(possible_ids))
                        .filter(User.paused == False)  # noqa: E712
                        .all()
                    )
                else:
                    products = []

                for product, user_lang_code in products:
                    lang = user_lang_code or DEFAULT_LANGUAGE
                    result = check_product_match(product, text)
                    if result is None:
                        continue

                    # Save to price history
                    session.add(PriceHistory(
                        product_id=product.id,
                        user_id=product.user_id,
                        price=result["price_found"],
                        channel=channel_name,
                        message_text=text[:500],
                        message_link=message_link,
                        source="realtime",
                    ))
                    session.commit()

                    if result["price_found"] is not None:
                        price_line = t("notify_price_line", lang, price=result['price_found'], target=result['target_price'])
                    else:
                        price_line = ""

                    link_line = t("notify_link_line", lang, link=message_link) if message_link else ""

                    notification = t(
                        "notify_match", lang,
                        product=product.name, channel=channel_name,
                        price_line=price_line, text=text, link_line=link_line,
                    )
                    log.info("MATCH '%s' for user_id=%s in '%s'", product.name, product.user_id, channel_name)
                    try:
                        await self.bot_client.send_message(product.user_id, notification)
                    except Exception as e:
                        log.error("Error sending notification to %s: %s", product.user_id, e)
