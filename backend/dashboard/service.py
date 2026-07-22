"""
Dashboard view-model aggregator (Phase 5).

The route handler asks this module for a single dict and renders the
template with it. There is no business logic in routes or templates.

Every value on the rendered page traces to one of:
  - settings (projected to a hardcoded SAFE subset)
  - stdlib (shutil/platform/os) for system health
  - intent_router.list_intents()
  - direct SQL reads on memory_items / notes / tasks / briefing_*
  - security.audit_reader

We bypass core/memory and core/tasks list functions to avoid emitting
extra audit events for dashboard reads. The route handler emits a single
`dashboard_viewed` event per page load instead.

Note: this module never reads `.env`, `os.environ`, or any settings
field other than the ones explicitly named below.
"""

from __future__ import annotations

import os
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from briefing.sources import CATEGORIES
from config import settings
from core.intent_router import list_intents
from security import audit_reader
from storage.database import db_session


_VERSION = "0.5.0"
_PHASE = "Phase 5 — Dashboard"


# Map intent names → declaring phase, for grouping in the UI.
_PHASE_BY_INTENT: dict[str, int] = {
    # Phase 1
    "time": 1, "uptime": 1, "cpu_temp": 1, "disk": 1,
    "memory_usage": 1, "hostname": 1, "system": 1,
    "greeting": 1, "help": 1,
    # Phase 3
    "save_memory": 3, "list_memory": 3, "save_note": 3, "list_notes": 3,
    "add_task": 3, "list_tasks": 3, "complete_task": 3,
    # Phase 4
    "daily_briefing": 4, "world_briefing": 4, "ai_briefing": 4,
    "tech_briefing": 4, "developer_briefing": 4,
    "weather_briefing": 4, "immigration_briefing": 4,
    # Phase 9 — integrations
    "slack_send_test": 9, "slack_send_briefing": 9,
    "ha_status": 9, "ha_turn_on": 9, "ha_turn_off": 9,
}


def _truncate(s: str | None, n: int = 200) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[:n] + "..."


def _mask_path(p: str) -> str:
    """Show only the last two path segments when masking is on, so absolute
    filesystem layout (e.g. /Users/foo/...) never appears in the UI."""
    if not settings.dashboard_mask_db_path:
        return p
    parts = Path(p).parts
    if len(parts) <= 2:
        return p
    return os.path.join(*parts[-2:])


# Backwards-compat alias used by existing test.
_mask_db_path = _mask_path


def _mask_url_to_host(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    except (ValueError, AttributeError):
        pass
    return url


# ─── overview / health ───────────────────────────────────────────────────────


def get_overview() -> dict:
    return {
        "name": settings.assistant_name,
        "version": _VERSION,
        "phase": _PHASE,
        "enable_local_llm": settings.enable_local_llm,
        "enable_briefing": settings.enable_briefing,
        "enable_llm_briefing_summary": settings.enable_llm_briefing_summary,
        "log_level": settings.log_level,
        "database_path": _mask_path(settings.database_path),
        "audit_log_dir": _mask_path(settings.audit_log_dir),
    }


def get_health() -> dict:
    disk = shutil.disk_usage("/")
    try:
        load = os.getloadavg()
        load_avg = f"{load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}"
    except (AttributeError, OSError):
        load_avg = None
    return {
        "current_time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "disk_total_gb": round(disk.total / (1024 ** 3), 1),
        "disk_used_gb": round(disk.used / (1024 ** 3), 1),
        "disk_free_gb": round(disk.free / (1024 ** 3), 1),
        "disk_used_percent": round(disk.used / disk.total * 100, 1),
        "load_avg_1_5_15": load_avg,
    }


# ─── intents ─────────────────────────────────────────────────────────────────


def get_intents_grouped() -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {1: [], 3: [], 4: [], 9: []}
    for intent in list_intents():
        phase = _PHASE_BY_INTENT.get(intent["name"], 1)
        grouped.setdefault(phase, []).append(
            {"name": intent["name"], "description": intent["description"]}
        )
    return grouped


# ─── memory / notes / tasks ──────────────────────────────────────────────────


def get_memory_summary() -> dict:
    """Read-only direct SQL so dashboard views don't trigger memory_listed
    audit events. The dashboard's own `dashboard_viewed` event covers it."""
    with db_session() as conn:
        memory_rows = conn.execute(
            "SELECT id, key, value, created_at FROM memory_items "
            "WHERE archived = 0 ORDER BY id DESC LIMIT 5"
        ).fetchall()
        note_rows = conn.execute(
            "SELECT id, content, created_at FROM notes "
            "WHERE archived = 0 ORDER BY id DESC LIMIT 5"
        ).fetchall()
        open_task_rows = conn.execute(
            "SELECT id, title, priority, created_at FROM tasks "
            "WHERE status = 'open' ORDER BY id ASC"
        ).fetchall()
        all_count_row = conn.execute(
            "SELECT COUNT(*) AS c FROM tasks"
        ).fetchone()
        done_count_row = conn.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE status = 'done'"
        ).fetchone()

    return {
        "memory": [
            {
                "id": r["id"],
                "key": _truncate(r["key"] or "", 60),
                "value": _truncate(r["value"], 200),
                "created_at": r["created_at"],
            }
            for r in memory_rows
        ],
        "notes": [
            {
                "id": r["id"],
                "content": _truncate(r["content"], 200),
                "created_at": r["created_at"],
            }
            for r in note_rows
        ],
        "open_tasks": [
            {
                "id": r["id"],
                "title": _truncate(r["title"], 200),
                "priority": r["priority"],
                "created_at": r["created_at"],
            }
            for r in open_task_rows
        ],
        "completed_count": done_count_row["c"],
        "total_count": all_count_row["c"],
    }


