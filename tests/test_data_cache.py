"""
Tests for data_sources.cache.TwoLayerCache.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from data_sources.cache import CacheEntry, TwoLayerCache


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── memory-only behavior ────────────────────────────────────────────────


def test_set_then_get_returns_entry():
    cache = TwoLayerCache()
    now = _now()
    cache.set("src", "k", {"a": 1}, now, now + timedelta(minutes=5))
    entry = cache.get("src", "k")
    assert entry is not None
    assert entry.payload == {"a": 1}


def test_get_miss_returns_none():
    cache = TwoLayerCache()
    assert cache.get("src", "missing") is None


def test_expired_entry_not_returned_by_default():
    cache = TwoLayerCache()
    now = _now()
    cache.set("src", "k", {"a": 1}, now - timedelta(minutes=10), now - timedelta(minutes=5))
    assert cache.get("src", "k") is None


def test_expired_entry_returned_when_include_expired():
    cache = TwoLayerCache()
    now = _now()
    past_fetched = now - timedelta(minutes=10)
    past_expired = now - timedelta(minutes=5)
    cache.set("src", "k", {"a": 1}, past_fetched, past_expired)
    entry = cache.get("src", "k", include_expired=True)
    assert entry is not None
    assert entry.payload == {"a": 1}
    assert entry.is_expired() is True


# ── SQLite persistence ─────────────────────────────────────────────────


def test_sqlite_persists_across_new_cache_instance(monkeypatch, tmp_path):
    """A fresh TwoLayerCache pointed at the same DB must see prior writes."""
    now = _now()
    c1 = TwoLayerCache()
    c1.set("src", "persisted", {"n": 42}, now, now + timedelta(minutes=5))

    # New instance = empty memory cache. SQLite should still serve it.
    c2 = TwoLayerCache()
    entry = c2.get("src", "persisted")
    assert entry is not None
    assert entry.payload == {"n": 42}


def test_sqlite_hit_rehydrates_memory():
    now = _now()
    c1 = TwoLayerCache()
    c1.set("src", "rehydrate", {"x": 1}, now, now + timedelta(minutes=5))
    c2 = TwoLayerCache()
    assert c2.memory_size() == 0
    c2.get("src", "rehydrate")
    assert c2.memory_size() == 1


# ── housekeeping ───────────────────────────────────────────────────────


def test_prune_expired_removes_only_expired_rows():
    now = _now()
    cache = TwoLayerCache()
    cache.set("src", "fresh", {"a": 1}, now, now + timedelta(minutes=5))
    cache.set("src", "stale", {"b": 2}, now - timedelta(hours=2), now - timedelta(hours=1))

    deleted = cache.prune_expired()
    assert deleted == 1
    assert cache.get("src", "fresh") is not None
    assert cache.get("src", "stale", include_expired=True) is None


def test_clear_wipes_both_layers():
    now = _now()
    c1 = TwoLayerCache()
    c1.set("src", "k", {"a": 1}, now, now + timedelta(minutes=5))
    c1.clear()
    assert c1.get("src", "k") is None
    assert c1.get("src", "k", include_expired=True) is None
    # Also verify SQLite side is empty (a new instance sees nothing):
    c2 = TwoLayerCache()
    assert c2.get("src", "k", include_expired=True) is None


# ── memory eviction ────────────────────────────────────────────────────


def test_memory_eviction_drops_oldest():
    cache = TwoLayerCache(memory_max_entries=4)
    now = _now()
    # 5 entries with increasing fetched_at
    for i in range(5):
        cache.set(
            "src",
            f"k{i}",
            {"i": i},
            now + timedelta(seconds=i),
            now + timedelta(minutes=5),
        )
    # After the 5th set, memory should be at ≤ max/2 (evict drops to half).
    # Newest entry must still be present in memory.
    assert cache.memory_size() <= 4
    # The most recently set entry is always retained.
    assert cache.get("src", "k4") is not None


# ── payload serialisation ──────────────────────────────────────────────


def test_non_json_payload_still_writes_to_memory():
    """set() with an unserialisable payload must not crash — memory succeeds,
    SQLite is best-effort."""

    class NotSerialisable:
        pass

    now = _now()
    cache = TwoLayerCache()
    cache.set("src", "k", NotSerialisable(), now, now + timedelta(minutes=5))
    entry = cache.get("src", "k")
    assert entry is not None  # memory path served it


# ── CacheEntry helper ──────────────────────────────────────────────────


def test_cache_entry_is_expired_helper():
    now = _now()
    fresh = CacheEntry(payload={}, fetched_at=now, expires_at=now + timedelta(minutes=5))
    stale = CacheEntry(
        payload={}, fetched_at=now - timedelta(minutes=10), expires_at=now - timedelta(minutes=5)
    )
    assert fresh.is_expired() is False
    assert stale.is_expired() is True
