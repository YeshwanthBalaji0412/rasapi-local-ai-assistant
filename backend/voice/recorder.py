"""
Audio recorder adapters (Phase 7).

Engines:
  - mock      → writes a tiny placeholder file (no real recording)
  - arecord   → shells out to ALSA's arecord (Pi/Linux production)
  - sounddevice → optional cross-platform recorder

This is the ONE place in `voice/` that may import subprocess. The
session module never imports it.
"""

from __future__ import annotations

import logging
import subprocess
import uuid
from pathlib import Path

from config import settings


logger = logging.getLogger(__name__)


class RecorderError(Exception):
    """A recording attempt could not complete."""


class EngineNotAvailable(RecorderError):
    """The configured engine is not installed or not configured."""


def _ensure_temp_dir() -> Path:
    p = Path(settings.voice_audio_temp_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _new_audio_path() -> Path:
    return _ensure_temp_dir() / f"{uuid.uuid4()}.wav"


# ─── interfaces ──────────────────────────────────────────────────────────────


class AudioRecorder:
    """Subclasses implement record(seconds) -> path-to-wav."""

    name = "base"

    def record(self, *, seconds: int) -> Path:  # pragma: no cover - abstract
        raise NotImplementedError


# ─── mock ────────────────────────────────────────────────────────────────────


class MockRecorder(AudioRecorder):
    """Writes a minimal placeholder file. Used in tests and as the safe default."""

    name = "mock"

    def record(self, *, seconds: int) -> Path:
        path = _new_audio_path()
        # Write a tiny placeholder so downstream "file exists" checks pass.
        path.write_bytes(b"MOCK_AUDIO")
        return path


# ─── arecord ─────────────────────────────────────────────────────────────────


class ArecordRecorder(AudioRecorder):
    """ALSA arecord. Used on Raspberry Pi / Linux."""

    name = "arecord"

    def record(self, *, seconds: int) -> Path:
        path = _new_audio_path()
        cmd = ["arecord"]
        if settings.voice_device_input:
            cmd += ["-D", settings.voice_device_input]
        cmd += [
            "-d", str(int(seconds)),
            "-f", "S16_LE",
            "-c", "1",
            "-r", "16000",
            str(path),
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=seconds + 5, check=False
            )
        except FileNotFoundError as exc:
            raise EngineNotAvailable(
                "arecord not found — install ALSA tools (apt install alsa-utils)"
            ) from exc
        if result.returncode != 0:
            raise RecorderError(
                f"arecord exit {result.returncode}: {result.stderr.strip()[:200]}"
            )
        return path


# ─── factory ─────────────────────────────────────────────────────────────────


_REGISTRY: dict[str, type[AudioRecorder]] = {
    "mock": MockRecorder,
    "arecord": ArecordRecorder,
}


def build_recorder() -> AudioRecorder:
    name = settings.voice_recorder_engine or "mock"
    cls = _REGISTRY.get(name)
    if cls is None:
        raise EngineNotAvailable(
            f"unknown VOICE_RECORDER_ENGINE={name!r} (known: {sorted(_REGISTRY)})"
        )
    return cls()
