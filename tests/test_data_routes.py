"""
Tests for api/routes/data.py — the /data/sources endpoint.

Later gates add per-source routes; this file locks the registry endpoint's
shape + auth posture in place so nothing later can regress it silently.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from config import settings
from data_sources.base import DataSource
from data_sources.registry import get_registry, reset_registry_for_tests
from main import app


_TEST_KEY = "test-secret-9fRcMzXqLpTwEbHiVjKuBnDsAoGyPvJmQeCr"


class _MockSource(DataSource):
    name = "test_source"
    default_ttl_seconds = 60

    def __init__(self, *, enabled: bool = True):
        super().__init__()
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled

    def disabled_reason(self) -> str:
        return "test_source is disabled by the test fixture"

    async def _do_fetch(self, key, warnings):
        return None


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "enable_auth", True)
    monkeypatch.setattr(settings, "auth_protect_ask", True)
    monkeypatch.setattr(settings, "api_secret_key", _TEST_KEY)


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


# ── auth gating ─────────────────────────────────────────────────────────


def test_sources_requires_auth_when_enabled(client, auth_on):
    r = client.get("/data/sources")
    assert r.status_code == 401


def test_sources_accepts_valid_api_key(client, auth_on):
    r = client.get("/data/sources", headers={"X-RasaPi-Key": _TEST_KEY})
    assert r.status_code == 200


def test_sources_accepts_bearer_token(client, auth_on):
    r = client.get("/data/sources", headers={"Authorization": f"Bearer {_TEST_KEY}"})
    assert r.status_code == 200


def test_sources_rejects_wrong_key(client, auth_on):
    r = client.get("/data/sources", headers={"X-RasaPi-Key": "wrong"})
    assert r.status_code == 401


def test_sources_open_when_auth_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_auth", False)
    r = client.get("/data/sources")
    assert r.status_code == 200


# ── response shape ──────────────────────────────────────────────────────


def test_sources_empty_registry_returns_empty_list(client):
    r = client.get("/data/sources")
    assert r.status_code == 200
    body = r.json()
    assert body == {"sources": [], "count": 0}


def test_sources_lists_registered_sources(client):
    reg = get_registry()
    reg.register(_MockSource(enabled=True))
    r = client.get("/data/sources")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["sources"][0]["name"] == "test_source"
    assert body["sources"][0]["enabled"] is True
    assert body["sources"][0]["disabled_reason"] is None
    assert body["sources"][0]["last_fetch_at"] is None
    assert body["sources"][0]["last_fetch_ok"] is None


def test_sources_reports_disabled_state(client):
    reg = get_registry()
    reg.register(_MockSource(enabled=False))
    r = client.get("/data/sources")
    body = r.json()
    entry = body["sources"][0]
    assert entry["enabled"] is False
    assert entry["disabled_reason"] == "test_source is disabled by the test fixture"


def test_sources_response_never_includes_api_secret_key(client, auth_on):
    reg = get_registry()
    reg.register(_MockSource())
    r = client.get("/data/sources", headers={"X-RasaPi-Key": _TEST_KEY})
    assert _TEST_KEY not in r.text
