"""
Integration registry (Phase 9).

Public-facing snapshot of every integration RasaPi knows about. Used by
the dashboard's Integrations card and by GET /integrations. Never
exposes webhook URLs, tokens, or auth headers.
"""

from __future__ import annotations

from integrations import home_assistant as ha
from integrations import slack
from integrations.types import (
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    IntegrationCapability,
    IntegrationEntry,
)
from security import audit_reader


_VOICE_TYPES_FOR_LAST_EVENT: dict[str, set[str]] = {
    "slack": {
        "slack_test_sent",
        "slack_test_failed",
        "slack_briefing_sent",
        "slack_briefing_failed",
    },
    "home_assistant": {
        "home_assistant_status_checked",
        "home_assistant_entity_listed",
        "home_assistant_state_read",
        "home_assistant_action_requested",
        "home_assistant_action_completed",
        "home_assistant_action_blocked",
    },
}


def _last_event_for(integration_key: str) -> dict | None:
    types = _VOICE_TYPES_FOR_LAST_EVENT.get(integration_key)
    if not types:
        return None
    rows = audit_reader.read_events_by_types(event_types=types, limit=1)
    return rows[0] if rows else None


def _slack_status_word() -> str:
    if not slack.is_enabled():
        return "disabled"
    if not slack.is_configured():
        return "not_configured"
    return "ready"


def _ha_status_word() -> str:
    if not ha.is_enabled():
        return "disabled"
    if not ha.is_configured():
        return "not_configured"
    return "ready"


def list_integrations() -> list[IntegrationEntry]:
    return [
        IntegrationEntry(
            key="slack",
            display_name="Slack",
            enabled=slack.is_enabled(),
            configured=slack.is_configured(),
            status=_slack_status_word(),
            risk=RISK_LOW,
            capabilities=[
                IntegrationCapability("send_test", "Post a fixed test message"),
                IntegrationCapability("send_briefing", "Post the daily or per-category briefing"),
            ],
            note="Incoming webhook only. No bot OAuth, no replies.",
            last_event=_last_event_for("slack"),
        ),
        IntegrationEntry(
            key="home_assistant",
            display_name="Home Assistant",
            enabled=ha.is_enabled(),
            configured=ha.is_configured(),
            status=_ha_status_word(),
            risk=RISK_MEDIUM,
            capabilities=[
                IntegrationCapability("status", "Check HA reachability"),
                IntegrationCapability("list_entities", "List allowed entities only"),
                IntegrationCapability("read_state", "Read state of an allowed entity"),
                IntegrationCapability(
                    "turn_on", "Turn on an allowed light/switch entity",
                    risk=RISK_MEDIUM,
                ),
                IntegrationCapability(
                    "turn_off", "Turn off an allowed light/switch entity",
                    risk=RISK_MEDIUM,
                ),
            ],
            note=(
                "Two-layer allowlist (domain + entity_id). Hard-blocked "
                "domains: lock, alarm_control_panel, cover, camera, "
                "device_tracker, person."
            ),
            last_event=_last_event_for("home_assistant"),
        ),
        IntegrationEntry(
            key="alexa_future_stub",
            display_name="Alexa (future)",
            enabled=False,
            configured=False,
            status="future",
            risk=RISK_HIGH,
            capabilities=[],
            note=(
                "Direct Alexa integration is not implemented in Phase 9. "
                "The recommended path is RasaPi → Home Assistant → "
                "Alexa-compatible devices, or an authenticated Alexa Skill "
                "after HTTPS/reverse-proxy hardening (later phase)."
            ),
            last_event=None,
        ),
    ]


def to_safe_dicts() -> list[dict]:
    """JSON-serialisable form for /integrations and the dashboard view-model."""
    out: list[dict] = []
    for entry in list_integrations():
        out.append(
            {
                "key": entry.key,
                "display_name": entry.display_name,
                "enabled": entry.enabled,
                "configured": entry.configured,
                "status": entry.status,
                "risk": entry.risk,
                "note": entry.note,
                "capabilities": [
                    {"name": c.name, "description": c.description, "risk": c.risk}
                    for c in entry.capabilities
                ],
                "last_event": entry.last_event,
            }
        )
    return out
