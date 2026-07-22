"""
Two-layer cache for /data/* sources.

Layer 1: in-memory dict, fastest, cleared on restart.
Layer 2: SQLite `data_cache` table, survives restarts.

Semantics:
  - get(source, key): return CacheEntry if a non-expired row exists in either
    layer. Memory hits skip SQLite. SQLite hits rehydrate memory.
  - get(source, key, include_expired=True): as above but returns expired
    entries too. Used by DataSource for the stale-fallback path.
  - set(...): writes to both layers. Memory eviction is a simple half-drop
    when the cap is exceeded.
  - prune_expired(): housekeeping; called from run-log-cleanup.sh (later gate).
  - clear(): wipes both layers. Used by tests.

The SQLite layer stores JSON, so payloads must be JSON-serialisable. Sources
should convert `datetime` / `Path` / etc. to strings before returning them.
The cache passes `default=str` to `json.dumps` as a last resort.

Thread-safety: an RLock protects the memory dict. SQLite is process-safe
under sqlite3's default "serialized" threadsafety.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> datetime:
    """Robust ISO-8601 parse. Accepts both '+00:00' and 'Z' suffixes."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


@dataclass
class CacheEntry:
    payload: Any
    fetched_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.expires_at <= (now or _now())


class TwoLayerCache:
    def __init__(
        self,
        db_path: str | Path | None = None,
        memory_max_entries: int | None = None,
    ) -> None:
        self._memory: dict[tuple[str, str], CacheEntry] = {}
        self._lock = threading.RLock()
        self._db_path = str(db_path) if db_path else str(settings.database_path)
        self._memory_max = (
            memory_max_entries
            if memory_max_entries is not None
            else int(getattr(settings, "data_memory_cache_max_entries", 500))
        )

    # ── connection helper ───────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── read ────────────────────────────────────────────────────────────

    def get(
        self,
        source: str,
        key: str,
        *,
        include_expired: bool = False,
    ) -> CacheEntry | None:
        now = _now()

        # 1. Memory
        with self._lock:
            entry = self._memory.get((source, key))
        if entry is not None:
            if include_expired or not entry.is_expired(now):
                return entry
            # Expired in memory: drop it, but leave SQLite intact for stale reads.
            with self._lock:
                self._memory.pop((source, key), None)

        # 2. SQLite
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT payload_json, fetched_at, expires_at "
                    "FROM data_cache WHERE source = ? AND key = ?",
                    (source, key),
                ).fetchone()
        except sqlite3.Error as e:
            logger.warning("data_cache SELECT failed: %s", e)
            return None
        if row is None:
            return None
        try:
            entry = CacheEntry(
                payload=json.loads(row["payload_json"]),
                fetched_at=_parse_iso(row["fetched_at"]),
                expires_at=_parse_iso(row["expires_at"]),
            )
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning("data_cache row parse failed for %s/%s: %s", source, key, e)
            return None

        if include_expired or not entry.is_expired(now):
            with self._lock:
                self._memory[(source, key)] = entry
                self._evict_if_needed()
            return entry
        return None

    # ── write ───────────────────────────────────────────────────────────

    def set(
        self,
        source: str,
        key: str,
        payload: Any,
        fetched_at: datetime,
        expires_at: datetime,
    ) -> None:
        entry = CacheEntry(payload=payload, fetched_at=fetched_at, expires_at=expires_at)

        with self._lock:
            self._memory[(source, key)] = entry
            self._evict_if_needed()

        try:
            payload_json = json.dumps(payload, default=str)
        except (TypeError, ValueError) as e:
            # Memory succeeded; SQLite persistence is best-effort.
            logger.warning(
                "data_cache: skipping SQLite persist for %s/%s (unserialisable payload): %s",
                source,
                key,
                e,
            )
            return

        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO data_cache "
                    "(source, key, payload_json, fetched_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        source,
                        key,
                        payload_json,
                        fetched_at.astimezone(timezone.utc).isoformat(),
                        expires_at.astimezone(timezone.utc).isoformat(),
                    ),
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.warning("data_cache INSERT failed for %s/%s: %s", source, key, e)

    # ── housekeeping ────────────────────────────────────────────────────

    def _evict_if_needed(self) -> None:
        """Called under lock. Simple half-drop when memory exceeds cap."""
        if len(self._memory) <= self._memory_max:
            return
        by_fetched = sorted(self._memory.items(), key=lambda kv: kv[1].fetched_at)
        keep_count = max(1, self._memory_max // 2)
        drop_count = len(self._memory) - keep_count
        for key_tuple, _ in by_fetched[:drop_count]:
            self._memory.pop(key_tuple, None)

    def clear(self) -> None:
        with self._lock:
            self._memory.clear()
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM data_cache")
                conn.commit()
        except sqlite3.Error as e:
            logger.warning("data_cache clear failed: %s", e)

    def prune_expired(self) -> int:
        """Delete expired rows from SQLite and drop matching memory entries.
        Returns the number of SQLite rows deleted. Cheap enough to run from
        run-log-cleanup.sh on a cron."""
        now_iso = _now().isoformat()
        deleted = 0
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM data_cache WHERE expires_at < ?", (now_iso,)
                )
                deleted = cur.rowcount or 0
                conn.commit()
        except sqlite3.Error as e:
            logger.warning("data_cache prune_expired failed: %s", e)
        now = _now()
        with self._lock:
            self._memory = {
                k: v for k, v in self._memory.items() if not v.is_expired(now)
            }
        return deleted

    # ── introspection (used by /data/sources) ───────────────────────────

    def memory_size(self) -> int:
        with self._lock:
            return len(self._memory)
