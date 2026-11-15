"""
Database models (SQLAlchemy ORM).
"""

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
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


class UserChannel(Base):
    """User-channel association (many-to-many)."""
    __tablename__ = "user_channels"

    user_id = Column(Integer, ForeignKey(
        "users.user_id", ondelete="CASCADE"), primary_key=True)
    channel_id = Column(Integer, ForeignKey(
        "channels.id", ondelete="CASCADE"), primary_key=True)
    # Linked by the Channel folder sync, which may unlink it; False once the user adds it by hand
    from_folder = Column(Boolean, nullable=False, default=False, server_default="0")


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
