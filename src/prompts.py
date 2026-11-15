"""
Conversation prompts: ask a command sender for free text or for one item of a numbered list.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypeVar

from telethon import events
from telethon.tl.custom import Conversation

from command_context import CommandContext
from translations import t

# Reply keywords, in every supported language
CANCEL_KEYWORDS = {"/cancel", "cancel", "/annulla", "annulla"}
SKIP_KEYWORDS = {"/skip", "skip", "/salta", "salta"}
YES_KEYWORDS = {"si", "sì", "yes", "ok"}
NO_KEYWORDS = {"no"}

_TIMEOUT_SECONDS = 60

T = TypeVar("T")


@asynccontextmanager
async def conversation(event: events.NewMessage.Event, ctx: CommandContext, command: str) -> AsyncIterator["Prompt"]:
    """Hold one exclusive conversation in the command's chat for all its questions."""
    async with event.client.conversation(event.chat_id, timeout=_TIMEOUT_SECONDS) as conv:
        yield Prompt(conv, event, ctx, command)


class Prompt:
    """The questions of one command. Each returns the answer, or None after telling the user why there is none."""

    def __init__(self, conv: Conversation, event: events.NewMessage.Event, ctx: CommandContext, command: str):
        self._conv = conv
        self._event = event
        self._ctx = ctx
        self._command = command

    async def _say_with_command(self, key: str) -> None:
        await self._event.respond(t(key, self._ctx.lang, command=self._command))

    async def text(self, prompt_key: str, given: str = "", **fields) -> str | None:
        """Ask with the `prompt_key` template and return the stripped reply; None on timeout or a cancel keyword.

        A non-empty `given` (the text typed after the command) is the reply, without asking.
        """
        if given:
            answer = given.strip()
        else:
            await self._event.respond(t(prompt_key, self._ctx.lang, **fields))
            try:
                response = await self._conv.wait_event(events.NewMessage(from_users=self._ctx.user_id))
            except TimeoutError:
                await self._say_with_command("timed_out")
                return None
            answer = (response.raw_text or "").strip()
        if answer.lower() in CANCEL_KEYWORDS:
            await self._event.respond(t("operation_cancelled", self._ctx.lang))
            return None
        return answer

    async def pick(self, prompt_key: str, choices: list[tuple[str, T]]) -> T | None:
        """Ask with the `prompt_key` template, its {items} the labels numbered from 1; return the chosen value."""
        listing = "\n".join(f"{i}. {label}" for i, (label, _) in enumerate(choices, 1))
        answer = await self.text(prompt_key, items=listing)
        if answer is None:
            return None
        try:
            index = int(answer) - 1
        except ValueError:
            await self._say_with_command("invalid_choice")
            return None
        if not 0 <= index < len(choices):
            await self._say_with_command("number_out_of_range")
            return None
        return choices[index][1]
