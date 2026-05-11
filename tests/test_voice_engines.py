"""
Phase 10 polish — exercise WhisperCppSTT and PiperTTS without invoking
real binaries.

These tests mock `subprocess.run` so the actual `whisper-cli` and `piper`
binaries never have to be installed. We assert on the command line they
would invoke, and on the friendly EngineNotAvailable messages when model
paths are missing.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from config import settings
from voice import stt as stt_module
from voice import tts as tts_module


# ─── WhisperCppSTT ──────────────────────────────────────────────────────────


def _make_completed_process(returncode: int = 0, stderr: str = "") -> MagicMock:
    cp = MagicMock(spec=subprocess.CompletedProcess)
    cp.returncode = returncode
    cp.stderr = stderr
    return cp


def test_whisper_passes_dash_m_when_model_path_set(tmp_path, monkeypatch):
    """If VOICE_WHISPER_MODEL_PATH is configured, the adapter must pass
    it via `-m` so whisper-cli doesn't fall back to its default lookup."""
    real_model = tmp_path / "ggml-tiny.en.bin"
    real_model.write_bytes(b"fake-model-bytes")
    monkeypatch.setattr(settings, "voice_whisper_model_path", str(real_model))

    audio_path = tmp_path / "test.wav"
    audio_path.write_bytes(b"fake-audio")

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        # Whisper writes a .txt next to the audio path's stem.
        out_path = Path(cmd[cmd.index("-of") + 1]).with_suffix(".txt")
        out_path.write_text("hello world\n", encoding="utf-8")
        return _make_completed_process(0)

    with patch("voice.stt.subprocess.run", side_effect=fake_run):
        engine = stt_module.WhisperCppSTT()
        transcript = engine.transcribe(audio_path=audio_path)

    assert transcript == "hello world"
    assert "-m" in captured["cmd"]
    assert str(real_model) in captured["cmd"]


def test_whisper_skips_dash_m_when_model_path_empty(tmp_path, monkeypatch):
    """With no path configured, the adapter must NOT pass `-m`. Keeps
    backward-compatible behaviour for installs relying on whisper-cli's
    default model lookup."""
    monkeypatch.setattr(settings, "voice_whisper_model_path", "")
    audio_path = tmp_path / "test.wav"
    audio_path.write_bytes(b"fake-audio")

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        out_path = Path(cmd[cmd.index("-of") + 1]).with_suffix(".txt")
        out_path.write_text("hi", encoding="utf-8")
        return _make_completed_process(0)

    with patch("voice.stt.subprocess.run", side_effect=fake_run):
        stt_module.WhisperCppSTT().transcribe(audio_path=audio_path)

    assert "-m" not in captured["cmd"]


def test_whisper_raises_engine_not_available_when_configured_path_missing(monkeypatch, tmp_path):
    """If the operator typo'd the path, fail closed with a helpful message
    *before* invoking the binary."""
    monkeypatch.setattr(
        settings, "voice_whisper_model_path", "/does/not/exist/ggml.bin"
    )
    audio_path = tmp_path / "test.wav"
    audio_path.write_bytes(b"fake")

    with patch("voice.stt.subprocess.run") as run_spy:
        with pytest.raises(stt_module.EngineNotAvailable, match="VOICE_WHISPER_MODEL_PATH"):
            stt_module.WhisperCppSTT().transcribe(audio_path=audio_path)
    run_spy.assert_not_called()


# ─── PiperTTS ───────────────────────────────────────────────────────────────


def test_piper_passes_model_flag(tmp_path, monkeypatch):
    """Adapter must build `piper --model <path> --output_file <wav>` so
    no wrapper script is needed."""
    real_model = tmp_path / "voice.onnx"
    real_model.write_bytes(b"fake-onnx")
    monkeypatch.setattr(settings, "voice_piper_model_path", str(real_model))
    monkeypatch.setattr(settings, "voice_audio_temp_dir", str(tmp_path / "audio"))
    monkeypatch.setattr(settings, "voice_tts_playback_command", "aplay")

    piper_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        piper_cmds.append(cmd)
        if cmd[0] == "piper":
            wav = Path(cmd[cmd.index("--output_file") + 1])
            wav.parent.mkdir(parents=True, exist_ok=True)
            wav.write_bytes(b"RIFF....WAVE")
        return _make_completed_process(0)

    with patch("voice.tts.subprocess.run", side_effect=fake_run):
        tts_module.PiperTTS().speak(text="hello")

    piper_cmd = [c for c in piper_cmds if c[0] == "piper"][0]
    assert "--model" in piper_cmd
    assert str(real_model) in piper_cmd
    assert "--output_file" in piper_cmd


def test_piper_passes_config_when_set(tmp_path, monkeypatch):
    """Optional VOICE_PIPER_CONFIG_PATH should be passed via `--config`
    when it points at a real file."""
    real_model = tmp_path / "voice.onnx"
    real_model.write_bytes(b"x")
    real_config = tmp_path / "voice.onnx.json"
    real_config.write_text("{}")
    monkeypatch.setattr(settings, "voice_piper_model_path", str(real_model))
    monkeypatch.setattr(settings, "voice_piper_config_path", str(real_config))
    monkeypatch.setattr(settings, "voice_audio_temp_dir", str(tmp_path / "audio"))
    monkeypatch.setattr(settings, "voice_tts_playback_command", "aplay")

    piper_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        piper_cmds.append(cmd)
        if cmd[0] == "piper":
            wav = Path(cmd[cmd.index("--output_file") + 1])
            wav.parent.mkdir(parents=True, exist_ok=True)
            wav.write_bytes(b"x")
        return _make_completed_process(0)

    with patch("voice.tts.subprocess.run", side_effect=fake_run):
        tts_module.PiperTTS().speak(text="hello")

    piper_cmd = [c for c in piper_cmds if c[0] == "piper"][0]
    assert "--config" in piper_cmd
    assert str(real_config) in piper_cmd


