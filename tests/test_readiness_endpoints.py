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
    assert body["version"] == "0.11.2"


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
    assert body["version"] == "0.11.2"
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
    assert body["version"] == "0.11.2"
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


# ─── Phase 10 polish: voice model summary in /config/status ─────────────────


def test_config_status_voice_section_exposes_boolean_flags_not_paths(
    client, auth_on, monkeypatch
):
    """When voice model paths are configured, /config/status must report
    *that they are configured* — never the path value itself."""
    sentinel_whisper = "/home/sentinel/whisper.cpp/models/ggml-tiny.en.bin"
    sentinel_piper = "/home/sentinel/piper-voices/SECRET-VOICE.onnx"
    sentinel_config = "/home/sentinel/piper-voices/SECRET-VOICE.onnx.json"
    monkeypatch.setattr(settings, "voice_whisper_model_path", sentinel_whisper)
    monkeypatch.setattr(settings, "voice_piper_model_path", sentinel_piper)
    monkeypatch.setattr(settings, "voice_piper_config_path", sentinel_config)
    monkeypatch.setattr(settings, "voice_tts_playback_command", "paplay")

    resp = client.get(
        "/config/status", headers={"X-RasaPi-Key": _TEST_KEY}
    )
    body_text = resp.text
    body = resp.json()

    # The booleans are present, true.
    assert body["voice"]["whisper_model_configured"] is True
    assert body["voice"]["piper_model_configured"] is True
    assert body["voice"]["piper_config_configured"] is True
    assert body["voice"]["tts_playback_command"] == "paplay"

    # None of the sentinel paths appear in the response.
    assert sentinel_whisper not in body_text
    assert sentinel_piper not in body_text
    assert sentinel_config not in body_text


def test_config_status_voice_section_when_models_not_configured(client, auth_on):
    """Default config — paths empty — should report false for each."""
    resp = client.get(
        "/config/status", headers={"X-RasaPi-Key": _TEST_KEY}
    )
    body = resp.json()
    assert body["voice"]["whisper_model_configured"] is False
    assert body["voice"]["piper_model_configured"] is False
    assert body["voice"]["piper_config_configured"] is False
    assert body["voice"]["tts_playback_command"] == "auto"
