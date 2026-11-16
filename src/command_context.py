"""
The identified sender of a bot command.
"""

from dataclasses import dataclass

from translations import resolve_lang


@dataclass(frozen=True)
class CommandContext:
    """An identified command sender: what a flow receives once the gate lets them through."""

    user_id: int
    username: str | None
    lang: str
    first_name: str | None = None

    @classmethod
    def from_sender(cls, user_id: int, tg_sender) -> "CommandContext":
        """The context of a Telegram sender (User entity; missing fields read as None)."""
        return cls(user_id, getattr(tg_sender, "username", None), resolve_lang(getattr(tg_sender, "lang_code", None)),
                   getattr(tg_sender, "first_name", None))

    @property
    def display_name(self) -> str:
        """How to address the sender: many accounts have no username, deleted ones no first name."""
        return self.username or self.first_name or str(self.user_id)
