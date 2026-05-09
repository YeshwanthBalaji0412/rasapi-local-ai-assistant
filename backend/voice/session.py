"""
Voice session orchestration (Phase 7).

A single push-to-talk cycle:
    record  →  STT  →  process_query  →  TTS

Crucial security boundaries (verified by tests):
  - This module does NOT import subprocess.
  - This module does NOT import core.command_runner.
  - This module does NOT import core.local_llm directly.
  - All command/memory/briefing dispatch happens through
    `orchestration.process_query`, the same function /ask uses.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from config import settings
from core import orchestration
from security.audit_log import audit_logger
from voice import recorder as recorder_module
from voice import stt as stt_module
from voice import tts as tts_module


logger = logging.getLogger(__name__)


@dataclass
class VoiceResult:
    request_id: str
    transcript: str
    intent: str
    response: str
    source: str
    audio_saved: bool
    duration_ms: int


class VoiceDisabledError(Exception):
    """Voice features are off. Set ENABLE_VOICE=true to use them."""


def _truncate(text: str, n: int) -> str:
    if not text:
        return ""
    return text if len(text) <= n else text[:n]


async def run_session_once(
    *,
    request_id: str | None = None,
    seconds: int | None = None,
) -> VoiceResult:
    """
    Run one push-to-talk session end to end. Raises VoiceDisabledError if
    ENABLE_VOICE is false.
    """
    if not settings.enable_voice:
        raise VoiceDisabledError(
            "Voice is disabled (ENABLE_VOICE=false). Enable it in .env."
        )

    rid = request_id or f"voice-{uuid.uuid4()}"
    record_seconds = seconds if seconds is not None else settings.voice_record_seconds
    start = time.monotonic()

    audit_logger.log_voice_event(
        request_id=rid,
        event_type="voice_session_started",
        stt_engine=settings.voice_stt_engine,
        tts_engine=settings.voice_tts_engine,
    )

    audio_path: Path | None = None
    try:
        # ── 1. Record ──────────────────────────────────────────────────
        recorder = recorder_module.build_recorder()
        rec_start = time.monotonic()
        audio_path = recorder.record(seconds=record_seconds)
        rec_ms = int((time.monotonic() - rec_start) * 1000)
        audit_logger.log_voice_event(
            request_id=rid,
            event_type="voice_recording_completed",
            duration_ms=rec_ms,
        )

        # ── 2. Transcribe ──────────────────────────────────────────────
        stt_engine = stt_module.build_stt()
        stt_start = time.monotonic()
        raw_transcript = stt_engine.transcribe(audio_path=audio_path)
        transcript = _truncate(
            (raw_transcript or "").strip(), settings.voice_max_transcript_chars
        )
        stt_ms = int((time.monotonic() - stt_start) * 1000)
        audit_logger.log_voice_event(
            request_id=rid,
            event_type="voice_transcription_completed",
            stt_engine=settings.voice_stt_engine,
            duration_ms=stt_ms,
            transcript_length=len(transcript),
        )

        if not transcript:
            response_text = "I didn't catch that. Try again."
            intent = "voice_no_input"
            source = "local"
        else:
            # ── 3. Route through the SAME orchestration as /ask ────────
            if settings.voice_log_transcripts:
                audit_logger.log_request(request_id=rid, query=transcript)
            intent, response_text, source = await orchestration.process_query(
                query=transcript, request_id=rid
            )

        # ── 4. Speak ───────────────────────────────────────────────────
        tts_engine = tts_module.build_tts()
        tts_start = time.monotonic()
        tts_engine.speak(text=response_text)
        tts_ms = int((time.monotonic() - tts_start) * 1000)
        audit_logger.log_voice_event(
            request_id=rid,
            event_type="voice_tts_completed",
            tts_engine=settings.voice_tts_engine,
            duration_ms=tts_ms,
        )

        # ── 5. Cleanup audio ───────────────────────────────────────────
        audio_saved = settings.voice_save_audio
        if not audio_saved and audio_path is not None:
            try:
                os.remove(audio_path)
            except OSError as exc:
                logger.warning("Could not delete temp audio %s: %s", audio_path, exc)

        total_ms = int((time.monotonic() - start) * 1000)
        audit_logger.log_voice_event(
            request_id=rid,
            event_type="voice_session_completed",
            stt_engine=settings.voice_stt_engine,
            tts_engine=settings.voice_tts_engine,
            duration_ms=total_ms,
            transcript_length=len(transcript),
            audio_saved=audio_saved,
        )

        return VoiceResult(
            request_id=rid,
            transcript=transcript,
            intent=intent,
            response=response_text,
            source=source,
            audio_saved=audio_saved,
            duration_ms=total_ms,
        )

    except Exception as exc:
        # On any failure, audit and clean up audio (unless save flag is on).
        total_ms = int((time.monotonic() - start) * 1000)
        audit_logger.log_voice_event(
            request_id=rid,
            event_type="voice_session_failed",
            outcome="error",
            stt_engine=settings.voice_stt_engine,
            tts_engine=settings.voice_tts_engine,
            duration_ms=total_ms,
            reason=f"{type(exc).__name__}: {str(exc)[:160]}",
        )
        if audio_path is not None and not settings.voice_save_audio:
            try:
                os.remove(audio_path)
            except OSError:
                pass
        raise
