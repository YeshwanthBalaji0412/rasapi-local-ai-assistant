"""
Integration registry types (Phase 9).

Pure data classes — no logic, no I/O. Used by the registry, the dashboard,
and the REST surface to describe what RasaPi can talk to without ever
exposing tokens, webhook URLs, or auth headers.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Risk labels for the dashboard. Purely descriptive.
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"


@dataclass(frozen=True)
class IntegrationCapability:
    """One discrete thing an integration can do."""
    name: str
    description: str
    risk: str = RISK_LOW


@dataclass
class IntegrationEntry:
    """Public-facing snapshot for the registry. Never carries secrets."""
    key: str                       # "slack" | "home_assistant" | "alexa_future_stub"
    display_name: str
    enabled: bool
    configured: bool
    status: str                    # "ready" | "disabled" | "not_configured" | "future"
    capabilities: list[IntegrationCapability] = field(default_factory=list)
    risk: str = RISK_LOW
    note: str = ""
    last_event: dict | None = None  # {event_type, timestamp, outcome, target?, reason?}
