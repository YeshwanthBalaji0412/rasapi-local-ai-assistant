import time
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from config import settings
from core import local_llm
from core.intent_router import route, list_intents
from security.audit_log import audit_logger


router = APIRouter(tags=["assistant"])


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)


class AskResponse(BaseModel):
    request_id: str
    intent: str
    response: str
    source: str
    duration_ms: int


class CommandsResponse(BaseModel):
    intents: list[dict]


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest) -> AskResponse:
    request_id = str(uuid.uuid4())
    start = time.monotonic()

    audit_logger.log_request(request_id=request_id, query=body.query)

    # Layer 1: deterministic router. Always runs first. Known intents
    # short-circuit here and never reach the LLM.
    routed = route(query=body.query, request_id=request_id)
    intent = routed.intent
    response_text = routed.response
    source = "local"

    # Phase 2: only fallback queries are eligible for the LLM, and only
    # when the operator has explicitly opted in.
    if routed.intent == "fallback" and settings.enable_local_llm:
        intent, response_text, source = await _try_local_llm(
            request_id=request_id, query=body.query
        )

    duration_ms = int((time.monotonic() - start) * 1000)

    return AskResponse(
        request_id=request_id,
        intent=intent,
        response=response_text,
        source=source,
        duration_ms=duration_ms,
    )


@router.get("/commands", response_model=CommandsResponse)
async def commands() -> CommandsResponse:
    return CommandsResponse(intents=list_intents())


async def _try_local_llm(*, request_id: str, query: str) -> tuple[str, str, str]:
    """
    Attempt the local LLM fallback. Returns (intent, response_text, source).
    On any failure, returns a static safe message — never re-raises.

    The LLM response is treated as opaque conversational text. It is never
    parsed, matched against commands, or passed to the command runner.
    """
    llm_start = time.monotonic()
    try:
        text = await local_llm.generate_chat_response(query=query)
        duration_ms = int((time.monotonic() - llm_start) * 1000)
        audit_logger.log_llm_call(
            request_id=request_id,
            model=settings.local_llm_model,
            outcome="success",
            duration_ms=duration_ms,
        )
        return "llm_fallback", text, "local_llm"

    except local_llm.LocalLLMTimeout:
        duration_ms = int((time.monotonic() - llm_start) * 1000)
        audit_logger.log_llm_call(
            request_id=request_id,
            model=settings.local_llm_model,
            outcome="error",
            duration_ms=duration_ms,
            reason="timeout",
        )
        return "llm_unavailable", local_llm.safe_fallback_message(), "local"

    except local_llm.LocalLLMUnavailable as exc:
        duration_ms = int((time.monotonic() - llm_start) * 1000)
        audit_logger.log_llm_call(
            request_id=request_id,
            model=settings.local_llm_model,
            outcome="error",
            duration_ms=duration_ms,
            reason=str(exc)[:200],
        )
        return "llm_unavailable", local_llm.safe_fallback_message(), "local"
