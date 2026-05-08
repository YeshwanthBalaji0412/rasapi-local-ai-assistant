"""
Ollama LLM client.

Phase 1: returns a stub response so the rest of the stack can be tested
without Ollama installed. Phase 2 replaces _call_ollama with a real
httpx request to the Ollama /api/generate endpoint.
"""

import logging

from config import settings


logger = logging.getLogger(__name__)

_STUB_MODE = True  # flipped to False in Phase 2


async def generate(prompt: str) -> str:
    if _STUB_MODE:
        logger.debug("LLM stub mode — echoing prompt")
        return f"[stub] You said: {prompt!r}. (Connect Ollama in Phase 2.)"

    return await _call_ollama(prompt)  # pragma: no cover


async def _call_ollama(prompt: str) -> str:  # pragma: no cover
    import httpx

    url = f"{settings.ollama_base_url}/api/generate"
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()["response"]
