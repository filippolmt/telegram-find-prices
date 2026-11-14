"""
Match a channel message against a product, record the match and notify the user.

Shared by the realtime listener and the backfill scan.
"""

import asyncio
import logging
import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from telethon import TelegramClient

from models import PriceHistory, Product, User
from price_parser import extract_prices
from translations import DEFAULT_LANGUAGE, t

log = logging.getLogger(__name__)

# source -> (notification key, price line key, max quoted text length, pause after each notification)
_SOURCES = {
    "realtime": ("notify_match", "notify_price_line", None, 0),
    "backfill": ("notify_backfill_match", "notify_backfill_price_line", 300, 0.5),
}


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

    async def record(self, product: Product, text: str, channel_name: str, message_link: str | None, source: str) -> bool:
        """Return True if the message matched the product and the match was recorded."""
        match_key, price_key, text_limit, pause = _SOURCES[source]
        result = check_product_match(product, text)
        if result is None:
            return False

        with self._session_factory() as session:
            session.add(PriceHistory(
                product_id=product.id,
                user_id=product.user_id,
                price=result["price_found"],
                channel=channel_name,
                message_text=text[:500],
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

        price_line = t(price_key, lang, price=result["price_found"], target=result["target_price"]) if result["price_found"] is not None else ""
        link_line = t("notify_link_line", lang, link=message_link) if message_link else ""
        notification = t(
            match_key, lang,
            product=product.name, channel=channel_name,
            price_line=price_line, text=text[:text_limit], link_line=link_line,
        )
        try:
            await self.bot_client.send_message(product.user_id, notification)
            await asyncio.sleep(pause)
        except Exception as e:
            log.error("Error sending %s notification to %s: %s", source, product.user_id, e)
        return True
