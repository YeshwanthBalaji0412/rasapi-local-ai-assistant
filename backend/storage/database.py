"""
SQLite connection helper and schema bootstrap (Phase 3).

The database is local-only. Path is read from settings at call time so tests
can override it via monkeypatch. All write paths use parameterized queries.
"""

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from config import settings
from storage.schema import ALL_STATEMENTS


logger = logging.getLogger(__name__)


def _ensure_parent_dir() -> Path:
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def init_db() -> None:
    """Idempotent: creates tables and indexes if they don't exist yet."""
    db_path = _ensure_parent_dir()
    logger.info("Initializing local database at %s", db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        for stmt in ALL_STATEMENTS:
            conn.execute(stmt)
        conn.commit()


@contextmanager
def db_session() -> Iterator[sqlite3.Connection]:
    """
    Yields a sqlite3.Connection with row_factory=Row. Commits on clean exit,
    rolls back on exception. Always closes.
    """
    db_path = _ensure_parent_dir()
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
