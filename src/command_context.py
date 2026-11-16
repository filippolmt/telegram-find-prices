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
