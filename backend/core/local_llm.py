"""
Local LLM client (Ollama).

Used as a Phase 2 conversational fallback for queries that the deterministic
intent router cannot match. The function in this module returns plain text
only and is never wired to any executor — by design, this file does not
import command_runner, allowlist, or subprocess. The LLM cannot escalate.

Security invariants:
  - Output is treated as opaque conversational text.
  - System prompt is hard-coded; user input cannot override it.
  - User query is the ONLY content sent to the model. Settings, env vars,
    audit logs, and filesystem are never read or transmitted.
  - Network errors and timeouts surface as typed exceptions so the route
    handler can degrade gracefully.
"""

import logging

import httpx

from config import settings


logger = logging.getLogger(__name__)


# Hard-coded system prompt. Treats the LLM as a pure conversational responder
# and tells it explicitly that it has no execution capability. The real
# enforcement is structural (no executor is reachable from this module);
# the prompt is just polish to reduce confused outputs.
SYSTEM_PROMPT = (
    "You are RasaPi, a local conversational assistant running on a "
    "Raspberry Pi. You CANNOT execute commands, access files, modify the "
    "system, or take any action. The user's system tools are handled by a "
    "separate router that only invokes pre-approved commands. Reply only "
    "with plain conversational text. Do not output shell commands, code "
    "blocks intended for execution, or instructions to run code."
)


_MAX_QUERY_CHARS = 2000
_SAFE_FALLBACK_MESSAGE = (
    "The local language model is unavailable right now. I can still answer "
    "system-status questions like 'what time is it' or 'how much disk space "
    "do I have'. Try 'help' to see what I can do."
)


class LocalLLMError(Exception):
    """Base class for local LLM failures."""


class LocalLLMUnavailable(LocalLLMError):
    """Ollama is not reachable, returned a non-success status, or sent an unparseable body."""


class LocalLLMTimeout(LocalLLMError):
    """Ollama did not respond within LOCAL_LLM_TIMEOUT_SECONDS."""


def safe_fallback_message() -> str:
    """The static message returned to the user when the LLM is unavailable."""
    return _SAFE_FALLBACK_MESSAGE


def _sanitize(query: str) -> str:
    # Remove ASCII control characters; truncate length. Pydantic already caps
    # the query at the API boundary, but we apply defense-in-depth here.
    cleaned = "".join(ch for ch in query if ch >= " " or ch == "\n")
    return cleaned[:_MAX_QUERY_CHARS]


async def generate_chat_response(query: str) -> str:
    """
    Send `query` to the local Ollama instance and return the assistant's text.

    Raises:
        LocalLLMTimeout: the request did not complete within the configured timeout.
        LocalLLMUnavailable: connection refused, network error, non-2xx status,
            or response body could not be parsed.

    The return value is a string. There is no overload that returns a
    structured tool call — by signature, this function cannot deliver
    something executable.
    """
    sanitized = _sanitize(query)

    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": settings.local_llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": sanitized},
        ],
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.local_llm_timeout_seconds) as client:
            response = await client.post(url, json=payload)
    except httpx.TimeoutException as exc:
        logger.warning("Ollama request timed out after %ss", settings.local_llm_timeout_seconds)
        raise LocalLLMTimeout("ollama request timed out") from exc
    except httpx.RequestError as exc:
        logger.warning("Ollama connection error: %s", exc)
        raise LocalLLMUnavailable(f"ollama connection error: {exc}") from exc

    if response.status_code >= 400:
        logger.warning("Ollama returned HTTP %s", response.status_code)
        raise LocalLLMUnavailable(f"ollama http {response.status_code}")

    try:
        data = response.json()
        text = data["message"]["content"]
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("Ollama response unparseable: %s", exc)
        raise LocalLLMUnavailable("ollama returned unparseable body") from exc

    if not isinstance(text, str) or not text.strip():
        raise LocalLLMUnavailable("ollama returned empty content")

    return text.strip()


# ─── Phase 4: synchronous briefing-summary helper ─────────────────────────────


_BRIEFING_SYSTEM_PROMPT = (
    "You are summarizing public news headlines into a 2-3 sentence digest. "
    "Reply with plain text only. Do not output commands, code, or "
    "instructions to run code. Keep it factual and brief."
)


def generate_briefing_summary(headlines: list[str]) -> str:
    """
    Synchronous Ollama call used only by the briefing generator when both
    ENABLE_LOCAL_LLM and ENABLE_LLM_BRIEFING_SUMMARY are true.

    `headlines` must contain ONLY public source content (titles + source
    names). Memory, notes, tasks, audit logs, and env values must never
    appear here.
    """
    if not headlines:
        return ""

    user_msg = "Summarize these headlines:\n" + "\n".join(
        f"- {h}" for h in headlines[:30]
    )

    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": settings.local_llm_model,
        "messages": [
            {"role": "system", "content": _BRIEFING_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
    }

    try:
        with httpx.Client(timeout=settings.local_llm_timeout_seconds) as client:
            response = client.post(url, json=payload)
        if response.status_code >= 400:
            raise LocalLLMUnavailable(f"ollama http {response.status_code}")
        data = response.json()
        text = data["message"]["content"]
    except httpx.TimeoutException as exc:
        raise LocalLLMTimeout("briefing summary timed out") from exc
    except (httpx.RequestError, ValueError, KeyError, TypeError) as exc:
        raise LocalLLMUnavailable(f"ollama error: {exc}") from exc

    if not isinstance(text, str) or not text.strip():
        raise LocalLLMUnavailable("ollama returned empty content")
    return text.strip()
