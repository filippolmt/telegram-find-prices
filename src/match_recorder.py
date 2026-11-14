"""
Match a channel message against a product, record the match and notify the user.

Shared by the realtime listener and the backfill scan.
"""

import asyncio
import logging
import re
from typing import NamedTuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from telethon import TelegramClient
from telethon.tl.custom.message import Message
from telethon.tl.types import InlineButtonTypeUrl, MessageEntityTextUrl

from amazon import message_asins
from models import MatchSource, PriceHistory, Product, User
from price_parser import extract_prices
from translations import DEFAULT_LANGUAGE, t

log = logging.getLogger(__name__)

class _Notification(NamedTuple):
    match_key: str
    price_key: str
    text_limit: int | None  # max quoted message length
    pause: float  # seconds to wait after sending, to stay under the bot rate limit


_NOTIFICATIONS = {
    MatchSource.REALTIME: _Notification("notify_match", "notify_price_line", None, 0),
    MatchSource.BACKFILL: _Notification("notify_backfill_match", "notify_backfill_price_line", 300, 0.5),
}


class MessageText(NamedTuple):
    match: str  # matching and price extraction: plain text plus the URLs it hides
    quote: str  # notification and PriceHistory: plain text


def message_text(message: Message) -> MessageText:
    """Build the match and quote text of a channel message, the same for Backfill and Realtime."""
    raw = message.raw_text or ""
    urls = [e.url for e in message.entities or () if isinstance(e, MessageEntityTextUrl)]
    urls += [
        button.type.url
        for row in getattr(message.reply_markup, "rows", ())
        for button in row.buttons
        if isinstance(button.type, InlineButtonTypeUrl)
    ]
    return MessageText("\n".join([raw, *urls]), raw)


def _normalize(text: str) -> str:
    """Normalize text for fuzzy matching: lowercase, remove hyphens/underscores, collapse spaces."""
    text = text.lower()
    text = re.sub(r"[-_]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def check_product_match(product: Product, message_text: str, asins: set[str] = frozenset()) -> dict | None:
    """Check if a message matches a product: its keywords, or a link to its ASIN, plus the target price.

    Returns a dict with notification info, or None if no match.
    """
    linked = product.asin is not None and product.asin in asins
    if not linked and _normalize(product.name) not in _normalize(message_text):
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


def build_message_link(channel_username: str | None, channel_id: int | None, message_id: int) -> str | None:
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


class MatchRecorder:
    """Decide whether a message matches a product, record it in PriceHistory and notify the owner."""

    def __init__(self, bot_client: TelegramClient | None, db_session_factory: sessionmaker):
        self.bot_client = bot_client
        self._session_factory = db_session_factory

    def _is_active(self, user_id: int) -> bool:
        with self._session_factory() as session:
            return session.query(User.id).filter_by(user_id=user_id, paused=False).first() is not None

    async def record(self, product: Product, text: MessageText, channel_name: str, message_link: str | None, source: MatchSource) -> bool:
        """Return True if the message matched the product and the match was recorded."""
        notification = _NOTIFICATIONS[source]
        result = check_product_match(product, text.match)
        if result is None and product.asin and self._is_active(product.user_id):
            # Links are resolved only for an active owner of an ASIN product: otherwise no HTTP request at all
            result = check_product_match(product, text.match, await message_asins(text.match))
        if result is None:
            return False

        with self._session_factory() as session:
            session.add(PriceHistory(
                product_id=product.id,
                user_id=product.user_id,
                price=result["price_found"],
                channel=channel_name,
                message_text=text.quote[:500],
                message_link=message_link,
                source=source,
            ))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                log.info("%s match for product id=%s not saved (integrity error, likely unwatched), skipped", source, product.id)
                return False
            # Read per match, so a /pause sent during a backfill is honoured from the next match on.
            user = session.query(User).filter_by(user_id=product.user_id).one_or_none()
            lang = (user and user.lang_code) or DEFAULT_LANGUAGE
            # A user deleted right after the commit gets no notification.
            notify = user is not None and not user.paused

        log.info("MATCH (%s) '%s' for user_id=%s in '%s'", source, product.name, product.user_id, channel_name)
        if not notify or self.bot_client is None:
            return True

        price_line = t(notification.price_key, lang, price=result["price_found"], target=result["target_price"]) if result["price_found"] is not None else ""
        link_line = t("notify_link_line", lang, link=message_link) if message_link else ""
        message = t(
            notification.match_key, lang,
            product=product.name, channel=channel_name,
            price_line=price_line, text=text.quote[:notification.text_limit], link_line=link_line,
        )
        try:
            # No parse mode: the quoted post may contain * and _, and a cut quote must not leave an entity open.
            await self.bot_client.send_message(product.user_id, message, parse_mode=None)
            if notification.pause:
                await asyncio.sleep(notification.pause)
        except Exception as e:
            log.error("Error sending %s notification to %s: %s", source, product.user_id, e)
        return True
