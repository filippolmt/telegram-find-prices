"""
Match a channel message against a product, record the match and notify the user.

Shared by the realtime listener and the backfill scan.
"""

import asyncio
import logging
import re
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import NamedTuple
from urllib.parse import urlsplit

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from telethon import TelegramClient
from telethon.helpers import add_surrogate, del_surrogate
from telethon.tl.custom.message import Message
from telethon.tl.types import InlineButtonTypeUrl, MessageEntityTextUrl

from amazon import message_asin_by_url, urls_in_text
from models import MatchSource, PriceHistory, Product, User
from price_parser import extract_prices, is_price_only
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
_PARAGRAPH_BREAK = re.compile(r"\n[\s\u115f\u1160\u200b-\u200d\u2060\u2800\u3164\ufeff\uffa0]*\n")


# A URL, also one typed without its scheme ("t.me/…", "www.x.it/…"): its slug or encoded text holds no price (#57).
_URL = re.compile(r"(?:https?://|\b(?:[a-z0-9-]+\.)+[a-z]{2,}/)\S*", re.IGNORECASE)


def _without_urls(text: str) -> str:
    return _URL.sub(" ", text)


def _flat(groups) -> list[float]:
    return [price for group in groups for price in group]


def _paragraph_prices(mentions: Callable[[str], bool], paragraph: str) -> list[float]:
    """Prices of a paragraph; in a list of one product per line, those on the lines naming the product.

    A list has two or more lines each naming a product with its price ("TCL 79€ / BOSE 161€"); lines that
    only quote a price ("📉 In offerta a 39€") belong to the product named above them.
    """
    # Prices are read without URLs: a slug or an encoded share text ("euro%20") is no price (#57)
    lines = [(line, _without_urls(line)) for line in paragraph.split("\n")]
    priced = [(line, no_urls, prices) for line, no_urls in lines if (prices := extract_prices(no_urls))]
    items = [(line, prices) for line, no_urls, prices in priced if not is_price_only(no_urls)]
    own = _flat(prices for line, prices in items if mentions(line)) if len(items) >= 2 else []
    return own or _flat(prices for _, _, prices in priced)


class _Paragraph(NamedTuple):
    text: str
    named: bool  # names or links to the product
    prices: list[float]  # the product's, see _paragraph_prices


def _priced_paragraphs(mentions: Callable[[str], bool], text: str, priced_below: bool) -> list[_Paragraph]:
    """Paragraphs naming the product that quote prices, since a post can list several products each with its own price.

    When they have none and priced_below (a name: a banner, then the name, then the price), the paragraphs from
    the first one naming it on. Else the whole message: a link in its own paragraph or in a URL button, or
    variants listed under the price.
    shortcut: a product named without a price below other products' paragraphs gets their prices (#77), as it
    reads the same as a variant listed under its product's price; revisit if channels start posting it.
    """
    paragraphs = [_Paragraph(p, mentions(p), _paragraph_prices(mentions, p)) for p in _PARAGRAPH_BREAK.split(text)]
    first = next((i for i, p in enumerate(paragraphs) if p.named), len(paragraphs))
    return (
        [p for p in paragraphs if p.named and p.prices]
        or ([p for p in paragraphs[first:] if p.prices] if priced_below else [])
        or [p for p in paragraphs if p.prices]
    )


def _offer_urls(text: str) -> list[str]:
    """URLs of text that can be the offer link: images (link previews, price charts) and Telegram's own pages
    (disclaimers, channel promos) never are.

    shortcut: a denylist, so an image host without a file extension or another disclaimer service passes as the
    offer link; after a make dump-posts, tally the offer link hosts of the matches and add any non-offer host found here.
    """
    return [
        url for url, parts in ((url, urlsplit(url)) for url in urls_in_text(text))
        if (parts.hostname or "").lower() not in {"t.me", "telegra.ph"}
        and not parts.path.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))
    ]


def _offer_url(mentions: Callable[[str], bool], paragraph: str, text: str) -> str | None:
    """The first offer URL from the paragraph's first line naming the product on (its line in a one-per-line list,
    or the link under its name), else in the paragraph, else in the post."""
    lines = paragraph.split("\n")
    first = next((i for i, line in enumerate(lines) if mentions(line)), 0)
    return next(iter(_offer_urls("\n".join(lines[first:])) or _offer_urls(paragraph) or _offer_urls(text)), None)


