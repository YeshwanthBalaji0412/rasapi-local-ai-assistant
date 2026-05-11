import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from config import settings


def test_voice_disabled_by_default():
    assert settings.enable_voice is False


def test_voice_default_engines_are_mock():
    assert settings.voice_recorder_engine == "mock"
    assert settings.voice_stt_engine == "mock"
    assert settings.voice_tts_engine == "mock"


def test_voice_default_does_not_save_audio():
    assert settings.voice_save_audio is False


def test_voice_default_requires_push_to_talk():
    assert settings.voice_require_push_to_talk is True


def test_voice_max_transcript_chars_default():
    assert settings.voice_max_transcript_chars == 1000


# ─── Phase 10 polish: model paths + playback command ────────────────────────


def test_whisper_model_path_default_empty():
    assert settings.voice_whisper_model_path == ""


def test_piper_model_path_default_empty():
    assert settings.voice_piper_model_path == ""


def test_piper_config_path_default_empty():
    assert settings.voice_piper_config_path == ""


def test_tts_playback_command_default_auto():
    assert settings.voice_tts_playback_command == "auto"


def test_settings_accept_real_paths(monkeypatch):
    monkeypatch.setattr(settings, "voice_whisper_model_path", "/x/whisper.bin")
    monkeypatch.setattr(settings, "voice_piper_model_path", "/y/voice.onnx")
    monkeypatch.setattr(settings, "voice_piper_config_path", "/y/voice.onnx.json")
    monkeypatch.setattr(settings, "voice_tts_playback_command", "paplay")
    assert settings.voice_whisper_model_path == "/x/whisper.bin"
    assert settings.voice_piper_model_path == "/y/voice.onnx"
    assert settings.voice_piper_config_path == "/y/voice.onnx.json"
    assert settings.voice_tts_playback_command == "paplay"
