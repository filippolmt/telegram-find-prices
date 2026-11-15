"""
Conversation prompts: ask a command sender for free text or for one item of a numbered list.
"""

from typing import TYPE_CHECKING, TypeVar

from telethon import events

from translations import t

if TYPE_CHECKING:
    from bot_commands import CommandContext

_CANCEL_KEYWORDS = {"/cancel", "cancel", "/annulla", "annulla"}
_TIMEOUT_SECONDS = 60

T = TypeVar("T")


class Prompt:
    """The questions of one command. Each returns the answer, or None after telling the user why there is none."""

    def __init__(self, event: events.NewMessage.Event, ctx: "CommandContext", command: str):
        self._event = event
        self._ctx = ctx
        self._command = command

    async def _retry_with_command(self, key: str) -> None:
        await self._event.respond(t(key, self._ctx.lang, command=self._command))

    async def text(self, prompt: str) -> str | None:
        """Send `prompt` and return the stripped reply; None on timeout or a cancel keyword."""
        await self._event.respond(prompt)
        try:
            async with self._event.client.conversation(self._event.chat_id, timeout=_TIMEOUT_SECONDS) as conv:
                response = await conv.wait_event(events.NewMessage(from_users=self._ctx.user_id))
        except TimeoutError:
            await self._retry_with_command("timed_out")
            return None
        answer = (response.raw_text or "").strip()
        if answer.lower() in _CANCEL_KEYWORDS:
            await self._event.respond(t("operation_cancelled", self._ctx.lang))
            return None
        return answer

    async def pick(self, prompt: str, items: list[T]) -> T | None:
        """Send `prompt` (listing `items` numbered from 1) and return the chosen item."""
        answer = await self.text(prompt)
        if answer is None:
            return None
        try:
            index = int(answer) - 1
        except ValueError:
            await self._retry_with_command("invalid_choice")
            return None
        if not 0 <= index < len(items):
            await self._retry_with_command("number_out_of_range")
            return None
        return items[index]
