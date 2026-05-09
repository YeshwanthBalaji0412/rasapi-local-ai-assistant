"""
Phase 9 — /ask routing for integration intents.

These verify the deterministic intent router maps the right phrases to the
right handlers. Real Slack / HA calls are mocked.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import httpx
import pytest
from fastapi.testclient import TestClient

from config import settings
from main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def slack_ready(monkeypatch):
    monkeypatch.setattr(settings, "enable_slack", True)
    monkeypatch.setattr(
        settings, "slack_webhook_url", "https://hooks.slack.com/services/T/B/x"
    )


@pytest.fixture
def ha_ready(monkeypatch):
    monkeypatch.setattr(settings, "enable_home_assistant", True)
    monkeypatch.setattr(settings, "home_assistant_url", "http://ha.local:8123")
    monkeypatch.setattr(settings, "home_assistant_token", "tkn")
    monkeypatch.setattr(
        settings, "home_assistant_allowed_entities", "light.desk_light,switch.fan,sensor.living_temp"
    )


def _ok():
    r = MagicMock(spec=httpx.Response)
    r.status_code = 200
    r.json.return_value = {"version": "x"}
    return r


# ─── Intent dispatch ────────────────────────────────────────────────────────


def test_send_test_slack_routes_to_slack_test(client, slack_ready):
    with patch("integrations.slack.httpx.post", return_value=_ok()):
        resp = client.post("/ask", json={"query": "send test slack notification"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "slack_send_test"


def test_send_daily_briefing_to_slack_routes_correctly(client, slack_ready):
    with patch("integrations.slack.httpx.post", return_value=_ok()):
        resp = client.post(
            "/ask", json={"query": "send today's briefing to Slack"}
        )
    assert resp.status_code == 200
    assert resp.json()["intent"] == "slack_send_briefing"


def test_send_ai_briefing_routes_to_slack_with_ai_category(client, slack_ready):
    captured: dict = {}
    def fake_post(url, json, timeout):
        captured["text"] = json.get("text", "")
        return _ok()
    with patch("integrations.slack.httpx.post", side_effect=fake_post):
        resp = client.post("/ask", json={"query": "send AI briefing to Slack"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "slack_send_briefing"
    # The AI-category briefing text should be sent (or fallback header).
    assert "RasaPi briefing" in captured["text"]


def test_home_assistant_status_intent_routes(client, ha_ready):
    with patch("integrations.home_assistant.httpx.get", return_value=_ok()):
        resp = client.post("/ask", json={"query": "home assistant status"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "ha_status"


def test_turn_on_desk_light_calls_ha(client, ha_ready):
    captured: dict = {}
    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["json"] = json
        r = MagicMock(spec=httpx.Response)
        r.status_code = 200
        r.json.return_value = []
        return r
    with patch("integrations.home_assistant.httpx.post", side_effect=fake_post):
        resp = client.post("/ask", json={"query": "turn on desk light"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "ha_turn_on"
    assert captured["url"].endswith("/api/services/light/turn_on")
    assert captured["json"] == {"entity_id": "light.desk_light"}


# ─── Integration intents do NOT invoke command_runner ──────────────────────


def test_integration_intents_do_not_invoke_command_runner(client, ha_ready):
    """The deterministic router dispatches; nothing reaches subprocess."""
    with patch("integrations.home_assistant.httpx.get", return_value=_ok()), \
         patch("core.command_runner.run_command",
               side_effect=AssertionError("must not be called")):
        resp = client.post("/ask", json={"query": "home assistant status"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "ha_status"


def test_integration_intents_do_not_invoke_local_llm(client, slack_ready, monkeypatch):
    """Even with the LLM enabled, integration intents short-circuit."""
    from unittest.mock import AsyncMock
    monkeypatch.setattr(settings, "enable_local_llm", True)
    with patch("integrations.slack.httpx.post", return_value=_ok()), \
         patch("core.orchestration.local_llm.generate_chat_response",
               new_callable=AsyncMock) as mock_llm:
        resp = client.post("/ask", json={"query": "send test slack notification"})
    assert resp.status_code == 200
    mock_llm.assert_not_called()
