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
