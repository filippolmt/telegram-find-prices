"""
Tests for the conversation prompts, against an in-memory conversation.
"""

import pytest

from command_context import CommandContext
from prompts import conversation
from tests.fakes import conversation_event
from translations import t

CTX = CommandContext(1, "owner", "en")
CHOICES = [("first", "a"), ("second", "b"), ("third", "c")]


async def _text(event, ctx=CTX):
    async with conversation(event, ctx, "/cmd") as ask:
        return await ask.text("question?")


async def _pick(event):
    async with conversation(event, CTX, "/unwatch") as ask:
        return await ask.pick("unwatch_prompt", CHOICES)


async def test_text_returns_stripped_answer_after_prompt():
    event = conversation_event(["  hello  "])

    assert await _text(event) == "hello"
    assert event.replies == ["question?"]


@pytest.mark.parametrize("keyword", ["/cancel", "Cancel", "annulla", "/annulla"])
async def test_text_cancel_keyword_returns_none_and_says_cancelled(keyword):
    event = conversation_event([keyword])

    assert await _text(event) is None
    assert event.replies == ["question?", t("operation_cancelled", "en")]


async def test_text_timeout_returns_none_and_names_command():
    event = conversation_event([TimeoutError()])

    assert await _text(event) is None
    assert event.replies == ["question?", t("timed_out", "en", command="/cmd")]


async def test_questions_share_one_conversation():
    event = conversation_event(["one", "two"])

    async with conversation(event, CTX, "/cmd") as ask:
        assert [await ask.text("q1"), await ask.text("q2")] == ["one", "two"]
    assert event.conversations == 1


async def test_pick_lists_labels_numbered_from_one_and_returns_chosen_value():
    event = conversation_event([" 2 "])

    assert await _pick(event) == "b"
    assert event.replies == [t("unwatch_prompt", "en", items="1. first\n2. second\n3. third")]


@pytest.mark.parametrize(
    ("answer", "reply"),
    [
        ("two", t("invalid_choice", "en", command="/unwatch")),
        ("0", t("number_out_of_range", "en", command="/unwatch")),
        ("4", t("number_out_of_range", "en", command="/unwatch")),
        ("-1", t("number_out_of_range", "en", command="/unwatch")),
        ("annulla", t("operation_cancelled", "en")),
        (TimeoutError(), t("timed_out", "en", command="/unwatch")),
    ],
)
async def test_pick_rejects_answer_and_says_why(answer, reply):
    event = conversation_event([answer])

    assert await _pick(event) is None
    assert event.replies[1:] == [reply]


async def test_prompt_is_in_the_user_language():
    event = conversation_event(["annulla"])

    await _text(event, CommandContext(1, "owner", "it"))
    assert event.replies[-1] == t("operation_cancelled", "it")
