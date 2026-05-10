import os
import re
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


# ─── /version ───────────────────────────────────────────────────────────────


def test_version_endpoint_public(client):
    resp = client.get("/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "RasaPi"
    assert body["version"] == "0.10.0"


def test_version_remains_public_when_auth_on(client, auth_on):
    """/version is a public probe — auth should not gate it."""
    resp = client.get("/version")
    assert resp.status_code == 200


# ─── /readiness ─────────────────────────────────────────────────────────────


def test_readiness_endpoint_public(client):
    resp = client.get("/readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["version"] == "0.10.0"
    assert "checks" in body
    assert "database_dir" in body["checks"]


def test_readiness_remains_public_when_auth_on(client, auth_on):
    resp = client.get("/readiness")
    assert resp.status_code == 200


def test_readiness_does_not_leak_filesystem_paths(client):
    """No `/Users/`, `/home/`, `/private/var/` prefixes in the body."""
    body = client.get("/readiness").text
    assert "/Users/" not in body
    assert "/home/" not in body
    assert "/private/var/" not in body


# ─── /config/status ─────────────────────────────────────────────────────────


def test_config_status_public_when_auth_off(client):
    resp = client.get("/config/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == "0.10.0"
    assert "features" in body
    assert "auth" in body
    assert body["auth"]["enabled"] is False


def test_config_status_returns_401_when_auth_on_no_key(client, auth_on):
    resp = client.get("/config/status")
    assert resp.status_code == 401


def test_config_status_works_with_api_key(client, auth_on):
    resp = client.get("/config/status", headers={"X-RasaPi-Key": _TEST_KEY})
    assert resp.status_code == 200
    body = resp.json()
    assert body["auth"]["enabled"] is True
    assert body["auth"]["secret_configured"] is True


def test_config_status_returns_503_when_auth_misconfigured(client, monkeypatch):
    """ENABLE_AUTH=true + placeholder key → fail-closed."""
    monkeypatch.setattr(settings, "enable_auth", True)
    monkeypatch.setattr(settings, "api_secret_key", "change-me-before-use")
    resp = client.get("/config/status", headers={"X-RasaPi-Key": "anything"})
    assert resp.status_code == 503


# ─── /config/status never leaks secrets ─────────────────────────────────────


def test_config_status_never_contains_api_secret_key(client, auth_on):
    body = client.get(
        "/config/status", headers={"X-RasaPi-Key": _TEST_KEY}
    ).text
    assert _TEST_KEY not in body
    assert "API_SECRET_KEY" not in body


def test_config_status_never_contains_slack_webhook(client, auth_on, monkeypatch):
    sentinel = "https://hooks.slack.com/services/CANARY-DO-NOT-LEAK/12345/abcdef"
    monkeypatch.setattr(settings, "enable_slack", True)
    monkeypatch.setattr(settings, "slack_webhook_url", sentinel)
    body = client.get(
        "/config/status", headers={"X-RasaPi-Key": _TEST_KEY}
    ).text
    assert sentinel not in body
    assert "hooks.slack.com" not in body


def test_config_status_never_contains_ha_token(client, auth_on, monkeypatch):
    sentinel = "ha-token-CANARY-LEAK-CANDIDATE-99999"
    monkeypatch.setattr(settings, "enable_home_assistant", True)
    monkeypatch.setattr(settings, "home_assistant_url", "http://ha.local:8123")
    monkeypatch.setattr(settings, "home_assistant_token", sentinel)
    body = client.get(
        "/config/status", headers={"X-RasaPi-Key": _TEST_KEY}
    ).text
    assert sentinel not in body


def test_config_status_does_not_contain_filesystem_paths(client, auth_on):
    body = client.get(
        "/config/status", headers={"X-RasaPi-Key": _TEST_KEY}
    ).text
    assert not re.search(r"/Users/[^\"]+", body)
    assert not re.search(r"/home/[^\"]+", body)
    assert not re.search(r"/private/var/", body)
