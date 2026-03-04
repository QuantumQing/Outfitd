"""Shared test fixtures and configuration."""

import os
import sys
import pytest
import tempfile

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Override database path for tests BEFORE importing anything else
os.environ["DATABASE_URL"] = "sqlite:///./test_trunk.db"


@pytest.fixture(autouse=True)
def setup_test_db():
    """Create a fresh test database for each test."""
    from src.database import init_db, get_db_path
    import os

    # Initialize
    init_db()

    yield

    # Cleanup
    db_path = get_db_path()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(db_path + suffix)
        except FileNotFoundError:
            pass