# ─── briefing ────────────────────────────────────────────────────────────────


def get_briefing_summary() -> dict:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT category, COUNT(*) AS c FROM briefing_items "
            "WHERE archived = 0 GROUP BY category"
        ).fetchall()
        last = conn.execute(
            "SELECT id, briefing_type, created_at, item_count, status, error "
            "FROM briefing_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()

    counts = {row["category"]: row["c"] for row in rows}
    counts_full = {cat: counts.get(cat, 0) for cat in CATEGORIES}

    return {
        "counts_by_category": counts_full,
        "last_run": dict(last) if last else None,
        "categories": list(CATEGORIES),
    }


# ─── local LLM (config only — no live ping) ──────────────────────────────────


def get_llm_summary() -> dict:
    return {
        "enabled": settings.enable_local_llm,
        "provider": settings.local_llm_provider,
        "model": settings.local_llm_model,
        "base_url_host": _mask_url_to_host(settings.ollama_base_url),
        "briefing_summary_enabled": settings.enable_llm_briefing_summary,
        "timeout_seconds": settings.local_llm_timeout_seconds,
    }


# ─── audit / security ────────────────────────────────────────────────────────


def get_auth_summary() -> dict:
    """Auth flags for the dashboard Security card. NEVER includes the secret."""
    # Import here rather than at module top to keep security/auth.py an
    # optional dependency for callers of this module (matches how the rest
    # of this file scopes its imports).
    from security.auth import PLACEHOLDER_KEYS

    secret_configured = settings.api_secret_key not in PLACEHOLDER_KEYS
    return {
        "enabled": settings.enable_auth,
        "secret_configured": secret_configured,
        "protect_dashboard": settings.auth_protect_dashboard,
        "protect_ask": settings.auth_protect_ask,
        "protect_voice": settings.auth_protect_voice,
        "protect_mutations": settings.auth_protect_mutations,
        "session_ttl_minutes": settings.session_ttl_minutes,
        "cookie_secure": settings.cookie_secure,
        "host": settings.host,
        # If the server is bound to 0.0.0.0 without auth, that is a posture
        # warning the dashboard should surface.
        "lan_exposed_without_auth": (
            settings.host in ("0.0.0.0", "::") and not settings.enable_auth
        ),
        # If auth is enabled but the secret is unset, fail-closed. Tell the
        # operator to fix this immediately.
        "misconfigured": settings.enable_auth and not secret_configured,
    }


def get_integrations_summary() -> dict:
    """Phase 9 — never includes webhook URLs, tokens, or HA URL."""
    from integrations import registry as integration_registry
    from integrations import slack
    from integrations import home_assistant as ha
    return {
        "registry": integration_registry.to_safe_dicts(),
        "slack": slack.safe_status(),
        "home_assistant": ha.safe_status(),
    }


def get_voice_summary() -> dict:
    """Voice configuration + last session, if any. Read-only."""
    last_events = audit_reader.read_events_by_types(
        event_types={"voice_session_completed", "voice_session_failed"},
        limit=1,
    )
    last_session = last_events[0] if last_events else None
    return {
        "enabled": settings.enable_voice,
        "recorder_engine": settings.voice_recorder_engine,
        "stt_engine": settings.voice_stt_engine,
        "tts_engine": settings.voice_tts_engine,
        "save_audio": settings.voice_save_audio,
        "log_transcripts": settings.voice_log_transcripts,
        "push_to_talk_required": settings.voice_require_push_to_talk,
        "last_session": last_session,
    }


def get_audit_recent(limit: int = 25) -> list[dict]:
    return audit_reader.read_recent(limit=limit)


def get_security_events(limit: int = 50) -> list[dict]:
    return audit_reader.read_security_events(limit=limit)


# ─── full view-model ─────────────────────────────────────────────────────────


def build_view_model() -> dict:
    return {
        "overview": get_overview(),
        "health": get_health(),
        "intents": get_intents_grouped(),
        "memory_summary": get_memory_summary(),
        "briefing_summary": get_briefing_summary(),
        "llm_summary": get_llm_summary(),
        "auth_summary": get_auth_summary(),
        "voice_summary": get_voice_summary(),
        "integrations_summary": get_integrations_summary(),
        "audit_recent": get_audit_recent(),
        "security_events": get_security_events(),
    }
