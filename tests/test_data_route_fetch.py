"""
Tests for the generic per-source /data/{source}[/{key}] route.

We register a MockSource (independent of Gate 2's real sources) so the
route contract is tested in isolation.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from config import settings
from data_sources.base import DataSource
from data_sources.registry import get_registry, reset_registry_for_tests
from main import app


class _MockSource(DataSource):
    name = "mock"
    default_ttl_seconds = 60

    def __init__(
        self,
        *,
        payload=None,
        enabled: bool = True,
        raise_exc: Exception | None = None,
    ):
        super().__init__()
        self._payload = payload
        self._enabled = enabled
        self._raise_exc = raise_exc
        self.last_key = None

    def is_enabled(self) -> bool:
        return self._enabled

    def disabled_reason(self) -> str:
        return "mock is disabled"

    async def _do_fetch(self, key, warnings):
        self.last_key = key
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._payload


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


# ── unknown source ─────────────────────────────────────────────────────


def test_fetch_unknown_source_returns_404(client):
    r = client.get("/data/does_not_exist")
    assert r.status_code == 404


def test_fetch_unknown_source_with_key_returns_404(client):
    r = client.get("/data/does_not_exist/some_key")
    assert r.status_code == 404


# ── happy path ─────────────────────────────────────────────────────────


def test_fetch_known_source_returns_envelope(client):
    src = _MockSource(payload={"hello": "world"})
    get_registry().register(src)

    r = client.get("/data/mock")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "mock"
    assert body["data"] == {"hello": "world"}
    assert body["warnings"] == []
    assert body["cache_hit"] is False
    assert "fetched_at" in body


def test_fetch_with_key_flows_through_to_source(client):
    src = _MockSource(payload={"ok": True})
    get_registry().register(src)

    r = client.get("/data/mock/boston")
    assert r.status_code == 200
    assert r.json()["key"] == "boston"
    assert src.last_key == "boston"


def test_fetch_with_multi_segment_key(client):
    """`/data/{source}/{key:path}` should accept multi-segment keys like a
    date in MM/DD form."""
    src = _MockSource(payload={"ok": True})
    get_registry().register(src)

    r = client.get("/data/mock/05/29")
    assert r.status_code == 200
    assert r.json()["key"] == "05/29"


# ── disabled source ────────────────────────────────────────────────────


def test_fetch_disabled_source_returns_200_with_null_data(client):
    src = _MockSource(payload={"never": True}, enabled=False)
    get_registry().register(src)

    r = client.get("/data/mock")
    assert r.status_code == 200
    body = r.json()
    assert body["data"] is None
    assert "mock is disabled" in body["warnings"]


# ── source raises ──────────────────────────────────────────────────────


def test_fetch_source_exception_returns_200_with_null_data(client, monkeypatch):
    """Sources aren't supposed to raise, but if one does, the base class
    catches it and returns a null envelope with a warning. The route stays
    at HTTP 200 — never 500."""
    src = _MockSource(raise_exc=RuntimeError("boom"))
    get_registry().register(src)

    # Also patch asyncio.sleep so retry backoffs don't slow the test.
    import data_sources.base as base_module

    async def fast_sleep(_):
        return None

    monkeypatch.setattr(base_module.asyncio, "sleep", fast_sleep)

    r = client.get("/data/mock")
    assert r.status_code == 200
    body = r.json()
    assert body["data"] is None
    assert any("RuntimeError" in w for w in body["warnings"])


# ── auth on data endpoints ─────────────────────────────────────────────


_TEST_KEY = "test-secret-fetch-yiKcAqPzBnRvXdLmSjWtHfEoGuNrMwJiVsBc"


def test_fetch_requires_auth_when_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_auth", True)
    monkeypatch.setattr(settings, "auth_protect_ask", True)
    monkeypatch.setattr(settings, "api_secret_key", _TEST_KEY)

    src = _MockSource(payload={"ok": True})
    get_registry().register(src)

    r = client.get("/data/mock")
    assert r.status_code == 401

    r = client.get("/data/mock", headers={"X-RasaPi-Key": _TEST_KEY})
    assert r.status_code == 200
