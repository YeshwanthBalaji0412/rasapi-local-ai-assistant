"""
Structured JSONL audit logger.

Every request and command execution is written as a single JSON line to
logs/audit-YYYY-MM-DD.jsonl. The file rotates daily. Entries are append-only
and never modified after writing.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from config import settings


logger = logging.getLogger(__name__)


def _log_dir() -> Path:
    p = Path(settings.audit_log_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write(entry: dict) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path = _log_dir() / f"audit-{today}.jsonl"
    try:
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.error("Failed to write audit log: %s", exc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditLogger:
    def log_request(self, *, request_id: str, query: str) -> None:
        _write({
            "timestamp": _now_iso(),
            "event_type": "request",
            "request_id": request_id,
            "query": query[:500],
        })

    def log_llm_call(
        self,
        *,
        request_id: str,
        model: str,
        outcome: str,
        duration_ms: int,
        reason: str | None = None,
    ) -> None:
        entry: dict = {
            "timestamp": _now_iso(),
            "event_type": "llm_call",
            "request_id": request_id,
            "model": model,
            "outcome": outcome,
            "duration_ms": duration_ms,
        }
        if reason:
            entry["reason"] = reason
        _write(entry)

    def log_command(
        self,
        *,
        request_id: str,
        command: str,
        args: list[str],
        outcome: str,
        reason: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        entry: dict = {
            "timestamp": _now_iso(),
            "event_type": "command_exec",
            "request_id": request_id,
            "command": command,
            "args": args,
            "outcome": outcome,
        }
        if reason:
            entry["reason"] = reason
        if duration_ms is not None:
            entry["duration_ms"] = duration_ms
        _write(entry)


    def log_storage_event(
        self,
        *,
        request_id: str,
        event_type: str,
        item_type: str,
        item_id: int | None = None,
        outcome: str = "success",
        reason: str | None = None,
    ) -> None:
        """
        Records a memory / note / task event. event_type is one of:
          memory_created, memory_listed, note_created, note_listed,
          task_created, task_listed, task_completed,
          sensitive_memory_blocked.
        """
        entry: dict = {
            "timestamp": _now_iso(),
            "event_type": event_type,
            "request_id": request_id,
            "item_type": item_type,
            "outcome": outcome,
        }
        if item_id is not None:
            entry["item_id"] = item_id
        if reason:
            entry["reason"] = reason
        _write(entry)


    def log_briefing_event(
        self,
        *,
        request_id: str,
        event_type: str,
        outcome: str = "success",
        category: str | None = None,
        source_name: str | None = None,
        item_count: int | None = None,
        reason: str | None = None,
    ) -> None:
        """
        Records a briefing event. event_type is one of:
          briefing_refresh_started, briefing_refresh_completed,
          briefing_refresh_failed, briefing_source_failed,
          briefing_item_stored, briefing_served,
          weather_fetch_completed, weather_fetch_failed,
          llm_briefing_summary_used, llm_briefing_summary_skipped.
        """
        entry: dict = {
            "timestamp": _now_iso(),
            "event_type": event_type,
            "request_id": request_id,
            "outcome": outcome,
        }
        if category:
            entry["category"] = category
        if source_name:
            entry["source_name"] = source_name
        if item_count is not None:
            entry["item_count"] = item_count
        if reason:
            entry["reason"] = reason[:200]
        _write(entry)


    def log_dashboard_event(
        self,
        *,
        request_id: str,
        event_type: str,
        outcome: str = "success",
        reason: str | None = None,
    ) -> None:
        """
        Records a dashboard event. event_type is one of:
          dashboard_viewed, dashboard_health_viewed, dashboard_audit_viewed,
          dashboard_security_events_viewed,
          dashboard_briefing_refresh_requested, dashboard_task_completed.
        """
        entry: dict = {
            "timestamp": _now_iso(),
            "event_type": event_type,
            "request_id": request_id,
            "outcome": outcome,
        }
        if reason:
            entry["reason"] = reason[:200]
        _write(entry)


    def log_voice_event(
        self,
        *,
        request_id: str,
        event_type: str,
        outcome: str = "success",
        stt_engine: str | None = None,
        tts_engine: str | None = None,
        duration_ms: int | None = None,
        transcript_length: int | None = None,
        audio_saved: bool | None = None,
        reason: str | None = None,
    ) -> None:
        """
        Records a voice event. event_type is one of:
          voice_session_started, voice_recording_completed,
          voice_transcription_completed, voice_tts_completed,
          voice_session_failed, voice_session_completed.

        Audio bytes, file paths, and transcript content are NEVER written
        to the audit log — only metadata.
        """
        entry: dict = {
            "timestamp": _now_iso(),
            "event_type": event_type,
            "request_id": request_id,
            "outcome": outcome,
        }
        if stt_engine is not None:
            entry["stt_engine"] = stt_engine
        if tts_engine is not None:
            entry["tts_engine"] = tts_engine
        if duration_ms is not None:
            entry["duration_ms"] = duration_ms
        if transcript_length is not None:
            entry["transcript_length"] = transcript_length
        if audio_saved is not None:
            entry["audio_saved"] = audio_saved
        if reason:
            entry["reason"] = reason[:200]
        _write(entry)


    def log_auth_event(
        self,
        *,
        request_id: str,
        event_type: str,
        outcome: str = "success",
        reason: str | None = None,
    ) -> None:
        """
        Records an auth event. event_type is one of:
          auth_login_success, auth_login_failed, auth_logout,
          auth_required_missing, auth_invalid_key,
          csrf_validation_failed, protected_route_accessed.

        The provided API key is NEVER stored. For failed-auth events,
        only `reason` is recorded ("no_credentials", "invalid_key",
        "auth_misconfigured", "csrf_mismatch", etc.).
        """
        entry: dict = {
            "timestamp": _now_iso(),
            "event_type": event_type,
            "request_id": request_id,
            "outcome": outcome,
        }
        if reason:
            entry["reason"] = reason[:200]
        _write(entry)


    def log_integration_event(
        self,
        *,
        request_id: str,
        event_type: str,
        outcome: str = "success",
        integration: str | None = None,
        target: str | None = None,
        reason: str | None = None,
    ) -> None:
        """
        Records an integration event. event_type is one of:
          integration_status_viewed,
          slack_test_sent / slack_test_failed,
          slack_briefing_sent / slack_briefing_failed,
          home_assistant_status_checked,
          home_assistant_entity_listed,
          home_assistant_state_read,
          home_assistant_action_requested,
          home_assistant_action_completed,
          home_assistant_action_blocked,
          integration_secret_missing,
          integration_auth_required.

        `target` is the entity_id for HA actions. NEVER a webhook URL,
        token, or auth header. Secrets are not accepted by this method.
        """
        entry: dict = {
            "timestamp": _now_iso(),
            "event_type": event_type,
            "request_id": request_id,
            "outcome": outcome,
        }
        if integration:
            entry["integration"] = integration
        if target:
            entry["target"] = target[:200]
        if reason:
            entry["reason"] = reason[:200]
        _write(entry)


audit_logger = AuditLogger()
