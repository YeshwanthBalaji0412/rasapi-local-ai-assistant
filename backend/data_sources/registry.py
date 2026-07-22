"""
Registry of DataSource instances.

Sources register themselves at import time (see backend/main.py lifespan
or a dedicated bootstrap module in later gates). The registry exposes:

  - names() / all()          — enumerate sources
  - get(name)                — look up a source by URL slug
  - health_for(name)         — per-source health snapshot
  - all_health()             — snapshot of every registered source
  - record_fetch(name, ok)   — bookkeeping call from the /data route

Health is intentionally minimal: enabled flag, disabled reason (nullable),
last fetch timestamp, and last fetch ok flag. This is what /data/sources
returns; no per-source private state leaks through.

The registry is a module-level singleton. `reset_registry_for_tests()`
zeroes it — tests that register mock sources should call this in a fixture
so they never leak into other tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .base import DataSource


@dataclass
class SourceHealth:
    name: str
    enabled: bool
    disabled_reason: str | None
    last_fetch_at: datetime | None
    last_fetch_ok: bool | None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "disabled_reason": self.disabled_reason,
            "last_fetch_at": (
                self.last_fetch_at.astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
                if self.last_fetch_at
                else None
            ),
            "last_fetch_ok": self.last_fetch_ok,
        }


class SourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, DataSource] = {}
        self._health: dict[str, SourceHealth] = {}

    def register(self, source: DataSource) -> None:
        if not source.name:
            raise ValueError("source must have a non-empty .name attribute")
        if source.name in self._sources:
            raise ValueError(f"source already registered: {source.name!r}")
        self._sources[source.name] = source
        self._health[source.name] = SourceHealth(
            name=source.name,
            enabled=source.is_enabled(),
            disabled_reason=(
                None if source.is_enabled() else source.disabled_reason()
            ),
            last_fetch_at=None,
            last_fetch_ok=None,
        )

    def get(self, name: str) -> DataSource | None:
        return self._sources.get(name)

    def names(self) -> list[str]:
        return sorted(self._sources.keys())

    def all(self) -> Iterable[DataSource]:
        return self._sources.values()

    def all_health(self) -> list[SourceHealth]:
        result: list[SourceHealth] = []
        for name in self.names():
            source = self._sources[name]
            h = self._health[name]
            # Refresh enabled state each read — config can change.
            h.enabled = source.is_enabled()
            h.disabled_reason = None if h.enabled else source.disabled_reason()
            result.append(h)
        return result

    def health_for(self, name: str) -> SourceHealth | None:
        h = self._health.get(name)
        if h is None:
            return None
        source = self._sources[name]
        h.enabled = source.is_enabled()
        h.disabled_reason = None if h.enabled else source.disabled_reason()
        return h

    def record_fetch(self, name: str, ok: bool) -> None:
        h = self._health.get(name)
        if h is None:
            return
        h.last_fetch_at = datetime.now(timezone.utc)
        h.last_fetch_ok = ok


# ── module-level singleton ──────────────────────────────────────────────

_registry: SourceRegistry | None = None


def get_registry() -> SourceRegistry:
    global _registry
    if _registry is None:
        _registry = SourceRegistry()
    return _registry


def reset_registry_for_tests() -> None:
    """Zero the registry. Tests only."""
    global _registry
    _registry = None
