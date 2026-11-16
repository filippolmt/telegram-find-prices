"""
Database models (SQLAlchemy ORM).
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import NamedTuple

from sqlalchemy import (
    Boolean,
    Column,
    ColumnElement,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)

from database import Base


class User(Base):
    """Registered bot user."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String)
    paused = Column(Boolean, nullable=False, default=False)
    lang_code = Column(String, nullable=False, default="en")
    added_at = Column(String, nullable=False,
                      default=lambda: datetime.now(timezone.utc).isoformat())


class Channel(Base):
    """Monitored Telegram channel."""
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    identifier = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=True)
    added_at = Column(String, nullable=False,
                      default=lambda: datetime.now(timezone.utc).isoformat())


def identifier_in(column, identifiers: list[str]) -> ColumnElement[bool]:
    """SQL condition: the column holds one of these channel identifiers. Usernames are case-insensitive on
    Telegram, and older rows hold them as the user typed them."""
    return func.lower(column).in_([i.lower() for i in identifiers])


def channel_label(identifier: str, title: str | None) -> str:
    """How a channel is shown to users: 'title (identifier)', or the identifier alone."""
    return f"{title} ({identifier})" if title else identifier


class ChannelInfo(NamedTuple):
    """A channel as Channel.identifier stores it, and its title; identifier None for an invite to a channel the
    account is not in."""
    identifier: str | None
    title: str | None

    @property
    def label(self) -> str:
        return channel_label(self.identifier, self.title)


class ChannelRequest(Base):
    """A pending Channel request: decided ones are deleted, invite hash included."""
    __tablename__ = "channel_requests"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String, nullable=False)  # ChannelRequestAction
    # Username or numeric id as Channel.identifier stores it; None for an invite to a channel the account is not in
    identifier = Column(String, nullable=True)
    invite_hash = Column(String, nullable=True)
    title = Column(String, nullable=True)
    added_at = Column(String, nullable=False,
                      default=lambda: datetime.now(timezone.utc).isoformat())


class ChannelRequestAction(StrEnum):
    ADD = "add"
    REMOVE = "remove"


class ChannelRequester(Base):
    """A user waiting for a Channel request: the first one filed it, the others joined it."""
    __tablename__ = "channel_requesters"

    request_id = Column(Integer, ForeignKey(
        "channel_requests.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Integer, ForeignKey(
        "users.user_id", ondelete="CASCADE"), primary_key=True)


class Product(Base):
    """Product monitored by a user."""
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_product"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey(
        "users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    target_price = Column(Float, nullable=True)
    category = Column(String, nullable=True)
    asin = Column(String, nullable=True)  # Amazon product: a post linking to it matches even without the keywords
    added_at = Column(String, nullable=False,
                      default=lambda: datetime.now(timezone.utc).isoformat())


class MatchSource(StrEnum):
    """Where a match was found (stored in PriceHistory.source)."""
    REALTIME = "realtime"
    BACKFILL = "backfill"


class PriceHistory(Base):
    """Price history entries found in channels."""
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey(
        "products.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey(
        "users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    price = Column(Float, nullable=True)
    channel = Column(String, nullable=False)
    message_text = Column(String, nullable=False)
    message_link = Column(String, nullable=True)
    source = Column(String, nullable=False, default=MatchSource.REALTIME)
    found_at = Column(String, nullable=False,
                      default=lambda: datetime.now(timezone.utc).isoformat())
