"""
Readiness / version / config-status endpoints (Phase 10).

  GET /version         → public, returns name + version
  GET /readiness       → public, k8s-style readiness probe over JSON
  GET /config/status   → safe feature-flag summary; gated by auth when
                         ENABLE_AUTH=true and AUTH_PROTECT_DASHBOARD=true
                         (same posture as the dashboard JSON endpoints)

`/config/status` is the only Phase 10 endpoint that requires auth. It is
the operator's source of truth for "what features are turned on" and
must never include secrets or absolute filesystem paths. Sentinel tests
enforce this.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from config import settings
from security import auth as auth_module


router = APIRouter(tags=["readiness"])


_VERSION = "0.10.0"
_NAME = "RasaPi"


# ─── /version ───────────────────────────────────────────────────────────────


@router.get("/version")
def get_version() -> dict:
    return {"name": _NAME, "version": _VERSION}


# ─── /readiness ─────────────────────────────────────────────────────────────


def _check_dir(path_str: str) -> str:
    """Return 'ok' if the path exists OR its parent does (so the writing
    subsystem can create it lazily). 'missing' only when neither exists."""
    p = Path(path_str)
    if p.exists():
        return "ok"
    if p.parent.exists():
        return "ok"
    return "missing"


@router.get("/readiness")
def get_readiness() -> dict:
    """
    JSON readiness probe. Returns 200 always so an uptime monitor can
    differentiate "service is alive but unhealthy" from "no response".
    The `ready` boolean and per-check fields tell the operator what's
    wrong without exposing paths.

    Audit log directories and the voice temp dir are created lazily on
    first write, so we treat "parent exists" as ok.
    """
    db_parent = Path(settings.database_path).parent
    checks = {
        "database_dir": _check_dir(str(db_parent)),
        "audit_log_dir": _check_dir(settings.audit_log_dir),
        "voice_audio_temp_dir": (
            _check_dir(settings.voice_audio_temp_dir)
            if settings.enable_voice
            else "skipped"
        ),
    }
    ready = all(v in {"ok", "skipped"} for v in checks.values())
    return {
        "ready": ready,
        "version": _VERSION,
        "checks": checks,
    }


# ─── /config/status ─────────────────────────────────────────────────────────


def _safe_feature_flags() -> dict:
    """A projection of `settings` that never includes secrets or paths.

    Keep this list explicit. Anything you want to expose has to be added
    here on purpose."""
    return {
        "version": _VERSION,
        "features": {
            "local_llm": bool(settings.enable_local_llm),
            "briefing": bool(settings.enable_briefing),
            "voice": bool(settings.enable_voice),
            "auth": bool(settings.enable_auth),
            "slack": bool(settings.enable_slack),
            "home_assistant": bool(settings.enable_home_assistant),
            "alexa": False,   # stub only
        },
        "auth": {
            "enabled": bool(settings.enable_auth),
            "secret_configured": settings.api_secret_key
            not in {
                "",
                "change-me-before-use",
                "replace-with-output-of-generate-secret-sh",
            },
            "protect_ask": bool(settings.auth_protect_ask),
            "protect_voice": bool(settings.auth_protect_voice),
            "protect_mutations": bool(settings.auth_protect_mutations),
            "protect_dashboard": bool(settings.auth_protect_dashboard),
            "protect_integrations": bool(settings.auth_protect_integrations),
            "cookie_secure": bool(settings.cookie_secure),
            "session_ttl_minutes": settings.session_ttl_minutes,
        },
        "voice": {
            "stt_engine": settings.voice_stt_engine,
            "tts_engine": settings.voice_tts_engine,
            "recorder_engine": settings.voice_recorder_engine,
            "save_audio": bool(settings.voice_save_audio),
            "log_transcripts": bool(settings.voice_log_transcripts),
        },
        "briefing": {
            "enabled": bool(settings.enable_briefing),
            "llm_summary_enabled": bool(settings.enable_llm_briefing_summary),
            "cache_minutes": settings.briefing_cache_minutes,
        },
        "integrations": {
            "slack_enabled": bool(settings.enable_slack),
            # secret_configured = URL is non-empty (we do NOT include the URL).
            "slack_configured": (
                bool(settings.enable_slack) and bool(settings.slack_webhook_url.strip())
            ),
            "home_assistant_enabled": bool(settings.enable_home_assistant),
            "home_assistant_configured": (
                bool(settings.enable_home_assistant)
                and bool(settings.home_assistant_url.strip())
                and bool(settings.home_assistant_token.strip())
            ),
            "home_assistant_allowed_domains": settings.home_assistant_allowed_domains,
            "home_assistant_allowed_entity_count": len(
                [
                    e.strip()
                    for e in (settings.home_assistant_allowed_entities or "").split(",")
                    if e.strip()
                ]
            ),
        },
    }


@router.get("/config/status")
def get_config_status(request: Request) -> dict:
    """
    Safe feature-flag summary. When auth is enabled, requires either an
    API key header or an active dashboard session — same posture as
    /dashboard/audit/recent.
    """
    if settings.enable_auth and settings.auth_protect_dashboard:
        if not auth_module._is_secret_configured():
            raise HTTPException(status_code=503, detail="auth misconfigured")
        x_key = request.headers.get("X-RasaPi-Key")
        authz = request.headers.get("Authorization")
        if not auth_module._request_has_valid_credentials(request, x_key, authz):
            raise HTTPException(status_code=401, detail="auth required")
    return _safe_feature_flags()
