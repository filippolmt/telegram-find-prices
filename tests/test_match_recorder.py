"""
Tests for MatchRecorder: the match/record/notify path shared by realtime and backfill.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import match_recorder
from match_recorder import MatchRecorder, MessageText
from models import PriceHistory, Product, User

LINK = "https://t.me/deals/7"


def _text(text):
    return MessageText(match=text, quote=text)


def _setup(db_session_factory, target_price=600, paused=False, name="iPhone 15", asin=None):
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
    return MatchRecorder(bot_client, db_session_factory), product, bot_client


def _history(db_session_factory):
    with db_session_factory() as session:
        return [(h.source, h.price, h.channel, h.message_link) for h in session.query(PriceHistory)]


@pytest.mark.parametrize("source", ["realtime", "backfill"])
async def test_price_under_target_is_recorded_and_notified(db_session_factory, source):
    recorder, product, bot_client = _setup(db_session_factory)

    assert await recorder.record(product, _text("iPhone 15 a 499€"), "Deals", LINK, source) is True

    assert _history(db_session_factory) == [(source, 499, "Deals", LINK)]
    bot_client.send_message.assert_awaited_once()
    user_id, text = bot_client.send_message.await_args.args
    assert user_id == 100
    assert "499.00" in text and "600.00" in text and LINK in text


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

    assert _history(db_session_factory) == [(source, None, "Deals", LINK)]
    bot_client.send_message.assert_awaited_once()


@pytest.mark.parametrize("source", ["realtime", "backfill"])
async def test_paused_user_is_recorded_but_not_notified(db_session_factory, source):
    recorder, product, bot_client = _setup(db_session_factory, paused=True)

    assert await recorder.record(product, _text("iPhone 15 a 499€"), "Deals", LINK, source) is True

    assert _history(db_session_factory) == [(source, 499, "Deals", LINK)]
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

    assert await MatchRecorder(None, db_session_factory).record(product, _text("iPhone 15 a 499€"), "Deals", LINK, "backfill") is True

    assert _history(db_session_factory) == [("backfill", 499, "Deals", LINK)]


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
    real = match_recorder.message_asins
    monkeypatch.setattr(match_recorder, "message_asins", lambda text: parsed.append(text) or real(text))
    text = _text(f"Offerta {SHORT}")

    assert await recorder.record(first, text, "Deals", LINK, "realtime") is True
    assert await recorder.record(second, text, "Deals", LINK, "realtime") is False
    assert len(parsed) == 1
