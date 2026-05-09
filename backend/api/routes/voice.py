"""
Voice REST endpoints (Phase 7).

  - GET  /voice/status         → safe config snapshot
  - POST /voice/test-tts       → speak a string via the configured TTS engine
  - POST /voice/session-once   → one push-to-talk cycle (record → STT → /ask → TTS)

`/voice/session-once` returns 403 unless ENABLE_VOICE=true. All endpoints
are local-only by Phase 6 deployment posture (systemd binds 127.0.0.1).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from config import settings
from security import auth as auth_module
from voice import session as session_module
from voice import tts as tts_module


router = APIRouter(prefix="/voice", tags=["voice"])


class VoiceStatusResponse(BaseModel):
    enabled: bool
    recorder_engine: str
    stt_engine: str
    tts_engine: str
    record_seconds: int
    save_audio: bool
    log_transcripts: bool
    push_to_talk_required: bool
    max_transcript_chars: int


class TestTTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class TestTTSResponse(BaseModel):
    spoken: bool
    engine: str
    detail: str | None = None


class VoiceSessionResponse(BaseModel):
    request_id: str
    transcript: str
    intent: str
    response: str
    source: str
    audio_saved: bool
    duration_ms: int


@router.get("/status", response_model=VoiceStatusResponse)
def get_status() -> VoiceStatusResponse:
    return VoiceStatusResponse(
        enabled=settings.enable_voice,
        recorder_engine=settings.voice_recorder_engine,
        stt_engine=settings.voice_stt_engine,
        tts_engine=settings.voice_tts_engine,
        record_seconds=settings.voice_record_seconds,
        save_audio=settings.voice_save_audio,
        log_transcripts=settings.voice_log_transcripts,
        push_to_talk_required=settings.voice_require_push_to_talk,
        max_transcript_chars=settings.voice_max_transcript_chars,
    )


@router.post(
    "/test-tts",
    response_model=TestTTSResponse,
    dependencies=[Depends(auth_module.require_auth_for_voice)],
)
def post_test_tts(body: TestTTSRequest) -> TestTTSResponse:
    if not settings.enable_voice:
        raise HTTPException(status_code=403, detail="voice disabled")
    try:
        engine = tts_module.build_tts()
        engine.speak(text=body.text)
    except tts_module.EngineNotAvailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except tts_module.TTSError as exc:
        raise HTTPException(status_code=500, detail=f"tts error: {exc}") from exc
    return TestTTSResponse(spoken=True, engine=engine.name)


@router.post(
    "/session-once",
    response_model=VoiceSessionResponse,
    dependencies=[Depends(auth_module.require_auth_for_voice)],
)
async def post_session_once() -> VoiceSessionResponse:
    if not settings.enable_voice:
        raise HTTPException(status_code=403, detail="voice disabled")
    try:
        result = await session_module.run_session_once()
    except session_module.VoiceDisabledError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"voice session failed: {exc}"
        ) from exc
    return VoiceSessionResponse(
        request_id=result.request_id,
        transcript=result.transcript,
        intent=result.intent,
        response=result.response,
        source=result.source,
        audio_saved=result.audio_saved,
        duration_ms=result.duration_ms,
    )
