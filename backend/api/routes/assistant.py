"""
Assistant routes.

  POST /ask                      → JSON API entry point (Phase 1)
  GET  /commands                 → list of allowlisted intents (Phase 1)

Phase 11 additions — browser-friendly interaction surface:
  GET  /assistant                → server-rendered chat page
  POST /assistant/ask            → form POST; runs orchestration.process_query
  POST /assistant/voice-trigger  → form POST; runs one voice session on the Pi

Security invariants (verified by tests):
  - This module imports ONLY orchestration.process_query for query handling.
  - It does NOT import command_runner or local_llm directly.
  - The Phase 11 POST routes reuse the same auth deps that already protect
    /ask and /voice/session-once.
  - CSRF is required for cookie-authenticated browser POSTs; skipped for
    API-key header POSTs (verify_csrf_for_api).
  - Chat history is in-memory only and never reaches the executor.
"""

import time
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from config import settings
from core import chat_history, orchestration
from core.intent_router import list_intents
from security import auth as auth_module
from security.audit_log import audit_logger
from voice import session as voice_session


router = APIRouter(tags=["assistant"])


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


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


@router.post(
    "/ask",
    response_model=AskResponse,
    dependencies=[Depends(auth_module.require_auth_for_ask)],
)
async def ask(body: AskRequest) -> AskResponse:
    request_id = str(uuid.uuid4())
    start = time.monotonic()

    audit_logger.log_request(request_id=request_id, query=body.query)

    intent, response_text, source = await orchestration.process_query(
        query=body.query, request_id=request_id
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


# ─── Phase 11 — /assistant page ──────────────────────────────────────────────


def _session_key(request: Request) -> str:
    """Pick a chat-history bucket key.

    When auth is on, use the signed session cookie value (rotates whenever
    the operator rotates API_SECRET_KEY, which already invalidates cookies).
    When auth is off, fall back to client host — single-user local-dev only.
    """
    if settings.enable_auth:
        return request.cookies.get(settings.session_cookie_name, "")
    client = request.client
    return f"ip:{client.host}" if client else "ip:unknown"


def _login_redirect(request: Request) -> RedirectResponse:
    next_path = quote(request.url.path or "/assistant", safe="/")
    return RedirectResponse(url=f"/login?next={next_path}", status_code=303)


def _check_browser_auth(request: Request) -> RedirectResponse | None:
    if auth_module.is_dashboard_authenticated(request):
        return None
    audit_logger.log_auth_event(
        request_id=auth_module._audit_id(),
        event_type="auth_required_missing",
        outcome="error",
        reason="assistant_no_session",
    )
    return _login_redirect(request)


async def _check_csrf_browser_or_header(request: Request) -> dict[str, str]:
    form = await auth_module.read_form(request)
    if not auth_module.verify_csrf_for_api(request, form):
        audit_logger.log_auth_event(
            request_id=auth_module._audit_id(),
            event_type="csrf_validation_failed",
            outcome="error",
            reason="assistant_csrf_mismatch",
        )
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    return form


def _render_page(
    request: Request,
    *,
    csrf_token: str,
    error: str | None = None,
    last_voice_result: dict | None = None,
):
    history = chat_history.recent(_session_key(request))
    context = {
        "assistant_name": settings.assistant_name,
        "csrf_token": csrf_token,
        "history": history,
        "voice_enabled": settings.enable_voice,
        "auth_enabled": settings.enable_auth,
        "error": error,
        "last_voice_result": last_voice_result,
        "max_query_chars": 2000,
    }
    return templates.TemplateResponse(
        request=request, name="assistant.html", context=context
    )


def _csrf_for_render(request: Request):
    existing = request.cookies.get(settings.csrf_cookie_name)
    if existing and len(existing) >= 16:
        return existing, False
    return auth_module.issue_csrf_token(), True


def _attach_csrf_cookie(response, token: str) -> None:
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token,
        max_age=settings.session_ttl_minutes * 60,
        httponly=False,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


@router.get("/assistant", response_class=HTMLResponse)
def get_assistant(request: Request):
    redirect = _check_browser_auth(request)
    if redirect is not None:
        return redirect

    csrf_token, fresh = _csrf_for_render(request)
    audit_logger.log_dashboard_event(
        request_id=f"asst-{uuid.uuid4()}", event_type="assistant_viewed"
    )
    response = _render_page(request, csrf_token=csrf_token)
    if fresh:
        _attach_csrf_cookie(response, csrf_token)
    return response


@router.post(
    "/assistant/ask",
    dependencies=[Depends(auth_module.require_auth_for_ask)],
)
async def post_assistant_ask(request: Request):
    form = await _check_csrf_browser_or_header(request)
    query = (form.get("query") or "").strip()
    if not query:
        csrf_token, fresh = _csrf_for_render(request)
        response = _render_page(
            request, csrf_token=csrf_token, error="Type a message before sending."
        )
        if fresh:
            _attach_csrf_cookie(response, csrf_token)
        return response
    if len(query) > 2000:
        query = query[:2000]

    request_id = f"asst-{uuid.uuid4()}"
    audit_logger.log_request(request_id=request_id, query=query)
    intent, response_text, source = await orchestration.process_query(
        query=query, request_id=request_id
    )

    chat_history.append(
        _session_key(request),
        chat_history.Exchange(
            query=query, response=response_text, intent=intent, source=source
        ),
    )

    return RedirectResponse(url="/assistant", status_code=303)


@router.post(
    "/assistant/voice-trigger",
    dependencies=[Depends(auth_module.require_auth_for_voice)],
)
async def post_assistant_voice_trigger(request: Request):
    await _check_csrf_browser_or_header(request)
    if not settings.enable_voice:
        raise HTTPException(status_code=403, detail="voice disabled")

    audit_logger.log_dashboard_event(
        request_id=f"asst-{uuid.uuid4()}",
        event_type="assistant_voice_trigger_requested",
    )
    try:
        result = await voice_session.run_session_once()
    except voice_session.VoiceDisabledError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503, detail=f"voice session failed: {exc}"
        ) from exc

    chat_history.append(
        _session_key(request),
        chat_history.Exchange(
            query=f"[voice] {result.transcript}" if result.transcript else "[voice]",
            response=result.response,
            intent=result.intent,
            source=result.source,
        ),
    )
    return RedirectResponse(url="/assistant", status_code=303)
