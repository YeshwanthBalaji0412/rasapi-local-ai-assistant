"""
Voice CLI (Phase 7).

Run with:
    python -m voice.cli status
    python -m voice.cli record-test
    python -m voice.cli stt-test --audio /path/to/file.wav
    python -m voice.cli tts-test "Hello, I am RasaPi"
    python -m voice.cli once

This module does NOT import subprocess or core.command_runner.
It only uses the voice/* engines and orchestration.process_query.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from config import settings
from voice import recorder as recorder_module
from voice import session as session_module
from voice import stt as stt_module
from voice import tts as tts_module


def _print_status() -> int:
    print("RasaPi voice — configuration")
    print(f"  ENABLE_VOICE       = {settings.enable_voice}")
    print(f"  RECORDER_ENGINE    = {settings.voice_recorder_engine}")
    print(f"  STT_ENGINE         = {settings.voice_stt_engine}")
    print(f"  TTS_ENGINE         = {settings.voice_tts_engine}")
    print(f"  RECORD_SECONDS     = {settings.voice_record_seconds}")
    print(f"  SAVE_AUDIO         = {settings.voice_save_audio}")
    print(f"  LOG_TRANSCRIPTS    = {settings.voice_log_transcripts}")
    print(f"  PUSH_TO_TALK       = {settings.voice_require_push_to_talk}")
    print(f"  AUDIO_TEMP_DIR     = {settings.voice_audio_temp_dir}")
    print(f"  DEVICE_INPUT       = {settings.voice_device_input or '(default)'}")
    print(f"  DEVICE_OUTPUT      = {settings.voice_device_output or '(default)'}")
    return 0


def _record_test() -> int:
    rec = recorder_module.build_recorder()
    print(f"Recording {settings.voice_record_seconds}s using engine={rec.name}...")
    path = rec.record(seconds=settings.voice_record_seconds)
    print(f"  wrote {path}")
    return 0


def _stt_test(audio: str | None) -> int:
    engine = stt_module.build_stt()
    if not audio:
        # Use the recorder to capture, then transcribe.
        rec = recorder_module.build_recorder()
        print(f"No --audio given; recording first using engine={rec.name}...")
        audio_path = rec.record(seconds=settings.voice_record_seconds)
    else:
        audio_path = Path(audio)
    print(f"Transcribing with engine={engine.name}...")
    text = engine.transcribe(audio_path=audio_path)
    print(f"  transcript: {text!r}")
    return 0


def _tts_test(text: str) -> int:
    engine = tts_module.build_tts()
    print(f"Speaking with engine={engine.name}: {text!r}")
    engine.speak(text=text)
    return 0


async def _once_async() -> int:
    print("Starting one voice session (record → STT → /ask → TTS)...")
    try:
        result = await session_module.run_session_once()
    except session_module.VoiceDisabledError as exc:
        print(f"Voice disabled: {exc}", file=sys.stderr)
        return 2
    print(f"  request_id  = {result.request_id}")
    print(f"  transcript  = {result.transcript!r}")
    print(f"  intent      = {result.intent}")
    print(f"  source      = {result.source}")
    print(f"  audio_saved = {result.audio_saved}")
    print(f"  duration_ms = {result.duration_ms}")
    print(f"  response    = {result.response}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voice.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="show voice configuration")
    sub.add_parser("record-test", help="record a short clip via the configured engine")
    p = sub.add_parser("stt-test", help="transcribe audio via the configured STT engine")
    p.add_argument("--audio", help="path to a wav file (records one if omitted)")
    p = sub.add_parser("tts-test", help="speak the given text via the configured TTS engine")
    p.add_argument("text", help="text to speak")
    sub.add_parser("once", help="record → STT → /ask → TTS in one cycle")

    args = parser.parse_args(argv)

    if args.cmd == "status":
        return _print_status()
    if args.cmd == "record-test":
        return _record_test()
    if args.cmd == "stt-test":
        return _stt_test(args.audio)
    if args.cmd == "tts-test":
        return _tts_test(args.text)
    if args.cmd == "once":
        return asyncio.run(_once_async())
    return 1  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
