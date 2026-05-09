import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

from config import settings
from main import app
from voice import stt as stt_module
from voice import tts as tts_module


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_tts():
    tts_module.reset_mock_history()
    yield
    tts_module.reset_mock_history()


# ─── /voice/status ───────────────────────────────────────────────────────────


def test_voice_status_returns_safe_config(client):
    resp = client.get("/voice/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["recorder_engine"] == "mock"
    assert body["stt_engine"] == "mock"
    assert body["tts_engine"] == "mock"


def test_voice_status_does_not_leak_secrets(client):
    resp = client.get("/voice/status")
    text = resp.text
    assert settings.api_secret_key not in text
    assert "API_KEY" not in text
    assert "/Users/" not in text


# ─── /voice/session-once ─────────────────────────────────────────────────────


def test_voice_session_once_refused_when_disabled(client):
    resp = client.post("/voice/session-once")
    assert resp.status_code == 403


def test_voice_session_once_succeeds_when_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_voice", True)
    monkeypatch.setattr(stt_module, "DEFAULT_MOCK_TRANSCRIPT", "hello")
    resp = client.post("/voice/session-once")
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] == "hello"
    assert body["intent"] == "greeting"
    assert body["audio_saved"] is False


# ─── /voice/test-tts ─────────────────────────────────────────────────────────


def test_voice_test_tts_refused_when_disabled(client):
    resp = client.post("/voice/test-tts", json={"text": "hi"})
    assert resp.status_code == 403


def test_voice_test_tts_succeeds_when_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_voice", True)
    resp = client.post("/voice/test-tts", json={"text": "Hello, I am RasaPi"})
    assert resp.status_code == 200
    assert resp.json()["spoken"] is True
    assert "Hello, I am RasaPi" in tts_module.MockTTS.spoken


# ─── dashboard renders the voice card ────────────────────────────────────────


def test_dashboard_renders_voice_section(client):
    body = client.get("/dashboard").text
    assert "<h2>Voice</h2>" in body
    assert "Recorder" in body
    assert "STT" in body
    assert "TTS" in body
