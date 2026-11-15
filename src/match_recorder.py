"""
Match a channel message against a product, record the match and notify the user.

Shared by the realtime listener and the backfill scan.
"""

import asyncio
import logging
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import NamedTuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from telethon import TelegramClient
from telethon.helpers import add_surrogate, del_surrogate
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
    # Each hidden URL goes at the end of its line, so a product's link stays in the product's paragraph.
    # Entity offsets count UTF-16 units: surrogates make the string index match them.
    text = add_surrogate(raw)
    links = sorted((e for e in message.entities or () if isinstance(e, MessageEntityTextUrl)), key=lambda e: e.offset, reverse=True)
    for entity in links:
        end = text.find("\n", entity.offset)
        end = len(text) if end < 0 else end
        text = f"{text[:end]} {entity.url}{text[end:]}"
    buttons = [
        button.type.url
        for row in getattr(message.reply_markup, "rows", ())
        for button in row.buttons
        if isinstance(button.type, InlineButtonTypeUrl)
    ]
    # URL buttons have no place in the text: their own paragraph
    return MessageText("\n\n".join([del_surrogate(text), *buttons]), raw)


def _normalize(text: str) -> str:
    """Normalize text for fuzzy matching: lowercase, remove hyphens/underscores, collapse spaces."""
    text = text.lower()
    text = re.sub(r"[-_]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def has_keywords(name: str) -> bool:
    """Whether a product name can match by text: one without letters or digits is in almost every message."""
    return re.search(r"[^\W_]", name) is not None


# A blank line, also one made only of the invisible characters channels use as spacers.
_PARAGRAPH_BREAK = re.compile(r"\n[\s\u200b-\u200d\u2060\ufeff\u3164]*\n")


def _names(marks: list[str], text: str) -> bool:
    """Whether text holds one of the product's marks: its normalized name, or its normalized links."""
    text = _normalize(text)
    return any(mark in text for mark in marks)


def _paragraph_prices(marks: list[str], paragraph: str) -> list[float]:
    """Prices of a paragraph; in a list of one product per line, those on the lines naming the product."""
    priced_lines = [(_names(marks, line), prices) for line in paragraph.split("\n") if (prices := extract_prices(line))]
    # shortcut: a list needs 3+ priced lines, so "name 75€ / offer at 60€" keeps both; a 2-item list still mixes prices
    own = [price for named, prices in priced_lines if named for price in prices] if len(priced_lines) >= 3 else []
    return own or [price for _, prices in priced_lines for price in prices]


def _product_prices(marks: list[str], text: str, priced_below: bool) -> list[float]:
    """Prices of the paragraphs naming the product, since a post can list several products each with its own price.

    When they have none and priced_below (a name: a banner, then the name, then the price), the paragraphs from
    the first one naming it on. Else the whole message: a link in its own paragraph or in a URL button, or
    variants listed under the price.
    shortcut: a product named without a price below other products' paragraphs gets their prices (#77); it reads
    the same as a variant listed under its product's price, which real channels post.
    """
    paragraphs = [(_names(marks, paragraph), _paragraph_prices(marks, paragraph)) for paragraph in _PARAGRAPH_BREAK.split(text)]
    first = next((i for i, (named, _) in enumerate(paragraphs) if named), len(paragraphs))
    return (
        [price for named, prices in paragraphs if named for price in prices]
        or [price for _, prices in paragraphs[first:] if priced_below for price in prices]
        or [price for _, prices in paragraphs for price in prices]
    )


def check_product_match(product: Product, message_text: str, asins: Mapping[str, str] = MappingProxyType({})) -> dict | None:
    """Check if a message matches a product: its keywords, or a link to its ASIN, plus the target price.

    asins maps the message's Amazon URLs to their ASINs. Returns a dict with notification info, or None if no match.
    """
    by_name = has_keywords(product.name) and _names([_normalize(product.name)], message_text)
    links = [_normalize(url) for url, asin in asins.items() if product.asin is not None and asin == product.asin]
    if not by_name and not links:
        return None

    if product.target_price is not None:
        prices = _product_prices([_normalize(product.name)] if by_name else links, message_text, priced_below=by_name)
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
        self._last_asins: tuple[str | None, dict[str, str]] = (None, {})

    async def _message_asins(self, text: str) -> dict[str, str]:
        # The caller records one message against every product in a row: parse its links once.
        if self._last_asins[0] != text:
            self._last_asins = (text, await message_asins(text))
        return self._last_asins[1]

    def _is_active(self, user_id: int) -> bool:
        with self._session_factory() as session:
            return session.query(User.id).filter_by(user_id=user_id, paused=False).first() is not None

    async def record(self, product: Product, text: MessageText, channel_name: str, message_link: str | None, source: MatchSource) -> bool:
        """Return True if the message matched the product and the match was recorded."""
        notification = _NOTIFICATIONS[source]
        result = check_product_match(product, text.match)
        if result is None and product.asin and self._is_active(product.user_id):
            # Links are resolved only for an active owner of an ASIN product: otherwise no HTTP request at all
            result = check_product_match(product, text.match, await self._message_asins(text.match))
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
