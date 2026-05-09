"""
Slack integration via incoming webhook (Phase 9).

No bot OAuth. No slash commands. No reply handling. RasaPi only POSTs
preformatted messages built from existing internal sources (briefing
formatter, fixed test string).

The webhook URL is read from settings.slack_webhook_url and never echoed
in responses, never written to audit log entries, never displayed on the
dashboard.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from briefing import generator as briefing_generator
from briefing.formatter import format_category_briefing, format_daily_briefing
from briefing.sources import is_valid_category
from config import settings
from security.audit_log import audit_logger


logger = logging.getLogger(__name__)


_TIMEOUT_SECONDS = 10
_TEST_MESSAGE = (
    "✅ RasaPi Slack integration test — your webhook is wired up. "
    "Replies and slash commands are not handled in this phase."
)


class SlackError(Exception):
    """Slack delivery failed."""


class SlackNotConfigured(SlackError):
    """Integration is disabled or webhook URL is empty."""


class SlackHttpError(SlackError):
    """Slack returned a non-2xx response, or the request timed out."""


# ─── public surface ─────────────────────────────────────────────────────────


def is_enabled() -> bool:
    return bool(settings.enable_slack)


def is_configured() -> bool:
    return is_enabled() and bool(settings.slack_webhook_url.strip())


def safe_status() -> dict[str, Any]:
    """Status snapshot for the registry/dashboard. No secrets."""
    return {
        "enabled": is_enabled(),
        "configured": is_configured(),
        "send_briefing_enabled": bool(settings.slack_send_briefing_enabled),
        "send_audit_alerts_enabled": bool(settings.slack_send_audit_alerts_enabled),
        "default_channel": settings.slack_default_channel or "(webhook default)",
    }


def send_test(*, request_id: str) -> str:
    """Post a fixed test message. Returns the user-facing summary."""
    if not is_configured():
        audit_logger.log_integration_event(
            request_id=request_id,
            event_type="slack_test_failed",
            outcome="error",
            integration="slack",
            reason="not_configured",
        )
        raise SlackNotConfigured(
            "Slack is not enabled or SLACK_WEBHOOK_URL is empty."
        )
    _post(_TEST_MESSAGE, request_id=request_id, kind="test")
    audit_logger.log_integration_event(
        request_id=request_id,
        event_type="slack_test_sent",
        outcome="success",
        integration="slack",
    )
    return "Slack test notification sent."


def send_briefing(*, request_id: str, category: str | None = None) -> str:
    """
    Post a briefing summary. If `category` is None, posts the daily
    briefing across all categories. Otherwise posts the per-category
    briefing.
    """
    if not is_configured():
        audit_logger.log_integration_event(
            request_id=request_id,
            event_type="slack_briefing_failed",
            outcome="error",
            integration="slack",
            reason="not_configured",
        )
        raise SlackNotConfigured(
            "Slack is not enabled or SLACK_WEBHOOK_URL is empty."
        )

    if category and is_valid_category(category):
        items = briefing_generator.get_recent_items(
            request_id=request_id,
            category=category,
            limit=settings.briefing_max_items_per_category,
        )
        text = format_category_briefing(category, items)
        target = f"category:{category}"
    else:
        grouped = briefing_generator.get_recent_items_grouped(
            request_id=request_id
        )
        text = format_daily_briefing(grouped)
        target = "daily"

    header = "🗞️ RasaPi briefing\n\n"
    _post(header + text, request_id=request_id, kind="briefing")
    audit_logger.log_integration_event(
        request_id=request_id,
        event_type="slack_briefing_sent",
        outcome="success",
        integration="slack",
        target=target,
    )
    if category:
        return f"Sent {category.replace('_', ' ')} briefing to Slack."
    return "Sent daily briefing to Slack."


# ─── internals ──────────────────────────────────────────────────────────────


def _post(text: str, *, request_id: str, kind: str) -> None:
    """POST to the configured webhook. Raises SlackHttpError on failure.
    The webhook URL is never returned, logged, or echoed."""
    url = settings.slack_webhook_url
    payload = {"text": text}
    try:
        response = httpx.post(url, json=payload, timeout=_TIMEOUT_SECONDS)
    except httpx.TimeoutException as exc:
        logger.warning("Slack post timed out (%s)", kind)
        audit_logger.log_integration_event(
            request_id=request_id,
            event_type=f"slack_{kind}_failed",
            outcome="error",
            integration="slack",
            reason="timeout",
        )
        raise SlackHttpError("Slack request timed out") from exc
    except httpx.RequestError as exc:
        logger.warning("Slack post failed (%s): %s", kind, exc)
        audit_logger.log_integration_event(
            request_id=request_id,
            event_type=f"slack_{kind}_failed",
            outcome="error",
            integration="slack",
            reason="connection_error",
        )
        raise SlackHttpError("Slack request failed") from exc

    if response.status_code >= 400:
        audit_logger.log_integration_event(
            request_id=request_id,
            event_type=f"slack_{kind}_failed",
            outcome="error",
            integration="slack",
            reason=f"http_{response.status_code}",
        )
        raise SlackHttpError(f"Slack returned HTTP {response.status_code}")


# ─── /ask handlers ──────────────────────────────────────────────────────────


_BRIEFING_CATEGORY_KEYWORDS: dict[str, str] = {
    "ai": "ai_news",
    "ml": "ai_news",
    "machine learning": "ai_news",
    "world": "world_news",
    "tech": "tech_news",
    "developer": "developer_news",
    "hacker": "developer_news",
    "weather": "boston_weather",
    "immigration": "immigration_updates",
    "uscis": "immigration_updates",
    "f-1": "immigration_updates",
    "f1 ": "immigration_updates",
    "opt": "immigration_updates",
}


def _detect_category(query: str) -> str | None:
    q = query.lower()
    for keyword, category in _BRIEFING_CATEGORY_KEYWORDS.items():
        if keyword in q:
            return category
    return None


def handle_send_test(query: str, request_id: str) -> str:
    try:
        return send_test(request_id=request_id)
    except SlackNotConfigured as exc:
        return f"Can't send to Slack: {exc}"
    except SlackError as exc:
        return f"Slack send failed: {exc}"


def handle_send_briefing(query: str, request_id: str) -> str:
    category = _detect_category(query)
    try:
        return send_briefing(request_id=request_id, category=category)
    except SlackNotConfigured as exc:
        return f"Can't send to Slack: {exc}"
    except SlackError as exc:
        return f"Slack send failed: {exc}"
