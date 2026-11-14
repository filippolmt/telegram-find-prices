"""
Tests for the /watch conversation, through the registered command and an in-memory conversation.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from models import Product
from tests.fakes import chat_event, registered_bot
from translations import t


def _watch_event(answers):
    event = chat_event(1, "owner")
    event.chat_id = 1
    answers = iter(answers)

    async def wait_event(_builder):
        return SimpleNamespace(raw_text=next(answers))

    async def send_message(text):
        event.replies.append(text)

    @asynccontextmanager
    async def conversation(_chat_id, timeout):
        yield SimpleNamespace(wait_event=wait_event, send_message=send_message)

    event.client = SimpleNamespace(conversation=conversation)
    return event


@pytest.mark.parametrize("answer", ["", "  ", "-", "."])
async def test_watch_rejects_product_name_without_keywords(monkeypatch, db_session_factory, answer):
    bot = registered_bot(monkeypatch, db_session_factory)
    event = _watch_event([answer])

    await bot.bot_client.dispatch("/watch", event)

    assert event.replies == [t("watch_ask_product", "en"), t("watch_name_no_keywords", "en")]
    with db_session_factory() as session:
        assert session.query(Product).count() == 0


async def test_watch_link_with_keywords_without_letters_matches_by_link_only(monkeypatch, db_session_factory):
    bot = registered_bot(monkeypatch, db_session_factory)
    event = _watch_event(["https://www.amazon.it/dp/B0TEST1234", "-", "/skip", "/skip"])

    await bot.bot_client.dispatch("/watch", event)

    with db_session_factory() as session:
        product = session.query(Product).one()
        assert (product.name, product.asin) == ("b0test1234", "B0TEST1234")
