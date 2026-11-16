"""
Shared test fixtures.
"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add src/ to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from database import Base  # noqa: E402


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite engine for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def fresh_engine(monkeypatch):
    """An empty in-memory SQLite engine standing in for database.engine, for migration tests to shape by hand.

    Disposed even when the test fails: an engine left open warns at garbage collection, and filterwarnings=error
    turns that into a failure of whichever later test is running.
    """
    import database

    engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(database, "engine", engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session_factory(db_engine):
    """Return a sessionmaker (same pattern as production)."""
    return sessionmaker(bind=db_engine)


@pytest.fixture
def db_session(db_session_factory):
    """Create a single session for tests that need it directly."""
    with db_session_factory() as session:
        yield session


@pytest.fixture
def http(monkeypatch):
    """Fake redirect table for amazon._location (no network); returns (redirects, requested URLs)."""
    import amazon

    redirects: dict[str, str | None] = {}
    requested: list[str] = []

    def fake_location(url):
        requested.append(url)
        return redirects.get(url)

    monkeypatch.setattr(amazon, "_location", fake_location)
    monkeypatch.setattr(amazon, "_cache", {})
    return redirects, requested


@pytest.fixture(autouse=True)
def every_user_allowed(monkeypatch):
    """Tests run with every user authorized, whatever the local .env says; a test narrows it with monkeypatch."""
    from config import Config

    monkeypatch.setattr(Config, "ALLOWED_USERS", [])
    monkeypatch.setattr(Config, "ALLOW_ALL_USERS", True)
