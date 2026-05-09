import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import httpx
import pytest
from fastapi.testclient import TestClient

from config import settings
from main import app


_TEST_KEY = "test-secret-VR1Hh7dQrEKaBiu1hqsfO9xNpV0sa1ZwH4bM"
_HA_URL = "http://ha.local:8123"
_HA_TOKEN = "ha-token-test"
_SLACK_URL = "https://hooks.slack.com/services/T_TEST/B_TEST/secret"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "enable_auth", True)
    monkeypatch.setattr(settings, "api_secret_key", _TEST_KEY)


@pytest.fixture
def slack_ready(monkeypatch):
    monkeypatch.setattr(settings, "enable_slack", True)
    monkeypatch.setattr(settings, "slack_webhook_url", _SLACK_URL)


@pytest.fixture
def ha_ready(monkeypatch):
    monkeypatch.setattr(settings, "enable_home_assistant", True)
    monkeypatch.setattr(settings, "home_assistant_url", _HA_URL)
    monkeypatch.setattr(settings, "home_assistant_token", _HA_TOKEN)
    monkeypatch.setattr(
        settings, "home_assistant_allowed_entities", "light.desk_light,switch.fan"
    )


def _ok_response(payload=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = payload or {}
    return resp


# ─── GET /integrations is open by default, gated when auth on ──────────────


def test_get_integrations_open_when_auth_off(client):
    resp = client.get("/integrations")
    assert resp.status_code == 200
    keys = {e["key"] for e in resp.json()["integrations"]}
    assert keys == {"slack", "home_assistant", "alexa_future_stub"}


def test_get_integrations_returns_401_when_auth_on_no_key(client, auth_on):
    resp = client.get("/integrations")
    assert resp.status_code == 401


def test_get_integrations_works_with_api_key(client, auth_on):
    resp = client.get("/integrations", headers={"X-RasaPi-Key": _TEST_KEY})
    assert resp.status_code == 200


# ─── Slack endpoints ─────────────────────────────────────────────────────────


def test_slack_test_returns_409_when_not_configured(client, auth_on):
    resp = client.post(
        "/integrations/slack/test", headers={"X-RasaPi-Key": _TEST_KEY}
    )
    assert resp.status_code == 409


def test_slack_test_works_with_api_key_and_mocked_post(client, auth_on, slack_ready):
    with patch("integrations.slack.httpx.post", return_value=_ok_response()):
        resp = client.post(
            "/integrations/slack/test", headers={"X-RasaPi-Key": _TEST_KEY}
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ─── Home Assistant endpoints ───────────────────────────────────────────────


def test_ha_status_returns_401_without_key(client, auth_on, ha_ready):
    resp = client.get("/integrations/home-assistant/status")
    assert resp.status_code == 401


def test_ha_turn_on_works_with_key(client, auth_on, ha_ready):
    with patch(
        "integrations.home_assistant.httpx.post",
        return_value=_ok_response([]),
    ):
        resp = client.post(
            "/integrations/home-assistant/entities/light.desk_light/turn-on",
            headers={"X-RasaPi-Key": _TEST_KEY},
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_ha_turn_on_blocked_entity_returns_400(client, auth_on, ha_ready):
    resp = client.post(
        "/integrations/home-assistant/entities/lock.front_door/turn-on",
        headers={"X-RasaPi-Key": _TEST_KEY},
    )
    assert resp.status_code == 400


# ─── Dashboard renders Integrations card ────────────────────────────────────


def test_dashboard_renders_integrations_section(client):
    body = client.get("/dashboard").text
    assert "<h2>Integrations</h2>" in body
    # All three registry slots show up
    assert "Slack" in body
    assert "Home Assistant" in body
    assert "Alexa" in body or "alexa" in body.lower()


def test_dashboard_does_not_leak_slack_webhook(client, slack_ready):
    body = client.get("/dashboard").text
    assert _SLACK_URL not in body
    assert "hooks.slack.com" not in body


def test_dashboard_does_not_leak_ha_token(client, ha_ready):
    body = client.get("/dashboard").text
    assert _HA_TOKEN not in body
