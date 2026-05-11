"""
Speech-to-text adapters (Phase 7).

Engines:
  - mock      → returns DEFAULT_MOCK_TRANSCRIPT (test/dev only)
  - whisper   → shells out to whisper-cli (whisper.cpp build); reads .txt output

This is the ONE place in `voice/` that may import subprocess for STT.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from config import settings


logger = logging.getLogger(__name__)


class STTError(Exception):
    """Transcription could not complete."""


class EngineNotAvailable(STTError):
    """The configured engine is not installed."""


# Module-level constant so tests can monkeypatch the mock transcript.
DEFAULT_MOCK_TRANSCRIPT = "hello"


# ─── interfaces ──────────────────────────────────────────────────────────────


class STTEngine:
    """Subclasses implement transcribe(audio_path) -> text."""

    name = "base"

    def transcribe(self, *, audio_path: Path) -> str:  # pragma: no cover - abstract
        raise NotImplementedError


# ─── mock ────────────────────────────────────────────────────────────────────


class MockSTT(STTEngine):
    name = "mock"

    def transcribe(self, *, audio_path: Path) -> str:
        return DEFAULT_MOCK_TRANSCRIPT


# ─── whisper.cpp ─────────────────────────────────────────────────────────────


class WhisperCppSTT(STTEngine):
    """Wraps the `whisper-cli` binary built from https://github.com/ggerganov/whisper.cpp

    If `VOICE_WHISPER_MODEL_PATH` is set, the model is passed explicitly
    via `-m`. If empty, the adapter leaves model selection to whisper-cli
    (which looks under `./models/` by convention). The explicit path is
    the recommended deployment — it avoids the symlink dance.
    """

    name = "whisper"

    def transcribe(self, *, audio_path: Path) -> str:
        model_path = settings.voice_whisper_model_path.strip()
        if model_path and not Path(model_path).is_file():
            raise EngineNotAvailable(
                "Whisper model not found. Set VOICE_WHISPER_MODEL_PATH in backend/.env "
                "to a real .bin file (e.g. ~/whisper.cpp/models/ggml-tiny.en.bin)."
            )

        out_prefix = audio_path.with_suffix("")
        cmd = ["whisper-cli"]
        if model_path:
            cmd += ["-m", model_path]
        cmd += [
            "-f", str(audio_path),
            "-otxt",
            "-of", str(out_prefix),
            "-l", "auto",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, check=False
            )
        except FileNotFoundError as exc:
            raise EngineNotAvailable(
                "whisper-cli not found — see audio-setup.md to build whisper.cpp"
            ) from exc
        if result.returncode != 0:
            raise STTError(
                f"whisper-cli exit {result.returncode}: {result.stderr.strip()[:200]}"
            )
        txt_path = out_prefix.with_suffix(".txt")
        if not txt_path.exists():
            raise STTError("whisper-cli completed but no transcript file was written")
        text = txt_path.read_text(encoding="utf-8").strip()
        try:
            txt_path.unlink()
        except OSError:
            pass
        return text


# ─── factory ─────────────────────────────────────────────────────────────────


_REGISTRY: dict[str, type[STTEngine]] = {
    "mock": MockSTT,
    "whisper": WhisperCppSTT,
}


def build_stt() -> STTEngine:
    name = settings.voice_stt_engine or "mock"
    cls = _REGISTRY.get(name)
    if cls is None:
        raise EngineNotAvailable(
            f"unknown VOICE_STT_ENGINE={name!r} (known: {sorted(_REGISTRY)})"
        )
    return cls()
