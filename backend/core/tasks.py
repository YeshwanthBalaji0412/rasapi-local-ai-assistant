"""
Tasks service (Phase 3).

CRUD operations on the `tasks` table, plus query-extracting variants for
the conversational /ask path. This module never imports the command runner
or the LLM.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from security.audit_log import audit_logger
from storage.database import db_session, now_iso


logger = logging.getLogger(__name__)


_MAX_TITLE_CHARS = 500
_LIST_LIMIT = 100


# ─── service layer ────────────────────────────────────────────────────────────


def add_task(
    *,
    title: str,
    request_id: str,
    priority: str = "normal",
    due_date: str | None = None,
) -> tuple[bool, str, int | None]:
    title = (title or "").strip()
    if not title:
        return (False, "Tell me what the task is.", None)
    if priority not in {"low", "normal", "high"}:
        priority = "normal"
    title = title[:_MAX_TITLE_CHARS]

    with db_session() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (title, priority, due_date, created_at) VALUES (?, ?, ?, ?)",
            (title, priority, due_date, now_iso()),
        )
        item_id = cur.lastrowid

    audit_logger.log_storage_event(
        request_id=request_id,
        event_type="task_created",
        item_type="task",
        item_id=item_id,
    )
    return (True, f"Task added: {title}", item_id)


def list_tasks(*, request_id: str, include_done: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT id, title, status, priority, due_date, created_at, completed_at FROM tasks"
    if not include_done:
        sql += " WHERE status = 'open'"
    sql += " ORDER BY id ASC LIMIT ?"

    with db_session() as conn:
        rows = conn.execute(sql, (_LIST_LIMIT,)).fetchall()

    audit_logger.log_storage_event(
        request_id=request_id,
        event_type="task_listed",
        item_type="task",
    )
    return [dict(row) for row in rows]


def complete_task(*, task_id: int, request_id: str) -> tuple[bool, str]:
    with db_session() as conn:
        row = conn.execute("SELECT id, status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            audit_logger.log_storage_event(
                request_id=request_id,
                event_type="task_completed",
                item_type="task",
                item_id=task_id,
                outcome="error",
                reason="not_found",
            )
            return (False, f"I couldn't find task {task_id}.")

        if row["status"] == "done":
            audit_logger.log_storage_event(
                request_id=request_id,
                event_type="task_completed",
                item_type="task",
                item_id=task_id,
                outcome="noop",
                reason="already_done",
            )
            return (True, f"Task {task_id} was already done.")

        conn.execute(
            "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
            (now_iso(), task_id),
        )

    audit_logger.log_storage_event(
        request_id=request_id,
        event_type="task_completed",
        item_type="task",
        item_id=task_id,
    )
    return (True, f"Marked task {task_id} as done.")


# ─── /ask handlers ────────────────────────────────────────────────────────────


_TASK_PREFIXES = (
    "add task ",
    "new task ",
    "create task ",
    "task: ",
)

# Matches "task 3" or "task #3" anywhere in the query.
_TASK_NUMBER_RE = re.compile(r"task\s*#?\s*(\d+)", re.IGNORECASE)


def add_task_from_query(query: str, request_id: str) -> str:
    q = query.strip()
    lowered = q.lower()
    title = ""
    for prefix in _TASK_PREFIXES:
        if lowered.startswith(prefix):
            title = q[len(prefix):].strip()
            break
    saved, msg, _ = add_task(title=title, request_id=request_id)
    return msg


def list_tasks_text(query: str, request_id: str) -> str:
    tasks = list_tasks(request_id=request_id)
    if not tasks:
        return "No open tasks. You're caught up."
    lines = ["Open tasks:"]
    for t in tasks:
        flag = "!" if t["priority"] == "high" else " "
        lines.append(f"  {t['id']}.{flag} {t['title']}")
    return "\n".join(lines)


def complete_task_from_query(query: str, request_id: str) -> str:
    match = _TASK_NUMBER_RE.search(query)
    if not match:
        return "Tell me which task number to complete (for example: 'mark task 3 as done')."
    task_id = int(match.group(1))
    _, msg = complete_task(task_id=task_id, request_id=request_id)
    return msg
