"""
DataSource — the abstract base every /data/* source implements.

Contract for subclasses:

  1. Set `name` (unique, snake_case, matches the URL slug).
  2. Set `default_ttl_seconds` (how long a fresh fetch stays valid).
  3. Optionally override `is_enabled()` to gate on config or an API key.
  4. Implement `_do_fetch(key, warnings) -> data | None`. Never raise from
     this method — append to `warnings` and return None if data can't be
     produced. The base class owns timeout / retry / cache / envelope
     construction; subclasses stay tightly scoped to their upstream.

Rules the base class enforces (see tests/test_data_base.py):

  - Total fetch time is bounded by `timeout_seconds` per attempt, times
    (retries + 1) attempts, plus a 2-second backoff between attempts.
  - Every response is wrapped in the same Envelope shape — the UI layer
    can render staleness, warnings, and cache_hit uniformly.
  - A disabled source returns `data=None` with a warning; the endpoint
    returns HTTP 200. Disabled != error.
  - On fresh-fetch failure with a stale cache present, stale data is
    served with a "stale, upstream unreachable" warning (opt-out via
    DATA_STALE_FALLBACK=false in .env).
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from config import settings

logger = logging.getLogger(__name__)


def _iso_z(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class SourceResult:
    """Internal return from a source module's helper functions. Not part of
    the wire envelope. Sources may use this if they build data in stages."""

    data: Any | None
    warnings: list[str] = field(default_factory=list)


@dataclass
class Envelope:
    """The response shape every /data/* endpoint returns.

    Wire JSON:
        {
          "source": "weather_world",
          "key": "boston",
          "fetched_at": "2026-05-29T14:22:31Z",
          "cache_hit": true,
          "cache_expires_at": "2026-05-29T14:52:31Z",
          "data": { ... } | null,
          "warnings": ["..."]
        }
    """

    source: str
    key: str
    fetched_at: datetime
    cache_hit: bool
    cache_expires_at: datetime | None
    data: Any | None
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "key": self.key,
            "fetched_at": _iso_z(self.fetched_at),
            "cache_hit": self.cache_hit,
            "cache_expires_at": _iso_z(self.cache_expires_at),
            "data": self.data,
            "warnings": list(self.warnings),
        }


class DataSource(ABC):
    """Abstract base. Subclasses set metadata and implement `_do_fetch`."""

    #: URL-slug for the source. Must be unique across the registry.
    name: str = ""
    #: How long a fresh fetch is considered valid before we go upstream again.
    default_ttl_seconds: int = 300

    def __init__(
        self,
        cache: Any = None,
        timeout_seconds: float | None = None,
        retries: int = 1,
    ) -> None:
        if not self.name:
            raise ValueError(
                f"{type(self).__name__} must set a non-empty `name` class attribute"
            )
        self._cache = cache
        self._timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else float(getattr(settings, "data_fetch_timeout_seconds", 10))
        )
        self._retries = max(0, retries)

    # ── subclass hooks ──────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        """Override to gate on config or credentials.

        Default: always enabled. Sources that need an API key should return
        False and populate `disabled_reason()` when the key is missing.
        """
        return True

    def disabled_reason(self) -> str:
        """Human-readable reason surfaced in the warning list when disabled."""
        return f"{self.name} disabled"

    @abstractmethod
    async def _do_fetch(self, key: str, warnings: list[str]) -> Any | None:
        """Perform the actual upstream fetch and return the payload.

        Rules:
          - Never raise. Append to `warnings` and return None if the fetch
            can't produce data. The base class treats any raised exception
            as a fatal fetch (fed into the retry loop, then None).
          - `warnings` is mutable and shared across retry attempts. Append
            per attempt so the caller sees the sequence.
          - `key` is the URL slug (e.g. "boston" for weather). Sources with
            a single canonical key can accept it as an empty string.
        """

    # ── public entry point ──────────────────────────────────────────────

    async def fetch(self, key: str = "") -> Envelope:
        """Cache-first fetch. Public API for routes and tests."""
        now = datetime.now(timezone.utc)

        # 1. Disabled? Return null envelope, no upstream call, no cache work.
        if not self.is_enabled():
            return Envelope(
                source=self.name,
                key=key,
                fetched_at=now,
                cache_hit=False,
                cache_expires_at=None,
                data=None,
                warnings=[self.disabled_reason()],
            )

        # 2. Fresh cache hit?
        if self._cache is not None and settings.data_cache_enabled:
            fresh = self._cache.get(self.name, key)
            if fresh is not None:
                return Envelope(
                    source=self.name,
                    key=key,
                    fetched_at=fresh.fetched_at,
                    cache_hit=True,
                    cache_expires_at=fresh.expires_at,
                    data=fresh.payload,
                    warnings=[],
                )

        # 3. Try upstream (with timeout + retry).
        warnings: list[str] = []
        data = await self._fetch_with_retry(key, warnings)

        # 4. Fresh fetch failed. Stale fallback?
        if data is None and self._cache is not None and settings.data_stale_fallback:
            stale = self._cache.get(self.name, key, include_expired=True)
            if stale is not None:
                warnings.append("stale, upstream unreachable")
                return Envelope(
                    source=self.name,
                    key=key,
                    fetched_at=stale.fetched_at,
                    cache_hit=True,
                    cache_expires_at=stale.expires_at,
                    data=stale.payload,
                    warnings=warnings,
                )

        # 5. Success? Write to cache and return.
        expires_at: datetime | None = None
        if data is not None:
            expires_at = now + timedelta(seconds=self.default_ttl_seconds)
            if self._cache is not None and settings.data_cache_enabled:
                try:
                    self._cache.set(self.name, key, data, now, expires_at)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "cache write failed for source=%s key=%s: %s",
                        self.name,
                        key,
                        e,
                    )

        return Envelope(
            source=self.name,
            key=key,
            fetched_at=now,
            cache_hit=False,
            cache_expires_at=expires_at,
            data=data,
            warnings=warnings,
        )

    # ── internal ────────────────────────────────────────────────────────

    async def _fetch_with_retry(self, key: str, warnings: list[str]) -> Any | None:
        attempts = self._retries + 1
        for attempt in range(attempts):
            try:
                result = await asyncio.wait_for(
                    self._do_fetch(key, warnings), timeout=self._timeout
                )
                # A source may correctly return None (e.g. "no matches").
                # Only treat exceptions/timeouts as a reason to retry.
                return result
            except asyncio.TimeoutError:
                warnings.append(
                    f"timeout after {self._timeout}s "
                    f"(attempt {attempt + 1}/{attempts})"
                )
            except Exception as e:  # noqa: BLE001
                warnings.append(
                    f"{type(e).__name__} (attempt {attempt + 1}/{attempts})"
                )
            if attempt < attempts - 1:
                await asyncio.sleep(2.0)
        return None
