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


@pytest.fixture
def db_session_factory(db_engine):
    """Return a sessionmaker (same pattern as production)."""
    return sessionmaker(bind=db_engine)


@pytest.fixture
def db_session(db_session_factory):
    """Create a single session for tests that need it directly."""
    with db_session_factory() as session:
        yield session
