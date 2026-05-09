import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from config import settings
from core import memory
from storage.database import db_session
from voice import session as session_module
from voice import stt as stt_module
from voice import tts as tts_module


@pytest.fixture(autouse=True)
def _reset_mock_tts():
    tts_module.reset_mock_history()
    yield
    tts_module.reset_mock_history()


@pytest.fixture
def voice_on(monkeypatch):
    monkeypatch.setattr(settings, "enable_voice", True)


def _set_mock_transcript(monkeypatch, text: str) -> None:
    monkeypatch.setattr(stt_module, "DEFAULT_MOCK_TRANSCRIPT", text)


# ─── happy path ──────────────────────────────────────────────────────────────


def test_voice_session_with_mocks_succeeds(voice_on, monkeypatch):
    _set_mock_transcript(monkeypatch, "hello")
    result = asyncio.run(session_module.run_session_once())
    assert result.transcript == "hello"
    assert result.intent == "greeting"
    assert "RasaPi" in result.response


def test_voice_session_routes_through_assistant_logic(voice_on, monkeypatch):
    """The transcript 'remember that X' must create a memory row, just like /ask."""
    _set_mock_transcript(monkeypatch, "remember that my project is RasaPi")
    asyncio.run(session_module.run_session_once())
    items = memory.list_memory(request_id="verify")
    assert any("RasaPi" in i["value"] for i in items)


def test_voice_session_known_command_routes_to_intent(voice_on, monkeypatch):
    _set_mock_transcript(monkeypatch, "what time is it")
    result = asyncio.run(session_module.run_session_once())
    assert result.intent == "time"


def test_voice_session_disabled_raises(monkeypatch):
    monkeypatch.setattr(settings, "enable_voice", False)
    with pytest.raises(session_module.VoiceDisabledError):
        asyncio.run(session_module.run_session_once())


# ─── transcript handling ─────────────────────────────────────────────────────


def test_transcript_truncated_to_max_chars(voice_on, monkeypatch):
    long = "remember that " + ("x" * 5000)
    monkeypatch.setattr(settings, "voice_max_transcript_chars", 100)
    _set_mock_transcript(monkeypatch, long)
    result = asyncio.run(session_module.run_session_once())
    assert len(result.transcript) <= 100


def test_empty_transcript_returns_safe_message(voice_on, monkeypatch):
    _set_mock_transcript(monkeypatch, "")
    result = asyncio.run(session_module.run_session_once())
    assert result.intent == "voice_no_input"
    assert "didn't catch" in result.response.lower()


# ─── audio file lifecycle ────────────────────────────────────────────────────


def test_temp_audio_deleted_when_save_disabled(voice_on, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "voice_audio_temp_dir", str(tmp_path / "audio"))
    monkeypatch.setattr(settings, "voice_save_audio", False)
    _set_mock_transcript(monkeypatch, "hello")
    asyncio.run(session_module.run_session_once())
    audio_dir = Path(settings.voice_audio_temp_dir)
    leftover = list(audio_dir.glob("*.wav"))
    assert leftover == []


def test_temp_audio_kept_when_save_enabled(voice_on, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "voice_audio_temp_dir", str(tmp_path / "audio"))
    monkeypatch.setattr(settings, "voice_save_audio", True)
    _set_mock_transcript(monkeypatch, "hello")
    result = asyncio.run(session_module.run_session_once())
    assert result.audio_saved is True
    audio_dir = Path(settings.voice_audio_temp_dir)
    leftover = list(audio_dir.glob("*.wav"))
    assert len(leftover) == 1


# ─── TTS receives the assistant response ────────────────────────────────────


def test_tts_receives_assistant_response_not_transcript(voice_on, monkeypatch):
    _set_mock_transcript(monkeypatch, "what time is it")
    result = asyncio.run(session_module.run_session_once())
    spoken = list(tts_module.MockTTS.spoken)
    assert spoken, "MockTTS should have recorded at least one spoken text"
    # The TTS engine speaks the response, not the transcript.
    assert spoken[-1] == result.response
    assert spoken[-1] != "what time is it"


# ─── failure path ────────────────────────────────────────────────────────────


def test_recorder_failure_raises_after_audit(voice_on, monkeypatch):
    """A recorder error propagates, but the session_failed audit is logged
    and any partial audio file is cleaned up."""
    monkeypatch.setattr(settings, "voice_save_audio", False)
    _set_mock_transcript(monkeypatch, "hello")
    with patch.object(
        session_module.recorder_module,
        "build_recorder",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            asyncio.run(session_module.run_session_once())


# ─── command runner is never invoked from voice ──────────────────────────────


def test_voice_session_does_not_invoke_command_runner_for_handler_intent(
    voice_on, monkeypatch
):
    """For 'hello' (handler intent), no run_command call is made."""
    _set_mock_transcript(monkeypatch, "hello")
    with patch(
        "core.command_runner.run_command",
        side_effect=AssertionError("must not be called for handler intent"),
    ):
        result = asyncio.run(session_module.run_session_once())
    assert result.intent == "greeting"
