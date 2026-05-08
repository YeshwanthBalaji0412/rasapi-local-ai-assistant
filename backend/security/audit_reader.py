"""
Audit log reader (Phase 5).

Read-only access to JSONL audit files for the dashboard. Skips malformed
lines so a corrupt entry never crashes a page render. String fields longer
than 120 chars are truncated to keep dashboard payloads small.

This module never writes audit logs and never modifies files on disk.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from config import settings


logger = logging.getLogger(__name__)


_TRUNCATE_AT = 120
_TRUNCATE_SUFFIX = "..."


def _log_dir() -> Path:
    return Path(settings.audit_log_dir)


def _iter_log_files() -> Iterable[Path]:
    d = _log_dir()
    if not d.exists():
        return
    yield from sorted(d.glob("audit-*.jsonl"), reverse=True)


def _redact(obj: dict) -> dict:
    out: dict = {}
    for k, v in obj.items():
        if isinstance(v, str) and len(v) > _TRUNCATE_AT:
            out[k] = v[: _TRUNCATE_AT - len(_TRUNCATE_SUFFIX)] + _TRUNCATE_SUFFIX
        else:
            out[k] = v
    return out


def _is_security_event(obj: dict) -> bool:
    et = obj.get("event_type", "")
    if et in {
        "sensitive_memory_blocked",
        "briefing_source_failed",
        "weather_fetch_failed",
        "briefing_refresh_failed",
        "llm_briefing_summary_skipped",
    }:
        return True
    if et == "command_exec" and obj.get("outcome") in {"rejected", "error"}:
        return True
    if et == "llm_call" and obj.get("outcome") == "error":
        return True
    return False


def _read_filtered(*, limit: int, predicate=lambda obj: True) -> list[dict]:
    events: list[dict] = []
    for path in _iter_log_files():
        try:
            with path.open("r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError as exc:
            logger.warning("Cannot read audit file %s: %s", path, exc)
            continue
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(obj, dict):
                continue
            if not predicate(obj):
                continue
            events.append(_redact(obj))
            if len(events) >= limit:
                return events
    return events


def read_recent(*, limit: int = 25) -> list[dict]:
    """Return the most recent N audit events across all log files, newest first."""
    return _read_filtered(limit=limit)


def read_security_events(*, limit: int = 50) -> list[dict]:
    """Return only security-relevant audit events, newest first."""
    return _read_filtered(limit=limit, predicate=_is_security_event)
