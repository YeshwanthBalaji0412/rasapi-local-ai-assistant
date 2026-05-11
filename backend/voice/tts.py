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
import shutil
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


def _resolve_playback() -> str:
    """Pick the playback binary based on VOICE_TTS_PLAYBACK_COMMAND.

    - `paplay` and `aplay` are honoured verbatim.
    - `auto` (default) prefers paplay if available — PipeWire/PulseAudio
      routes Bluetooth output correctly through it; aplay can land on
      HDMI or the wrong card. Falls back to aplay otherwise.
    """
    mode = (settings.voice_tts_playback_command or "auto").strip().lower()
    if mode == "paplay":
        return "paplay"
    if mode == "aplay":
        return "aplay"
    # auto
    return "paplay" if shutil.which("paplay") else "aplay"


def _build_playback_command(wav_path: Path) -> list[str]:
    cmd = [_resolve_playback()]
    if settings.voice_device_output:
        # `aplay` uses `-D <device>`, `paplay` uses `--device <device>`.
        if cmd[0] == "aplay":
            cmd += ["-D", settings.voice_device_output]
        else:
            cmd += ["--device", settings.voice_device_output]
    cmd.append(str(wav_path))
    return cmd


class PiperTTS(TTSEngine):
    """Higher-quality TTS via Piper. Requires `piper` plus a configured
    ONNX voice model. Playback uses paplay or aplay depending on
    VOICE_TTS_PLAYBACK_COMMAND (default `auto` prefers paplay).

    Operator-required setting:
      VOICE_PIPER_MODEL_PATH=/absolute/path/to/voice.onnx

    Optional:
      VOICE_PIPER_CONFIG_PATH=/absolute/path/to/voice.onnx.json
        (only needed if the .onnx.json is not beside the .onnx file)
    """

    name = "piper"

    def speak(self, *, text: str) -> None:
        model_path = settings.voice_piper_model_path.strip()
        if not model_path or not Path(model_path).is_file():
            raise EngineNotAvailable(
                "Piper model not found. Set VOICE_PIPER_MODEL_PATH in backend/.env "
                "to a real .onnx file (e.g. ~/piper-voices/en_US-amy-low.onnx). "
                "The .onnx.json config file should sit beside the .onnx model, "
                "or set VOICE_PIPER_CONFIG_PATH explicitly."
            )

        wav_path = Path(settings.voice_audio_temp_dir) / "tts_out.wav"
        wav_path.parent.mkdir(parents=True, exist_ok=True)

        piper_cmd = ["piper", "--model", model_path]
        config_path = settings.voice_piper_config_path.strip()
        if config_path:
            if not Path(config_path).is_file():
                raise EngineNotAvailable(
                    "VOICE_PIPER_CONFIG_PATH is set but the file does not exist."
                )
            piper_cmd += ["--config", config_path]
        piper_cmd += ["--output_file", str(wav_path)]

        try:
            subprocess.run(
                piper_cmd,
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

        play_cmd = _build_playback_command(wav_path)
        try:
            subprocess.run(play_cmd, check=False, timeout=60)
        except FileNotFoundError as exc:
            raise EngineNotAvailable(
                f"{play_cmd[0]} not found — install with: "
                f"sudo apt install {'pulseaudio-utils' if play_cmd[0] == 'paplay' else 'alsa-utils'}"
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
