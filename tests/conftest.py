"""
Shared pytest fixtures.

The autouse `isolated_db` fixture gives every test a fresh SQLite file in
a temp directory. Tests that don't touch the DB pay only the cost of an
empty CREATE TABLE IF NOT EXISTS.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from config import settings
from storage.database import init_db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    init_db()
    yield
