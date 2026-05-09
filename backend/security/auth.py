"""
Authentication primitives (Phase 8).

Stateless, stdlib-only auth:
  - API key verification via hmac.compare_digest
  - Stateless signed session cookies (HMAC-SHA256 over a JSON payload)
  - Double-submit-cookie CSRF tokens
  - Audited via security.audit_log.log_auth_event

Key safety properties (verified by tests):
  - Every secret comparison uses hmac.compare_digest (no `==`).
  - The configured API_SECRET_KEY never appears in audit log entries.
  - When ENABLE_AUTH=true but the secret is missing or the placeholder,
    protected routes fail closed with 503 "auth misconfigured".
  - When ENABLE_AUTH=false, all dependencies are no-ops so the existing
    local workflow keeps working with zero changes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from typing import Callable
from urllib.parse import parse_qs

from fastapi import Header, HTTPException, Request, Response

from config import settings
from security.audit_log import audit_logger


_PLACEHOLDER_KEYS = {"", "change-me-before-use", "replace-with-output-of-generate-secret-sh"}


# ─── helpers ─────────────────────────────────────────────────────────────────


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64_decode(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


def _audit_id() -> str:
    return f"auth-{uuid.uuid4()}"


def _is_secret_configured() -> bool:
    return settings.api_secret_key not in _PLACEHOLDER_KEYS


def _misconfig_error(request_id: str) -> HTTPException:
    audit_logger.log_auth_event(
        request_id=request_id,
        event_type="auth_required_missing",
        outcome="error",
        reason="auth_misconfigured",
    )
    return HTTPException(status_code=503, detail="auth misconfigured")


# ─── API key verification ───────────────────────────────────────────────────


def verify_api_key(provided: str | None) -> bool:
    """Constant-time check against settings.api_secret_key. Returns False
    when the secret is missing/placeholder so callers can fail closed."""
    if not provided:
        return False
    if not _is_secret_configured():
        return False
    return hmac.compare_digest(provided, settings.api_secret_key)


# ─── Session cookies (stateless, signed) ────────────────────────────────────


def create_session_cookie() -> str:
    """Returns the signed cookie value. Uses the configured TTL."""
    if not _is_secret_configured():
        raise RuntimeError("cannot mint session cookie without a real API_SECRET_KEY")
    exp = int(time.time()) + settings.session_ttl_minutes * 60
    payload = _b64(json.dumps({"exp": exp, "v": 1}).encode("utf-8"))
    sig = _b64(
        hmac.new(
            settings.api_secret_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    )
    return f"{payload}.{sig}"


def validate_session_cookie(value: str | None) -> bool:
    if not value or "." not in value:
        return False
    if not _is_secret_configured():
        return False
    try:
        payload, sig = value.split(".", 1)
        expected = _b64(
            hmac.new(
                settings.api_secret_key.encode("utf-8"),
                payload.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        )
        if not hmac.compare_digest(sig, expected):
            return False
        data = json.loads(_b64_decode(payload).decode("utf-8"))
        return int(data.get("exp", 0)) > int(time.time())
    except (ValueError, json.JSONDecodeError, KeyError):
        return False


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value="",
        max_age=0,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


# ─── CSRF (double-submit cookie) ────────────────────────────────────────────


def issue_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def get_or_set_csrf_cookie(request: Request, response: Response) -> str:
    """Return the current CSRF token, setting a fresh cookie if missing."""
    existing = request.cookies.get(settings.csrf_cookie_name)
    if existing and len(existing) >= 16:
        return existing
    token = issue_csrf_token()
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token,
        max_age=settings.session_ttl_minutes * 60,
        httponly=False,  # template needs to read it; double-submit pattern
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return token


# ─── Form helpers (manual, no python-multipart dep) ─────────────────────────


async def read_form(request: Request) -> dict[str, str]:
    """Read application/x-www-form-urlencoded body without python-multipart."""
    body = await request.body()
    if not body:
        return {}
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        return {}
    parsed = parse_qs(text, keep_blank_values=True)
    return {k: v[0] for k, v in parsed.items() if v}


# ─── HTTP credential extraction ─────────────────────────────────────────────


def _extract_api_key(
    x_rasapi_key: str | None, authorization: str | None
) -> str | None:
    if x_rasapi_key:
        return x_rasapi_key.strip()
    if authorization:
        auth = authorization.strip()
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
    return None


def _request_has_valid_credentials(
    request: Request,
    x_rasapi_key: str | None,
    authorization: str | None,
) -> bool:
    candidate = _extract_api_key(x_rasapi_key, authorization)
    if candidate and verify_api_key(candidate):
        return True
    cookie = request.cookies.get(settings.session_cookie_name)
    return validate_session_cookie(cookie)


# ─── FastAPI dependencies ────────────────────────────────────────────────────


def _make_api_dep(flag_attr: str) -> Callable:
    """Build a FastAPI dependency that protects API routes when the given
    AUTH_PROTECT_* flag is on."""

    def dep(
        request: Request,
        x_rasapi_key: str | None = Header(default=None, alias="X-RasaPi-Key"),
        authorization: str | None = Header(default=None),
    ) -> None:
        if not (settings.enable_auth and getattr(settings, flag_attr)):
            return  # auth disabled or this category not protected
        request_id = _audit_id()
        if not _is_secret_configured():
            raise _misconfig_error(request_id)
        if _request_has_valid_credentials(request, x_rasapi_key, authorization):
            audit_logger.log_auth_event(
                request_id=request_id,
                event_type="protected_route_accessed",
                outcome="success",
            )
            return
        provided = _extract_api_key(x_rasapi_key, authorization)
        reason = "invalid_key" if provided else "no_credentials"
        audit_logger.log_auth_event(
            request_id=request_id,
            event_type="auth_invalid_key" if provided else "auth_required_missing",
            outcome="error",
            reason=reason,
        )
        raise HTTPException(status_code=401, detail="auth required")

    return dep


require_auth_for_ask = _make_api_dep("auth_protect_ask")
require_auth_for_voice = _make_api_dep("auth_protect_voice")
require_auth_for_mutations = _make_api_dep("auth_protect_mutations")


# ─── Dashboard (browser) helpers ─────────────────────────────────────────────


def is_dashboard_authenticated(request: Request) -> bool:
    if not (settings.enable_auth and settings.auth_protect_dashboard):
        return True
    if not _is_secret_configured():
        return False
    return validate_session_cookie(request.cookies.get(settings.session_cookie_name))


def safe_next_url(raw: str | None) -> str:
    """Open-redirect guard: only allow same-origin paths starting with '/'."""
    if not raw:
        return "/dashboard"
    if not raw.startswith("/"):
        return "/dashboard"
    if "://" in raw or raw.startswith("//"):
        return "/dashboard"
    return raw


def verify_csrf(request: Request, form: dict[str, str]) -> bool:
    """Double-submit check. Skipped entirely when ENABLE_AUTH=false."""
    if not (settings.enable_auth and settings.auth_protect_dashboard):
        return True
    cookie = request.cookies.get(settings.csrf_cookie_name, "")
    form_token = form.get("_csrf", "")
    if not (cookie and form_token):
        return False
    return hmac.compare_digest(cookie, form_token)
