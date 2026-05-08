"""
Memory and notes service (Phase 3).

Handles two related concerns:
  - memory_items: key/value pairs the user wants the assistant to remember
                  ("remember that my domain is rasapi.com")
  - notes:        free-form notes ("save note buy a USB mic on Friday")

Both flow through the same sensitive-data check and the same audit logger.
This module never imports the command runner, the LLM, or subprocess. It is
the only place that writes to the memory_items / notes tables.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from security.audit_log import audit_logger
from security.sensitive_data import REJECTION_MESSAGE, is_sensitive
from storage.database import db_session, now_iso


logger = logging.getLogger(__name__)


_MAX_VALUE_CHARS = 4000
_LIST_LIMIT = 50


# ─── memory_items ─────────────────────────────────────────────────────────────


def save_memory(
    *,
    value: str,
    request_id: str,
    key: str | None = None,
    category: str = "general",
) -> tuple[bool, str, int | None]:
    """
    Insert a memory item. Returns (saved, message, item_id).
    Returns (False, rejection_msg, None) on sensitive content.
    """
    value = (value or "").strip()
    if not value:
        return (False, "Tell me what you'd like me to remember.", None)
    value = value[:_MAX_VALUE_CHARS]

    blocked, reason = is_sensitive(value)
    if blocked:
        audit_logger.log_storage_event(
            request_id=request_id,
            event_type="sensitive_memory_blocked",
            item_type="memory",
            outcome="blocked",
            reason=reason,
        )
        return (False, REJECTION_MESSAGE, None)

    with db_session() as conn:
        cur = conn.execute(
            "INSERT INTO memory_items (key, value, category, created_at) VALUES (?, ?, ?, ?)",
            (key, value, category, now_iso()),
        )
        item_id = cur.lastrowid

    audit_logger.log_storage_event(
        request_id=request_id,
        event_type="memory_created",
        item_type="memory",
        item_id=item_id,
    )
    return (True, "Saved to local memory.", item_id)


def list_memory(*, request_id: str, include_archived: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT id, key, value, category, created_at, archived FROM memory_items"
    if not include_archived:
        sql += " WHERE archived = 0"
    sql += " ORDER BY id DESC LIMIT ?"

    with db_session() as conn:
        rows = conn.execute(sql, (_LIST_LIMIT,)).fetchall()

    audit_logger.log_storage_event(
        request_id=request_id,
        event_type="memory_listed",
        item_type="memory",
    )
    return [dict(row) for row in rows]


# ─── notes ────────────────────────────────────────────────────────────────────


def save_note(
    *,
    content: str,
    request_id: str,
    tags: str | None = None,
) -> tuple[bool, str, int | None]:
    content = (content or "").strip()
    if not content:
        return (False, "Tell me what to put in the note.", None)
    content = content[:_MAX_VALUE_CHARS]

    blocked, reason = is_sensitive(content)
    if blocked:
        audit_logger.log_storage_event(
            request_id=request_id,
            event_type="sensitive_memory_blocked",
            item_type="note",
            outcome="blocked",
            reason=reason,
        )
        return (False, REJECTION_MESSAGE, None)

    with db_session() as conn:
        cur = conn.execute(
            "INSERT INTO notes (content, tags, created_at) VALUES (?, ?, ?)",
            (content, tags, now_iso()),
        )
        item_id = cur.lastrowid

    audit_logger.log_storage_event(
        request_id=request_id,
        event_type="note_created",
        item_type="note",
        item_id=item_id,
    )
    return (True, f"Note saved (#{item_id}).", item_id)


def list_notes(*, request_id: str, include_archived: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT id, content, tags, created_at, archived FROM notes"
    if not include_archived:
        sql += " WHERE archived = 0"
    sql += " ORDER BY id DESC LIMIT ?"

    with db_session() as conn:
        rows = conn.execute(sql, (_LIST_LIMIT,)).fetchall()

    audit_logger.log_storage_event(
        request_id=request_id,
        event_type="note_listed",
        item_type="note",
    )
    return [dict(row) for row in rows]


# ─── /ask handlers — deterministic query parsing ──────────────────────────────


_REMEMBER_PREFIXES = (
    "remember that ",
    "remember to remember that ",
    "please remember that ",
    "remember ",
)

_NOTE_PREFIXES = (
    "save note ",
    "take a note ",
    "note: ",
    "add note ",
)


def _strip_prefix(query: str, prefixes: tuple[str, ...]) -> str | None:
    q = query.strip()
    lowered = q.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return q[len(prefix):].strip()
    return None


def save_memory_from_query(query: str, request_id: str) -> str:
    value = _strip_prefix(query, _REMEMBER_PREFIXES) or ""
    saved, msg, _ = save_memory(value=value, request_id=request_id)
    return msg


def list_memory_text(query: str, request_id: str) -> str:
    items = list_memory(request_id=request_id)
    if not items:
        return "I don't have anything saved in memory yet."
    lines = ["Here's what I remember:"]
    for it in items:
        prefix = f"{it['id']}."
        if it["key"]:
            lines.append(f"  {prefix} [{it['key']}] {it['value']}")
        else:
            lines.append(f"  {prefix} {it['value']}")
    return "\n".join(lines)


def save_note_from_query(query: str, request_id: str) -> str:
    content = _strip_prefix(query, _NOTE_PREFIXES) or ""
    saved, msg, _ = save_note(content=content, request_id=request_id)
    return msg


def list_notes_text(query: str, request_id: str) -> str:
    notes = list_notes(request_id=request_id)
    if not notes:
        return "You don't have any notes yet."
    lines = ["Your notes:"]
    for n in notes:
        lines.append(f"  {n['id']}. {n['content']}")
    return "\n".join(lines)
