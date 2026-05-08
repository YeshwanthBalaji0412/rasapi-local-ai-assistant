"""
RSS / Atom client (Phase 4).

Fetches via httpx (so timeouts are explicit and tests can mock at the HTTP
layer), then hands the raw bytes to feedparser. feedparser tolerates a wide
range of variants which is exactly why we accepted the dependency.

Failures raise SourceFetchError so the generator can audit them and continue
with remaining sources. Empty / malformed feeds return [] (not an error).
"""

import logging

import feedparser
import httpx

from briefing.sources import Source
from config import settings


logger = logging.getLogger(__name__)


_USER_AGENT = "RasaPi/0.4 (+local-first-ai-assistant)"
_MAX_TITLE_CHARS = 500
_MAX_SUMMARY_CHARS = 600
_MAX_URL_CHARS = 2000


class SourceFetchError(Exception):
    """A source could not be fetched (network error, timeout, HTTP error)."""


def fetch_rss_items(source: Source) -> list[dict]:
    if source.kind != "rss" or not source.url:
        return []

    try:
        resp = httpx.get(
            source.url,
            timeout=settings.briefing_fetch_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        )
        resp.raise_for_status()
    except httpx.TimeoutException as exc:
        raise SourceFetchError(f"timeout: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        raise SourceFetchError(f"http {resp.status_code}") from exc
    except httpx.RequestError as exc:
        raise SourceFetchError(f"request error: {exc}") from exc

    parsed = feedparser.parse(resp.content)

    items: list[dict] = []
    seen_urls: set[str] = set()
    for entry in parsed.entries:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        url = (entry.get("link") or "").strip()
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        published = entry.get("published") or entry.get("updated") or ""
        summary_raw = entry.get("summary") or ""

        items.append(
            {
                "title": title[:_MAX_TITLE_CHARS],
                "url": url[:_MAX_URL_CHARS] if url else None,
                "published_at": str(published)[:64],
                "summary": str(summary_raw)[:_MAX_SUMMARY_CHARS],
            }
        )

    return items
