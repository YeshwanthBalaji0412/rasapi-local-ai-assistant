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

    def log_llm_call(self, *, request_id: str, model: str, duration_ms: int) -> None:
        _write({
            "timestamp": _now_iso(),
            "event_type": "llm_call",
            "request_id": request_id,
            "model": model,
            "duration_ms": duration_ms,
        })

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


audit_logger = AuditLogger()
