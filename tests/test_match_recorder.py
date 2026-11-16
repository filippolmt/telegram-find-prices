"""
Tests for MatchRecorder: the match/record/notify path shared by realtime and backfill.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telethon.tl.custom.message import Message
from telethon.tl.types import (
    InlineButtonTypeUrl,
    KeyboardInlineButton,
    KeyboardInlineButtonRow,
    MessageEntityTextUrl,
    PeerChannel,
    ReplyInlineMarkup,
)

import match_recorder
from match_recorder import MatchRecorder, MessageLink, MessageText, message_text
from models import PriceHistory, Product, User

LINK = MessageLink("https://t.me/deals/7", private=False)


def _text(text):
    return MessageText(match=text, quote=text)


def _setup(db_session_factory, target_price=600, paused=False, name="iPhone 15", asin=None, owner_id=1):
    with db_session_factory() as session:
        session.add(User(user_id=100, paused=paused, lang_code="en"))
        session.flush()
        product = Product(user_id=100, name=name, target_price=target_price, asin=asin)
        session.add(product)
        session.commit()
        session.refresh(product)
        session.expunge(product)
    bot_client = MagicMock()
    bot_client.send_message = AsyncMock()
    user_client = MagicMock()
    user_client.get_me = AsyncMock(return_value=SimpleNamespace(user_id=owner_id))
    return MatchRecorder(bot_client, db_session_factory, user_client), product, bot_client


def _history(db_session_factory):
    with db_session_factory() as session:
        return [(h.source, h.price, h.channel, h.message_link) for h in session.query(PriceHistory)]


@pytest.mark.parametrize("source", ["realtime", "backfill"])
async def test_price_under_target_is_recorded_and_notified(db_session_factory, source):
    recorder, product, bot_client = _setup(db_session_factory)

    assert await recorder.record(product, _text("iPhone 15 a 499€"), "Deals", LINK, source) is True

    assert _history(db_session_factory) == [(source, 499, "Deals", LINK.url)]
    bot_client.send_message.assert_awaited_once()
    user_id, text = bot_client.send_message.await_args.args
    assert user_id == 100
    assert "499.00" in text and "600.00" in text and LINK.url in text


@pytest.mark.parametrize("source", ["realtime", "backfill"])
async def test_price_over_target_is_ignored(db_session_factory, source):
    recorder, product, bot_client = _setup(db_session_factory)

    assert await recorder.record(product, _text("iPhone 15 a 799€"), "Deals", LINK, source) is False

    assert _history(db_session_factory) == []
    bot_client.send_message.assert_not_awaited()


@pytest.mark.parametrize("source", ["realtime", "backfill"])
async def test_no_target_records_match_without_price(db_session_factory, source):
    recorder, product, bot_client = _setup(db_session_factory, target_price=None)

    assert await recorder.record(product, _text("iPhone 15 disponibile a 999€"), "Deals", LINK, source) is True

    assert _history(db_session_factory) == [(source, None, "Deals", LINK.url)]
    bot_client.send_message.assert_awaited_once()


@pytest.mark.parametrize("source", ["realtime", "backfill"])
async def test_paused_user_is_recorded_but_not_notified(db_session_factory, source):
    recorder, product, bot_client = _setup(db_session_factory, paused=True)

    assert await recorder.record(product, _text("iPhone 15 a 499€"), "Deals", LINK, source) is True

    assert _history(db_session_factory) == [(source, 499, "Deals", LINK.url)]
    bot_client.send_message.assert_not_awaited()


async def test_notification_text_depends_on_source(db_session_factory):
    recorder, product, bot_client = _setup(db_session_factory)
    long_text = "iPhone 15 a 499€ " + "x" * 400

    await recorder.record(product, _text(long_text), "Deals", LINK, "realtime")
    await recorder.record(product, _text(long_text), "Deals", LINK, "backfill")

    realtime, backfill = (call.args[1] for call in bot_client.send_message.await_args_list)
    assert not realtime.startswith("[Backfill]") and long_text in realtime
    assert backfill.startswith("[Backfill]") and long_text[:300] in backfill and long_text[:301] not in backfill


async def test_without_bot_client_match_is_recorded(db_session_factory):
    _, product, _ = _setup(db_session_factory)

    assert await MatchRecorder(None, db_session_factory, MagicMock()).record(product, _text("iPhone 15 a 499€"), "Deals", LINK, "backfill") is True

    assert _history(db_session_factory) == [("backfill", 499, "Deals", LINK.url)]


async def test_product_unwatched_before_recording_is_skipped(db_session_factory):
    recorder, product, bot_client = _setup(db_session_factory)
    with db_session_factory() as session:
        session.query(Product).delete()
        session.commit()

    assert await recorder.record(product, _text("iPhone 15 a 499€"), "Deals", LINK, "realtime") is False

    assert _history(db_session_factory) == []
    bot_client.send_message.assert_not_awaited()


async def test_quote_is_sent_without_parse_mode(db_session_factory):
    recorder, product, bot_client = _setup(db_session_factory)
    quote = "iPhone 15 a 499€ *solo oggi* __codice_SCONTO__ [link](https://x.y)"

    await recorder.record(product, _text(quote), "Deals", LINK, "realtime")

    assert quote in bot_client.send_message.await_args.args[1]
    assert bot_client.send_message.await_args.kwargs == {"parse_mode": None}


ASIN = "B0CXYZ1234"
SHORT = "https://amzn.to/3abc"


@pytest.fixture
def links(http):
    """Short links of the posts below; returns the URLs requested."""
    redirects, requested = http
    redirects[SHORT] = f"https://www.amazon.it/dp/{ASIN}?tag=aff-21"
    redirects["https://amzn.to/other"] = "https://www.amazon.it/dp/B0OTHER001"
    return requested


@pytest.mark.parametrize(
    "post, matched",
    [
        (f"Spazzolino a 19€ {SHORT}", True),  # ASIN via short link, keywords absent
        ("Oral-B Pro 3 a 19€ https://www.amazon.it/dp/B0OTHER001", True),  # keywords, ASIN different
        (f"Spazzolino a 29€ {SHORT}", False),  # ASIN, price over target
        ("Oral-B Pro 3 a 29€", False),  # keywords, price over target
        ("Spazzolino a 19€ https://amzn.to/other", False),  # neither
    ],
)
async def test_match_by_asin_or_keywords(db_session_factory, links, post, matched):
    recorder, product, _ = _setup(db_session_factory, target_price=20, name="oral-b pro 3", asin=ASIN)

    assert await recorder.record(product, _text(post), "Deals", LINK, "realtime") is matched


async def test_no_resolution_for_product_without_asin(db_session_factory, links):
    recorder, product, _ = _setup(db_session_factory)

    assert await recorder.record(product, _text(f"Offerta a 19€ {SHORT}"), "Deals", LINK, "realtime") is False
    assert links == []


async def test_no_resolution_for_paused_user(db_session_factory, links):
    recorder, product, _ = _setup(db_session_factory, paused=True, name="oral-b pro 3", asin=ASIN)

    assert await recorder.record(product, _text(f"Offerta a 19€ {SHORT}"), "Deals", LINK, "realtime") is False
    assert links == []


async def test_links_resolved_once_per_message_for_several_asin_products(db_session_factory, links, monkeypatch):
    recorder, first, _ = _setup(db_session_factory, target_price=None, name="oral-b pro 3", asin=ASIN)
    with db_session_factory() as session:
        second = Product(user_id=100, name="kindle", asin="B0OTHER001")
        session.add(second)
        session.commit()
        session.refresh(second)
        session.expunge(second)
    parsed = []
    real = match_recorder.message_asin_by_url
    monkeypatch.setattr(match_recorder, "message_asin_by_url", lambda text: parsed.append(text) or real(text))
    text = _text(f"Offerta {SHORT}")

    assert await recorder.record(first, text, "Deals", LINK, "realtime") is True
    assert await recorder.record(second, text, "Deals", LINK, "realtime") is False
    assert len(parsed) == 1


def _post(text, entities=(), buttons=()):
    return Message(
        id=7, peer_id=PeerChannel(123), message=text, entities=list(entities),
        reply_markup=ReplyInlineMarkup([KeyboardInlineButtonRow([KeyboardInlineButton("Compra", InlineButtonTypeUrl(url)) for url in buttons])]) if buttons else None,
    )


async def _offer_line(db_session_factory, post, name="iPhone 15"):
    recorder, product, bot_client = _setup(db_session_factory, name=name)

    assert await recorder.record(product, message_text(post), "Deals", LINK, "realtime") is True

    lines = [line for line in bot_client.send_message.await_args.args[1].split("\n") if line.startswith("Offer:")]
    return lines


async def test_offer_link_is_the_link_in_the_products_paragraph(db_session_factory):
    post = _post("🔥 Offerte\n\nAirPods 99€ https://amzn.eu/d/airpods\n\niPhone 15 499€\nhttps://amzn.eu/d/iphone")

    assert await _offer_line(db_session_factory, post) == ["Offer: https://amzn.eu/d/iphone"]


async def test_offer_link_is_a_hidden_link(db_session_factory):
    text = "AirPods 99€\n\n🔥 iPhone 15 499€\n👉 Vai all'offerta"
    # Telegram offsets count UTF-16 units: the emoji before the link text counts two
    post = _post(text, [MessageEntityTextUrl(offset=text.index("Vai") + 2, length=14, url="https://amzn.eu/d/iphone")])

    assert await _offer_line(db_session_factory, post) == ["Offer: https://amzn.eu/d/iphone"]


async def test_offer_link_is_a_url_button(db_session_factory):
    post = _post("iPhone 15 a 499€", buttons=["https://amzn.eu/d/iphone"])

    assert await _offer_line(db_session_factory, post) == ["Offer: https://amzn.eu/d/iphone"]


async def test_post_without_urls_has_no_offer_link(db_session_factory):
    assert await _offer_line(db_session_factory, _post("iPhone 15 a 499€")) == []


PRIVATE_LINK = MessageLink("https://t.me/c/123/7", private=True)


@pytest.mark.parametrize("owner_id, shown", [(100, True), (200, False)])
async def test_private_post_link_is_shown_only_to_the_owner(db_session_factory, owner_id, shown):
    recorder, product, bot_client = _setup(db_session_factory, owner_id=owner_id)

    assert await recorder.record(product, _text("iPhone 15 a 499€"), "Deals", PRIVATE_LINK, "realtime") is True

    assert (PRIVATE_LINK.url in bot_client.send_message.await_args.args[1]) is shown


@pytest.mark.parametrize(
    "text, links",
    [
        # Link preview: an image behind an invisible character (RisparmiareSulWeb, pallok, CouponsItalia)
        ("\u2063iPhone 15\n\n🌐 https://amzlink.to/iphone\n\n💰 699€ 👉 499€", [(0, 1, "https://i.ibb.co/x/image.jpg")]),
        # A disclaimer page before the offer link, both outside the price's paragraph
        ("iPhone 15\n\n💰 499 € invece di 699 €\n\n🛒 #AMAZON - Disclaimer\n\n👉🏻 VAI ALL'OFFERTA",
         [(50, 10, "https://telegra.ph/Disclaimer-prodotti"), (67, 15, "https://amzlink.to/iphone")]),
    ],
)
async def test_images_and_telegram_pages_are_no_offer_link(db_session_factory, text, links):
    post = _post(text, [MessageEntityTextUrl(offset=o, length=n, url=u) for o, n, u in links])

    assert await _offer_line(db_session_factory, post) == ["Offer: https://amzlink.to/iphone"]


async def test_offer_link_in_a_one_per_line_list_is_on_the_products_line(db_session_factory):
    post = _post("Offerte PlayStation\n• DualSense 59,99€ https://link.amazon/dualsense\n• iPhone 15 499€ https://link.amazon/iphone")

    assert await _offer_line(db_session_factory, post) == ["Offer: https://link.amazon/iphone"]


async def test_offer_link_of_a_variant_is_on_its_line(db_session_factory):
    post = _post("Yankee Candle Giara Grande\n💰Passa da 34,99 a 19,94€\n👉 Bahama Breeze https://amzn.eu/d/bahama\n👉 French Vanilla https://amzn.eu/d/vanilla")

    assert await _offer_line(db_session_factory, post, name="French Vanilla") == ["Offer: https://amzn.eu/d/vanilla"]


async def test_offer_link_of_a_link_match_is_the_link_to_the_product(db_session_factory, links):
    recorder, product, bot_client = _setup(db_session_factory, target_price=None, name="oral-b pro 3", asin=ASIN)
    post = _post(f"Kindle 99€ https://amzn.to/other\n\nSpazzolino in offerta\n{SHORT}")

    assert await recorder.record(product, message_text(post), "Deals", LINK, "realtime") is True

    assert f"Offer: {SHORT}" in bot_client.send_message.await_args.args[1]


async def test_owner_lookup_failure_still_notifies_without_the_private_link(db_session_factory):
    _, product, bot_client = _setup(db_session_factory)
    user_client = MagicMock()
    user_client.get_me = AsyncMock(side_effect=ConnectionError("down"))
    recorder = MatchRecorder(bot_client, db_session_factory, user_client)

    assert await recorder.record(product, _text("iPhone 15 a 499€"), "Deals", PRIVATE_LINK, "realtime") is True

    assert PRIVATE_LINK.url not in bot_client.send_message.await_args.args[1]


async def test_public_post_link_is_shown_to_every_user(db_session_factory):
    recorder, product, bot_client = _setup(db_session_factory, owner_id=200)

    assert await recorder.record(product, _text("iPhone 15 a 499€"), "Deals", LINK, "realtime") is True

    assert LINK.url in bot_client.send_message.await_args.args[1]
