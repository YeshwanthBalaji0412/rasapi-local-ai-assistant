"""
Briefing generator (Phase 4).

Owns the lifecycle:
  - refresh: fetch all (or filtered) sources, dedupe, store, audit
  - get_recent_items: read items grouped by category for display
  - get_or_refresh_daily_briefing: cache-aware /ask handler

Security boundaries enforced by structure:
  - This module imports ONLY: briefing.*, config, security.audit_log,
    storage.database, core.local_llm. It does NOT import core/memory or
    core/tasks. Verified by tests/test_phase4_routing.py.
  - The LLM summary call only runs when both ENABLE_LOCAL_LLM and
    ENABLE_LLM_BRIEFING_SUMMARY are true. The headlines passed to it
    come from briefing_items (already public source content).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from briefing import rss_client, weather as weather_module
from briefing.formatter import format_category_briefing, format_daily_briefing
from briefing.sources import CATEGORIES, SOURCES, Source, is_valid_category
from config import settings
from core import local_llm
from security.audit_log import audit_logger
from storage.database import db_session, now_iso


logger = logging.getLogger(__name__)


# ─── refresh ──────────────────────────────────────────────────────────────────


def refresh_briefing(
    *,
    request_id: str,
    categories: Iterable[str] | None = None,
    briefing_type: str = "daily",
) -> dict[str, Any]:
    """
    Fetch sources (optionally filtered by category), insert new items,
    update a briefing_runs row. Returns run metadata.
    """
    cat_set = set(categories) if categories is not None else None
    source_list: list[Source] = [
        s for s in SOURCES if cat_set is None or s.category in cat_set
    ]

    audit_logger.log_briefing_event(
        request_id=request_id,
        event_type="briefing_refresh_started",
        outcome="started",
        category=",".join(sorted(cat_set)) if cat_set else "all",
    )

    with db_session() as conn:
        cur = conn.execute(
            "INSERT INTO briefing_runs (briefing_type, created_at, status) VALUES (?, ?, ?)",
            (briefing_type, now_iso(), "success"),
        )
        run_id = cur.lastrowid

    item_count = 0
    failures: list[tuple[str, str]] = []

    for source in source_list:
        try:
            raw_items = _fetch_one(source, request_id=request_id)
        except rss_client.SourceFetchError as exc:
            audit_logger.log_briefing_event(
                request_id=request_id,
                event_type="briefing_source_failed",
                outcome="error",
                source_name=source.name,
                category=source.category,
                reason=str(exc),
            )
            failures.append((source.name, str(exc)))
            continue

        cap = settings.briefing_max_items_per_category
        for item in raw_items[:cap]:
            if _is_duplicate(item, source.category):
                continue
            with db_session() as conn:
                conn.execute(
                    "INSERT INTO briefing_items "
                    "(category, source_name, title, url, published_at, fetched_at, summary) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        source.category,
                        source.name,
                        item["title"],
                        item.get("url"),
                        item.get("published_at"),
                        now_iso(),
                        item.get("summary"),
                    ),
                )
            audit_logger.log_briefing_event(
                request_id=request_id,
                event_type="briefing_item_stored",
                outcome="success",
                source_name=source.name,
                category=source.category,
            )
            item_count += 1

    status = "partial" if failures else "success"
    error_blob = (
        "; ".join(f"{n}: {e}" for n, e in failures)[:500] if failures else None
    )

    with db_session() as conn:
        conn.execute(
            "UPDATE briefing_runs SET item_count = ?, status = ?, error = ? WHERE id = ?",
            (item_count, status, error_blob, run_id),
        )

    audit_logger.log_briefing_event(
        request_id=request_id,
        event_type="briefing_refresh_completed",
        outcome=status,
        item_count=item_count,
    )

    return {
        "run_id": run_id,
        "item_count": item_count,
        "status": status,
        "errors": [{"source": n, "error": e} for n, e in failures],
    }


def _fetch_one(source: Source, *, request_id: str) -> list[dict]:
    """Dispatch to the right fetcher for a source kind."""
    if source.kind == "rss":
        return rss_client.fetch_rss_items(source)

    if source.kind == "weather":
        w = weather_module.fetch_weather(
            settings.briefing_weather_lat, settings.briefing_weather_lon
        )
        if w is None:
            audit_logger.log_briefing_event(
                request_id=request_id,
                event_type="weather_fetch_failed",
                outcome="error",
                source_name=source.name,
                reason="provider unavailable",
            )
            raise rss_client.SourceFetchError("weather provider unavailable")

        audit_logger.log_briefing_event(
            request_id=request_id,
            event_type="weather_fetch_completed",
            outcome="success",
            source_name=source.name,
        )
        return [
            {
                "title": weather_module.format_weather_title(
                    w, settings.briefing_default_location
                ),
                "url": None,
                "published_at": now_iso(),
                "summary": weather_module.format_weather_summary(w),
            }
        ]

    # 'placeholder' (personalized_action_items) — intentionally empty.
    return []


def _is_duplicate(item: dict, category: str) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    url = item.get("url")
    title = item.get("title")
    with db_session() as conn:
        if url:
            row = conn.execute(
                "SELECT 1 FROM briefing_items "
                "WHERE url = ? AND fetched_at > ? LIMIT 1",
                (url, cutoff),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM briefing_items "
                "WHERE category = ? AND title = ? AND fetched_at > ? LIMIT 1",
                (category, title, cutoff),
            ).fetchone()
    return row is not None


# ─── read ─────────────────────────────────────────────────────────────────────


def get_recent_items(
    *,
    request_id: str,
    category: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Read recent items, newest first. If `category` is None, all categories.
    """
    sql = (
        "SELECT id, category, source_name, title, url, published_at, "
        "fetched_at, summary FROM briefing_items WHERE archived = 0"
    )
    params: list[Any] = []
    if category is not None:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit if limit is not None else 50)

    with db_session() as conn:
        rows = conn.execute(sql, params).fetchall()

    audit_logger.log_briefing_event(
        request_id=request_id,
        event_type="briefing_served",
        outcome="success",
        category=category or "all",
        item_count=len(rows),
    )

    return [dict(row) for row in rows]


