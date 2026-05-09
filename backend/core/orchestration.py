"""
Query orchestration (Phase 7 extraction).

Single source of truth for "given a query, produce (intent, response, source)".
Both the HTTP `/ask` route and the voice session call this. Voice cannot
introduce a new dispatch path — it uses the same router → allowlist →
LLM-fallback pipeline as text input.

The function is async so the optional LLM fallback can use httpx.AsyncClient.
For sync callers (e.g. the voice CLI), wrap with asyncio.run.
"""

from __future__ import annotations

import logging
import time

from config import settings
from core import local_llm
from core.intent_router import route
from security.audit_log import audit_logger


logger = logging.getLogger(__name__)


async def process_query(*, query: str, request_id: str) -> tuple[str, str, str]:
    """
    Run a query through the deterministic router and (if enabled) the LLM
    fallback. Returns (intent, response_text, source).

      - source == "local"     → handler/command/built-in handled the query
      - source == "local_llm" → Ollama answered (only when fallback + opt-in)
      - intent == "fallback"  → no router match, LLM disabled
      - intent == "llm_unavailable" → LLM was tried and failed gracefully
    """
    routed = route(query=query, request_id=request_id)
    intent = routed.intent
    response_text = routed.response
    source = "local"

    if routed.intent == "fallback" and settings.enable_local_llm:
        intent, response_text, source = await _try_local_llm(
            request_id=request_id, query=query
        )

    return intent, response_text, source


async def _try_local_llm(*, request_id: str, query: str) -> tuple[str, str, str]:
    """LLM fallback. Always returns; never re-raises. See Phase 2 docs."""
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
