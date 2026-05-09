"""
Text-to-speech adapters (Phase 7).

Engines:
  - mock     → records spoken text in an in-memory list (test/dev)
  - espeak   → shells out to `espeak-ng` (lightweight, ships in apt)
  - piper    → shells out to `piper` then `aplay` (better quality, optional)

This is the ONE place in `voice/` that may import subprocess for TTS.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from config import settings


logger = logging.getLogger(__name__)


class TTSError(Exception):
    """A TTS attempt could not complete."""


class EngineNotAvailable(TTSError):
    """The configured engine is not installed."""


# ─── interfaces ──────────────────────────────────────────────────────────────


class TTSEngine:
    """Subclasses implement speak(text)."""

    name = "base"

    def speak(self, *, text: str) -> None:  # pragma: no cover - abstract
        raise NotImplementedError


# ─── mock ────────────────────────────────────────────────────────────────────


class MockTTS(TTSEngine):
    """Records spoken text in memory. Used in tests and as the safe default."""

    name = "mock"
    spoken: list[str] = []  # class-level so tests can inspect across instances

    def speak(self, *, text: str) -> None:
        type(self).spoken.append(text)


def reset_mock_history() -> None:
    """Clear MockTTS.spoken between tests."""
    MockTTS.spoken.clear()


# ─── espeak-ng ───────────────────────────────────────────────────────────────


class EspeakTTS(TTSEngine):
    """Lightweight TTS via `espeak-ng`. Robotic but reliable."""

    name = "espeak"

    def speak(self, *, text: str) -> None:
        cmd = ["espeak-ng"]
        if settings.voice_device_output:
            # espeak-ng doesn't take a device flag directly; rely on system
            # ALSA default. Operator can set ALSA env vars instead.
            pass
        cmd.append(text)
        try:
            subprocess.run(cmd, check=False, timeout=60)
        except FileNotFoundError as exc:
            raise EngineNotAvailable(
                "espeak-ng not found — install with: sudo apt install espeak-ng"
            ) from exc


# ─── piper ───────────────────────────────────────────────────────────────────


class PiperTTS(TTSEngine):
    """Higher-quality TTS via Piper. Requires both `piper` and `aplay` in PATH
    plus an ONNX voice model file (see audio-setup.md).
    """

    name = "piper"

    def speak(self, *, text: str) -> None:
        wav_path = Path(settings.voice_audio_temp_dir) / "tts_out.wav"
        wav_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            subprocess.run(
                ["piper", "--output_file", str(wav_path)],
                input=text,
                text=True,
                check=False,
                timeout=60,
            )
        except FileNotFoundError as exc:
            raise EngineNotAvailable(
                "piper not found — see audio-setup.md to install Piper TTS"
            ) from exc

        if not wav_path.exists():
            raise TTSError("piper completed but produced no output file")

        try:
            play_cmd = ["aplay"]
            if settings.voice_device_output:
                play_cmd += ["-D", settings.voice_device_output]
            play_cmd.append(str(wav_path))
            subprocess.run(play_cmd, check=False, timeout=60)
        except FileNotFoundError as exc:
            raise EngineNotAvailable(
                "aplay not found — install with: sudo apt install alsa-utils"
            ) from exc
        finally:
            try:
                wav_path.unlink()
            except OSError:
                pass


# ─── factory ─────────────────────────────────────────────────────────────────


_REGISTRY: dict[str, type[TTSEngine]] = {
    "mock": MockTTS,
    "espeak": EspeakTTS,
    "piper": PiperTTS,
}


def build_tts() -> TTSEngine:
    name = settings.voice_tts_engine or "mock"
    cls = _REGISTRY.get(name)
    if cls is None:
        raise EngineNotAvailable(
            f"unknown VOICE_TTS_ENGINE={name!r} (known: {sorted(_REGISTRY)})"
        )
    return cls()