def get_recent_items_grouped(
    *, request_id: str, per_category: int | None = None
) -> dict[str, list[dict[str, Any]]]:
    cap = per_category or settings.briefing_max_items_per_category
    grouped: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORIES}
    for category in CATEGORIES:
        items = get_recent_items(
            request_id=request_id, category=category, limit=cap
        )
        grouped[category] = items
    return grouped


# ─── /ask cache-aware path ────────────────────────────────────────────────────


def get_or_refresh_daily_briefing(*, request_id: str) -> str:
    """
    Returns a formatted daily briefing string. Auto-refreshes if no
    successful run within BRIEFING_CACHE_MINUTES.
    """
    if not settings.enable_briefing:
        return "Daily briefing is disabled (ENABLE_BRIEFING=false)."

    if not _has_fresh_run(briefing_type="daily"):
        refresh_briefing(request_id=request_id, briefing_type="daily")

    grouped = get_recent_items_grouped(request_id=request_id)

    leading_summary = _maybe_llm_summary(grouped, request_id=request_id)
    return format_daily_briefing(grouped, leading_summary=leading_summary)


def get_category_briefing(*, request_id: str, category: str) -> str:
    if not settings.enable_briefing:
        return "Daily briefing is disabled (ENABLE_BRIEFING=false)."
    if not is_valid_category(category):
        return f"Unknown category '{category}'."

    if not _has_fresh_run(briefing_type="daily"):
        refresh_briefing(
            request_id=request_id,
            briefing_type=f"category:{category}",
            categories=[category],
        )

    items = get_recent_items(
        request_id=request_id,
        category=category,
        limit=settings.briefing_max_items_per_category,
    )
    return format_category_briefing(category, items)


def _has_fresh_run(*, briefing_type: str) -> bool:
    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(minutes=settings.briefing_cache_minutes)
    ).isoformat()
    with db_session() as conn:
        row = conn.execute(
            "SELECT id FROM briefing_runs "
            "WHERE briefing_type = ? "
            "AND status IN ('success','partial') "
            "AND created_at > ? "
            "ORDER BY id DESC LIMIT 1",
            (briefing_type, cutoff),
        ).fetchone()
    return row is not None


def _maybe_llm_summary(
    grouped: dict[str, list[dict[str, Any]]], *, request_id: str
) -> str | None:
    """
    Returns a leading summary string, or None. Both flags must be true
    before any LLM call happens. Failures fall back silently and audit.
    """
    if not (settings.enable_local_llm and settings.enable_llm_briefing_summary):
        return None

    headlines: list[str] = []
    for items in grouped.values():
        for it in items[:3]:
            headlines.append(f"{it['title']} ({it['source_name']})")
    if not headlines:
        return None

    try:
        text = local_llm.generate_briefing_summary(headlines)
    except (local_llm.LocalLLMTimeout, local_llm.LocalLLMUnavailable) as exc:
        audit_logger.log_briefing_event(
            request_id=request_id,
            event_type="llm_briefing_summary_skipped",
            outcome="error",
            reason=str(exc),
        )
        return None

    audit_logger.log_briefing_event(
        request_id=request_id,
        event_type="llm_briefing_summary_used",
        outcome="success",
        item_count=len(headlines),
    )
    return text


# ─── /ask handlers — mapped from intent_router ───────────────────────────────


def handle_daily_briefing(query: str, request_id: str) -> str:
    return get_or_refresh_daily_briefing(request_id=request_id)


def handle_world_briefing(query: str, request_id: str) -> str:
    return get_category_briefing(request_id=request_id, category="world_news")


def handle_ai_briefing(query: str, request_id: str) -> str:
    return get_category_briefing(request_id=request_id, category="ai_news")


def handle_tech_briefing(query: str, request_id: str) -> str:
    return get_category_briefing(request_id=request_id, category="tech_news")


def handle_developer_briefing(query: str, request_id: str) -> str:
    return get_category_briefing(request_id=request_id, category="developer_news")


def handle_weather_briefing(query: str, request_id: str) -> str:
    return get_category_briefing(request_id=request_id, category="boston_weather")


def handle_immigration_briefing(query: str, request_id: str) -> str:
    return get_category_briefing(request_id=request_id, category="immigration_updates")
