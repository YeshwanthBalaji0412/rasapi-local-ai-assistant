"""
On-This-Day source (Wikipedia REST v1).

Public API, no key. One upstream call per fetch. Long-lived cache
(12 hours) — the endpoint only rolls over at midnight UTC.

Key convention: `MM/DD` (e.g. "05/29"). Empty key → today's date UTC.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from data_sources.base import DataSource

ENDPOINT = "https://en.wikipedia.org/api/rest_v1/feed/onthisday/all"

# Trim the raw Wikipedia response to the top-N items per category so payload
# size stays modest. Adjustable via constants if the UI needs more later.
_MAX_EVENTS = 5
_MAX_BIRTHS = 3
_MAX_DEATHS = 3
_MAX_HOLIDAYS = 5


class OnThisDaySource(DataSource):
    name = "on_this_day"
    default_ttl_seconds = 60 * 60 * 12  # 12 hours

    def __init__(
        self,
        cache: Any = None,
        http_client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        super().__init__(cache=cache)
        self._client_factory = http_client_factory or self._default_client_factory

    def _default_client_factory(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            follow_redirects=True,
            headers={
                "User-Agent": "RasaPi (+github.com/YeshwanthBalaji0412/rasapi-local-ai-assistant)",
                "Accept": "application/json",
            },
        )

    def _resolve_key(self, key: str) -> tuple[str, str]:
        """Return (month, day) as zero-padded strings. Empty key → today UTC."""
        if key:
            parts = key.split("/", 1)
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return parts[0].zfill(2), parts[1].zfill(2)
        today = datetime.now(timezone.utc)
        return f"{today.month:02d}", f"{today.day:02d}"

    async def _do_fetch(self, key: str, warnings: list[str]) -> Any | None:
        month, day = self._resolve_key(key)
        url = f"{ENDPOINT}/{month}/{day}"

        async with self._client_factory() as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            warnings.append(f"HTTP {resp.status_code}")
            return None
        raw = resp.json()

        return {
            "date": f"{month}-{day}",
            "events": _trim_events(raw.get("events") or [], _MAX_EVENTS),
            "births": _trim_people(raw.get("births") or [], _MAX_BIRTHS),
            "deaths": _trim_people(raw.get("deaths") or [], _MAX_DEATHS),
            "holidays": _trim_holidays(raw.get("holidays") or [], _MAX_HOLIDAYS),
        }


def _trim_events(items: list[dict], limit: int) -> list[dict]:
    trimmed: list[dict] = []
    for item in items[:limit]:
        trimmed.append(
            {
                "year": item.get("year"),
                "text": item.get("text"),
                "pages": [_page_snippet(p) for p in (item.get("pages") or [])[:2]],
            }
        )
    return trimmed


def _trim_people(items: list[dict], limit: int) -> list[dict]:
    trimmed: list[dict] = []
    for item in items[:limit]:
        trimmed.append(
            {
                "year": item.get("year"),
                "text": item.get("text"),
                "page": _page_snippet((item.get("pages") or [None])[0]) if item.get("pages") else None,
            }
        )
    return trimmed


def _trim_holidays(items: list[dict], limit: int) -> list[dict]:
    trimmed: list[dict] = []
    for item in items[:limit]:
        trimmed.append(
            {
                "text": item.get("text"),
                "page": _page_snippet((item.get("pages") or [None])[0]) if item.get("pages") else None,
            }
        )
    return trimmed


def _page_snippet(page: dict | None) -> dict | None:
    if not page:
        return None
    return {
        "title": page.get("normalizedtitle") or page.get("title"),
        "extract": page.get("extract"),
        "url": (page.get("content_urls") or {}).get("desktop", {}).get("page"),
    }
