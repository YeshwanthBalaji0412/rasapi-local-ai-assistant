"""
Tests for data_sources.base — DataSource ABC, Envelope, timeout/retry.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from data_sources.base import DataSource, Envelope
from data_sources.cache import TwoLayerCache


# ── test doubles ────────────────────────────────────────────────────────


class _StubSource(DataSource):
    """Configurable fake source. Every knob we need for base-class testing."""

    name = "stub"
    default_ttl_seconds = 60

    def __init__(
        self,
        *,
        payload=None,
        raise_exc: Exception | None = None,
        sleep_seconds: float = 0.0,
        enabled: bool = True,
        cache=None,
        timeout_seconds: float = 5.0,
        retries: int = 0,
    ):
        super().__init__(cache=cache, timeout_seconds=timeout_seconds, retries=retries)
        self._payload = payload
        self._raise_exc = raise_exc
        self._sleep = sleep_seconds
        self._enabled = enabled
        self.calls = 0

    def is_enabled(self) -> bool:
        return self._enabled

    def disabled_reason(self) -> str:
        return "stub is disabled by test"

    async def _do_fetch(self, key: str, warnings: list[str]):
        self.calls += 1
        if self._sleep:
            await asyncio.sleep(self._sleep)
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._payload


# ── envelope shape ──────────────────────────────────────────────────────


def test_envelope_to_dict_has_iso_z_timestamps():
    now = datetime(2026, 5, 29, 14, 22, 31, tzinfo=timezone.utc)
    env = Envelope(
        source="x",
        key="y",
        fetched_at=now,
        cache_hit=False,
        cache_expires_at=now,
        data={"a": 1},
        warnings=["hi"],
    )
    d = env.to_dict()
    assert d["source"] == "x"
    assert d["key"] == "y"
    assert d["fetched_at"] == "2026-05-29T14:22:31Z"
    assert d["cache_expires_at"] == "2026-05-29T14:22:31Z"
    assert d["cache_hit"] is False
    assert d["data"] == {"a": 1}
    assert d["warnings"] == ["hi"]


def test_envelope_to_dict_handles_null_expires():
    env = Envelope(
        source="x",
        key="y",
        fetched_at=datetime.now(timezone.utc),
        cache_hit=False,
        cache_expires_at=None,
        data=None,
        warnings=[],
    )
    assert env.to_dict()["cache_expires_at"] is None


# ── contract ────────────────────────────────────────────────────────────


def test_source_without_name_raises():
    class Nameless(DataSource):
        name = ""

        async def _do_fetch(self, key, warnings):
            return None

    with pytest.raises(ValueError):
        Nameless()


def test_disabled_source_returns_null_envelope_with_reason():
    src = _StubSource(payload={"never": "fetched"}, enabled=False)
    env = asyncio.run(src.fetch(""))
    assert env.data is None
    assert env.cache_hit is False
    assert env.cache_expires_at is None
    assert "stub is disabled by test" in env.warnings
    assert src.calls == 0  # never dispatched to upstream


# ── happy path ──────────────────────────────────────────────────────────


def test_success_returns_data_envelope():
    src = _StubSource(payload={"ok": True})
    env = asyncio.run(src.fetch("k"))
    assert env.data == {"ok": True}
    assert env.cache_hit is False
    assert env.warnings == []
    assert env.cache_expires_at is not None
    assert env.cache_expires_at > env.fetched_at


def test_success_key_flows_through_to_envelope():
    src = _StubSource(payload={"ok": True})
    env = asyncio.run(src.fetch("boston"))
    assert env.key == "boston"


# ── failure paths ───────────────────────────────────────────────────────


def test_timeout_returns_null_data_and_warning():
    src = _StubSource(
        payload={"never": True}, sleep_seconds=0.5, timeout_seconds=0.05, retries=0
    )
    env = asyncio.run(src.fetch(""))
    assert env.data is None
    assert any("timeout" in w for w in env.warnings)


def test_exception_returns_null_data_and_warning():
    src = _StubSource(raise_exc=RuntimeError("upstream down"), retries=0)
    env = asyncio.run(src.fetch(""))
    assert env.data is None
    assert any("RuntimeError" in w for w in env.warnings)


def test_retry_counts_multiple_attempts():
    class Flaky(DataSource):
        name = "flaky"
        default_ttl_seconds = 60

        def __init__(self):
            super().__init__(retries=2, timeout_seconds=1.0)
            self.calls = 0

        async def _do_fetch(self, key, warnings):
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("temporary")
            return {"eventually": True}

    src = Flaky()
    # Speed the test up: skip the 2s backoff in _fetch_with_retry.
    async def _fast_sleep(_):
        return None

    env = asyncio.run(_run_with_patched_sleep(src, _fast_sleep))
    assert env.data == {"eventually": True}
    assert src.calls == 3


async def _run_with_patched_sleep(src: DataSource, patched_sleep):
    """Helper: run fetch() with asyncio.sleep monkey-patched to be a no-op."""
    import data_sources.base as base_module

    original = base_module.asyncio.sleep
    base_module.asyncio.sleep = patched_sleep  # type: ignore[assignment]
    try:
        return await src.fetch("")
    finally:
        base_module.asyncio.sleep = original  # type: ignore[assignment]


# ── cache interaction ──────────────────────────────────────────────────


def test_cache_hit_returns_cached_data_without_upstream_call():
    cache = TwoLayerCache()
    src = _StubSource(payload={"first": True}, cache=cache)

    first = asyncio.run(src.fetch("k"))
    assert first.cache_hit is False
    assert src.calls == 1

    # Second call: should be served from cache; no new upstream call.
    src._payload = {"second": True}  # would be returned if upstream ran
    second = asyncio.run(src.fetch("k"))
    assert second.cache_hit is True
    assert second.data == {"first": True}
    assert src.calls == 1  # unchanged


def test_stale_fallback_when_upstream_fails_and_stale_cache_exists():
    cache = TwoLayerCache()
    src = _StubSource(payload={"good": True}, cache=cache)

    # Populate cache with a fresh entry, then make it stale.
    asyncio.run(src.fetch("k"))
    from data_sources.cache import _now  # noqa: F401 (import for patch context)
    from datetime import timedelta

    entry = cache.get("stub", "k", include_expired=True)
    assert entry is not None
    entry.expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    # Also expire the SQLite row so a fresh TwoLayerCache would still see stale.
    cache.set("stub", "k", entry.payload, entry.fetched_at, entry.expires_at)

    # Break upstream. Fresh fetch fails, stale should be served.
    src._payload = None
    src._raise_exc = RuntimeError("upstream")
    env = asyncio.run(src.fetch("k"))
    assert env.data == {"good": True}
    assert "stale, upstream unreachable" in env.warnings
    assert env.cache_hit is True