def check_product_match(product: Product, message_text: str, asin_by_url: Mapping[str, str] = MappingProxyType({})) -> dict | None:
    """Check if a message matches a product: its keywords, or a link to its ASIN, plus the target price.

    asin_by_url maps the message's Amazon URLs to their ASINs. Returns a dict with notification info, or None if no match.
    """
    name = _normalize(product.name) if has_keywords(product.name) else None
    links = {url for url, asin in asin_by_url.items() if product.asin is not None and asin == product.asin}

    def names(part: str) -> bool:
        # message_text puts hidden links at line ends: also look past one splitting a name that wraps
        return name in _normalize(part) or name in _normalize(_without_urls(part))

    def links_to(part: str) -> bool:
        return not links.isdisjoint(urls_in_text(part))

    by_name = name is not None and names(message_text)
    if not by_name and not links:
        return None

    mentions = names if by_name else links_to
    paragraph = min(_priced_paragraphs(mentions, message_text, priced_below=by_name), key=lambda p: min(p.prices), default=None)
    price = min(paragraph.prices) if paragraph else None
    if by_name:
        offer_url = _offer_url(mentions, paragraph.text if paragraph else message_text, message_text)
    else:
        offer_url = next((url for url in urls_in_text(message_text) if url in links), None)
    if product.target_price is not None:
        if price is None or price > product.target_price:
            return None
        return {"matched": True, "price_found": price, "target_price": product.target_price, "offer_url": offer_url}

    return {"matched": True, "price_found": None, "target_price": None, "offer_url": offer_url}


class MessageLink(NamedTuple):
    url: str
    private: bool  # a channel without a username: the link opens only for its members


def build_message_link(channel_username: str | None, channel_id: int | None, message_id: int) -> MessageLink | None:
    """Build a direct link to a channel message."""
    if channel_username:
        return MessageLink(f"https://t.me/{channel_username}/{message_id}", private=False)
    if channel_id:
        # For private channels: remove the -100 prefix
        clean_id = str(channel_id)
        if clean_id.startswith("-100"):
            clean_id = clean_id[4:]
        return MessageLink(f"https://t.me/c/{clean_id}/{message_id}", private=True)
    return None


class MatchRecorder:
    """Decide whether a message matches a product, record it in PriceHistory and notify the owner."""

    def __init__(self, bot_client: TelegramClient | None, db_session_factory: sessionmaker, user_client: TelegramClient):
        self.bot_client = bot_client
        self.user_client = user_client  # its account is the owner's
        self._session_factory = db_session_factory
        self._last_asin_by_url: tuple[str | None, dict[str, str]] = (None, {})

    async def _message_asin_by_url(self, text: str) -> dict[str, str]:
        # The caller records one message against every product in a row: parse its links once.
        if self._last_asin_by_url[0] != text:
            self._last_asin_by_url = (text, await message_asin_by_url(text))
        return self._last_asin_by_url[1]

    def _is_active(self, user_id: int) -> bool:
        with self._session_factory() as session:
            return session.query(User.id).filter_by(user_id=user_id, paused=False).first() is not None

    async def _can_open(self, user_id: int, message_link: MessageLink | None) -> bool:
        """Whether the user can open the post link: a private channel's opens only for its members, the owner."""
        if message_link is None:
            return False
        if not message_link.private:
            return True
        try:
            # input_peer: Telethon caches it, no request per notification
            return (await self.user_client.get_me(input_peer=True)).user_id == user_id
        except Exception as e:
            log.error("Owner lookup failed, private post link not sent to %s: %s", user_id, e)
            return False

    async def record(self, product: Product, text: MessageText, channel_name: str, message_link: MessageLink | None, source: MatchSource) -> bool:
        """Return True if the message matched the product and the match was recorded."""
        notification = _NOTIFICATIONS[source]
        result = check_product_match(product, text.match)
        if result is None and product.asin and self._is_active(product.user_id):
            # Links are resolved only for an active owner of an ASIN product: otherwise no HTTP request at all
            result = check_product_match(product, text.match, await self._message_asin_by_url(text.match))
        if result is None:
            return False

        with self._session_factory() as session:
            session.add(PriceHistory(
                product_id=product.id,
                user_id=product.user_id,
                price=result["price_found"],
                channel=channel_name,
                message_text=text.quote[:500],
                message_link=message_link and message_link.url,
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
        offer_line = t("notify_offer_line", lang, url=result["offer_url"]) if result["offer_url"] else ""
        link_line = t("notify_link_line", lang, link=message_link.url) if await self._can_open(product.user_id, message_link) else ""
        message = t(
            notification.match_key, lang,
            product=product.name, channel=channel_name,
            price_line=price_line, text=text.quote[:notification.text_limit], offer_line=offer_line, link_line=link_line,
        )
        try:
            # No parse mode: the quoted post may contain * and _, and a cut quote must not leave an entity open.
            await self.bot_client.send_message(product.user_id, message, parse_mode=None)
            if notification.pause:
                await asyncio.sleep(notification.pause)
        except Exception as e:
            log.error("Error sending %s notification to %s: %s", source, product.user_id, e)
        return True
