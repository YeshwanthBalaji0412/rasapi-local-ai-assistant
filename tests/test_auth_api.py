import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

from config import settings
from main import app


_TEST_KEY = "test-secret-VR1Hh7dQrEKaBiu1hqsfO9xNpV0sa1ZwH4bM"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "enable_auth", True)
    monkeypatch.setattr(settings, "api_secret_key", _TEST_KEY)


@pytest.fixture
def auth_on_no_secret(monkeypatch):
    monkeypatch.setattr(settings, "enable_auth", True)
    monkeypatch.setattr(settings, "api_secret_key", "change-me-before-use")


# ─── /health and /commands always public ────────────────────────────────────


def test_health_always_public(client, auth_on):
    assert client.get("/health").status_code == 200


def test_commands_always_public(client, auth_on):
    assert client.get("/commands").status_code == 200


# ─── /ask gating ─────────────────────────────────────────────────────────────


def test_ask_open_when_auth_disabled(client):
    resp = client.post("/ask", json={"query": "hello"})
    assert resp.status_code == 200


def test_ask_returns_401_when_auth_on_and_no_key(client, auth_on):
    resp = client.post("/ask", json={"query": "hello"})
    assert resp.status_code == 401


def test_ask_works_with_x_rasapi_key_header(client, auth_on):
    resp = client.post(
        "/ask",
        json={"query": "hello"},
        headers={"X-RasaPi-Key": _TEST_KEY},
    )
    assert resp.status_code == 200
    assert resp.json()["intent"] == "greeting"


def test_ask_works_with_authorization_bearer(client, auth_on):
    resp = client.post(
        "/ask",
        json={"query": "hello"},
        headers={"Authorization": f"Bearer {_TEST_KEY}"},
    )
    assert resp.status_code == 200


def test_ask_returns_401_with_wrong_key(client, auth_on):
    resp = client.post(
        "/ask",
        json={"query": "hello"},
        headers={"X-RasaPi-Key": "totally-wrong-key"},
    )
    assert resp.status_code == 401


# ─── /voice gating ───────────────────────────────────────────────────────────


def test_voice_session_returns_401_when_auth_on_and_no_key(client, auth_on, monkeypatch):
    monkeypatch.setattr(settings, "enable_voice", True)
    resp = client.post("/voice/session-once")
    assert resp.status_code == 401


def test_voice_session_works_with_key(client, auth_on, monkeypatch):
    monkeypatch.setattr(settings, "enable_voice", True)
    resp = client.post(
        "/voice/session-once", headers={"X-RasaPi-Key": _TEST_KEY}
    )
    assert resp.status_code == 200


# ─── /memory and /tasks (mutations flag) ─────────────────────────────────────


def test_memory_post_returns_401_when_auth_on(client, auth_on):
    resp = client.post("/memory", json={"value": "remember this"})
    assert resp.status_code == 401


def test_memory_post_works_with_key(client, auth_on):
    resp = client.post(
        "/memory",
        json={"value": "remember this"},
        headers={"X-RasaPi-Key": _TEST_KEY},
    )
    assert resp.status_code == 201


def test_memory_get_returns_401_when_auth_on(client, auth_on):
    """Reading personal data is also gated by AUTH_PROTECT_MUTATIONS."""
    resp = client.get("/memory")
    assert resp.status_code == 401


def test_tasks_patch_returns_401_when_auth_on(client, auth_on):
    resp = client.patch("/tasks/1/complete")
    assert resp.status_code == 401


# ─── /briefing stays public ──────────────────────────────────────────────────


def test_briefing_sources_public_even_when_auth_on(client, auth_on):
    resp = client.get("/briefing/sources")
    assert resp.status_code == 200


# ─── auth misconfigured (enabled + placeholder) → 503 ────────────────────────


def test_protected_route_503_when_secret_is_placeholder(client, auth_on_no_secret):
    resp = client.post("/ask", json={"query": "hello"}, headers={"X-RasaPi-Key": "anything"})
    assert resp.status_code == 503
    assert "auth misconfigured" in resp.json()["detail"].lower()


def test_health_still_public_when_secret_is_placeholder(client, auth_on_no_secret):
    """/health must remain reachable even in the misconfigured state so
    operators can still see the service is alive."""
    assert client.get("/health").status_code == 200
