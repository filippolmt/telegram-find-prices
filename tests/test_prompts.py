"""
Tests for the conversation prompts, against an in-memory conversation.
"""

import pytest

from bot_commands import CommandContext
from prompts import Prompt
from tests.fakes import conversation_event
from translations import t

CTX = CommandContext(1, "owner", "en")


async def test_text_returns_stripped_answer_after_prompt():
    event = conversation_event(["  hello  "])

    assert await Prompt(event, CTX, "/cmd").text("question?") == "hello"
    assert event.replies == ["question?"]


@pytest.mark.parametrize("keyword", ["/cancel", "Cancel", "annulla", "/annulla"])
async def test_text_cancel_keyword_returns_none_and_says_cancelled(keyword):
    event = conversation_event([keyword])

    assert await Prompt(event, CTX, "/cmd").text("question?") is None
    assert event.replies == ["question?", t("operation_cancelled", "en")]


async def test_text_timeout_returns_none_and_names_command():
    event = conversation_event([TimeoutError()])

    assert await Prompt(event, CTX, "/cmd").text("question?") is None
    assert event.replies == ["question?", t("timed_out", "en", command="/cmd")]


async def test_pick_returns_chosen_item():
    event = conversation_event([" 2 "])

    assert await Prompt(event, CTX, "/cmd").pick("which?", ["a", "b", "c"]) == "b"
    assert event.replies == ["which?"]


@pytest.mark.parametrize(
    ("answer", "reply"),
    [
        ("two", t("invalid_choice", "en", command="/cmd")),
        ("0", t("number_out_of_range", "en", command="/cmd")),
        ("4", t("number_out_of_range", "en", command="/cmd")),
        ("-1", t("number_out_of_range", "en", command="/cmd")),
        ("annulla", t("operation_cancelled", "en")),
        (TimeoutError(), t("timed_out", "en", command="/cmd")),
    ],
)
async def test_pick_rejects_answer_and_says_why(answer, reply):
    event = conversation_event([answer])

    assert await Prompt(event, CTX, "/cmd").pick("which?", ["a", "b", "c"]) is None
    assert event.replies == ["which?", reply]


async def test_prompt_is_in_the_user_language():
    event = conversation_event(["annulla"])

    await Prompt(event, CommandContext(1, "owner", "it"), "/cmd").text("domanda?")
    assert event.replies[-1] == t("operation_cancelled", "it")
