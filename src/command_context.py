"""
The identified sender of a bot command.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandContext:
    """An identified command sender: what a flow receives once the gate lets them through."""

    user_id: int
    username: str | None
    lang: str
    first_name: str | None = None

    @property
    def display_name(self) -> str:
        """How to address the sender: many accounts have no username, deleted ones no first name."""
        return self.username or self.first_name or str(self.user_id)