def test_piper_raises_when_model_path_empty(monkeypatch):
    monkeypatch.setattr(settings, "voice_piper_model_path", "")
    with patch("voice.tts.subprocess.run") as run_spy:
        with pytest.raises(tts_module.EngineNotAvailable, match="VOICE_PIPER_MODEL_PATH"):
            tts_module.PiperTTS().speak(text="hello")
    run_spy.assert_not_called()


def test_piper_raises_when_model_path_does_not_exist(monkeypatch):
    monkeypatch.setattr(
        settings, "voice_piper_model_path", "/nope/voice.onnx"
    )
    with patch("voice.tts.subprocess.run") as run_spy:
        with pytest.raises(tts_module.EngineNotAvailable, match="VOICE_PIPER_MODEL_PATH"):
            tts_module.PiperTTS().speak(text="hello")
    run_spy.assert_not_called()


# ─── Playback command selection ─────────────────────────────────────────────


def _make_speaking_piper(tmp_path, monkeypatch):
    """Common setup that wires up a fake Piper that writes a wav."""
    real_model = tmp_path / "voice.onnx"
    real_model.write_bytes(b"x")
    monkeypatch.setattr(settings, "voice_piper_model_path", str(real_model))
    monkeypatch.setattr(settings, "voice_audio_temp_dir", str(tmp_path / "audio"))


def test_piper_uses_paplay_when_explicitly_configured(tmp_path, monkeypatch):
    _make_speaking_piper(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "voice_tts_playback_command", "paplay")

    play_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        if cmd[0] == "piper":
            wav = Path(cmd[cmd.index("--output_file") + 1])
            wav.parent.mkdir(parents=True, exist_ok=True)
            wav.write_bytes(b"x")
        else:
            play_cmds.append(cmd)
        return _make_completed_process(0)

    with patch("voice.tts.subprocess.run", side_effect=fake_run):
        tts_module.PiperTTS().speak(text="hello")

    assert len(play_cmds) == 1
    assert play_cmds[0][0] == "paplay"


def test_piper_uses_aplay_when_explicitly_configured(tmp_path, monkeypatch):
    _make_speaking_piper(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "voice_tts_playback_command", "aplay")

    play_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        if cmd[0] == "piper":
            wav = Path(cmd[cmd.index("--output_file") + 1])
            wav.parent.mkdir(parents=True, exist_ok=True)
            wav.write_bytes(b"x")
        else:
            play_cmds.append(cmd)
        return _make_completed_process(0)

    with patch("voice.tts.subprocess.run", side_effect=fake_run):
        tts_module.PiperTTS().speak(text="hello")

    assert play_cmds[0][0] == "aplay"


def test_piper_auto_mode_prefers_paplay_when_available(tmp_path, monkeypatch):
    _make_speaking_piper(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "voice_tts_playback_command", "auto")

    play_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        if cmd[0] == "piper":
            wav = Path(cmd[cmd.index("--output_file") + 1])
            wav.parent.mkdir(parents=True, exist_ok=True)
            wav.write_bytes(b"x")
        else:
            play_cmds.append(cmd)
        return _make_completed_process(0)

    # which("paplay") returns a path → auto picks paplay.
    with patch("voice.tts.shutil.which", return_value="/usr/bin/paplay"), \
         patch("voice.tts.subprocess.run", side_effect=fake_run):
        tts_module.PiperTTS().speak(text="hello")

    assert play_cmds[0][0] == "paplay"


def test_piper_auto_mode_falls_back_to_aplay_when_paplay_missing(tmp_path, monkeypatch):
    _make_speaking_piper(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "voice_tts_playback_command", "auto")

    play_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        if cmd[0] == "piper":
            wav = Path(cmd[cmd.index("--output_file") + 1])
            wav.parent.mkdir(parents=True, exist_ok=True)
            wav.write_bytes(b"x")
        else:
            play_cmds.append(cmd)
        return _make_completed_process(0)

    # which("paplay") returns None → auto falls back to aplay.
    with patch("voice.tts.shutil.which", return_value=None), \
         patch("voice.tts.subprocess.run", side_effect=fake_run):
        tts_module.PiperTTS().speak(text="hello")

    assert play_cmds[0][0] == "aplay"


def test_playback_passes_device_with_correct_flag(tmp_path, monkeypatch):
    """aplay uses `-D`, paplay uses `--device`. Adapter must pick correctly."""
    _make_speaking_piper(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "voice_device_output", "plughw:0,0")
    monkeypatch.setattr(settings, "voice_tts_playback_command", "aplay")

    play_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        if cmd[0] == "piper":
            wav = Path(cmd[cmd.index("--output_file") + 1])
            wav.parent.mkdir(parents=True, exist_ok=True)
            wav.write_bytes(b"x")
        else:
            play_cmds.append(cmd)
        return _make_completed_process(0)

    with patch("voice.tts.subprocess.run", side_effect=fake_run):
        tts_module.PiperTTS().speak(text="hello")

    cmd = play_cmds[0]
    assert cmd[0] == "aplay"
    assert "-D" in cmd
    assert "plughw:0,0" in cmd

    # Now switch to paplay and confirm it uses --device instead of -D.
    monkeypatch.setattr(settings, "voice_tts_playback_command", "paplay")
    play_cmds.clear()
    with patch("voice.tts.subprocess.run", side_effect=fake_run):
        tts_module.PiperTTS().speak(text="hello")
    cmd = play_cmds[0]
    assert cmd[0] == "paplay"
    assert "--device" in cmd
    assert "plughw:0,0" in cmd
