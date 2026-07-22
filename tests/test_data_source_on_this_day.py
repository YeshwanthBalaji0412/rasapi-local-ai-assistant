"""
Tests for data_sources.sources.on_this_day.OnThisDaySource.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from data_sources.sources.on_this_day import OnThisDaySource


def _client_factory(handler):
    def factory():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return factory


_SAMPLE_RESPONSE = {
    "events": [
        {
            "year": 1953,
            "text": "Edmund Hillary and Tenzing Norgay reach the summit of Mount Everest.",
            "pages": [
                {
                    "normalizedtitle": "Mount Everest",
                    "extract": "Mount Everest is Earth's highest mountain above sea level.",
                    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Mount_Everest"}},
                }
            ],
        }
    ]
    * 8,  # 8 raw events to prove trimming
    "births": [
        {"year": 1917, "text": "John F. Kennedy", "pages": [{"normalizedtitle": "JFK"}]}
    ]
    * 6,
    "deaths": [
        {"year": 1990, "text": "Sample Death", "pages": [{"normalizedtitle": "Person"}]}
    ]
    * 6,
    "holidays": [{"text": "Democracy Day"}, {"text": "Statehood Day"}],
    "selected": [],
}


# ── happy path ─────────────────────────────────────────────────────────


def test_on_this_day_happy_path():
    handler = lambda req: httpx.Response(200, json=_SAMPLE_RESPONSE)
    src = OnThisDaySource(http_client_factory=_client_factory(handler))
    env = asyncio.run(src.fetch("05/29"))
    assert env.data is not None
    assert env.data["date"] == "05-29"
    # Trimming: 5 events max, 3 births/deaths max, 5 holidays max.
    assert len(env.data["events"]) == 5
    assert len(env.data["births"]) == 3
    assert len(env.data["deaths"]) == 3
    assert env.data["holidays"][0]["text"] == "Democracy Day"


def test_on_this_day_page_extract_included():
    handler = lambda req: httpx.Response(200, json=_SAMPLE_RESPONSE)
    src = OnThisDaySource(http_client_factory=_client_factory(handler))
    env = asyncio.run(src.fetch("05/29"))
    first_event = env.data["events"][0]
    assert first_event["pages"][0]["title"] == "Mount Everest"
    assert first_event["pages"][0]["url"].startswith("https://en.wikipedia.org/")


def test_on_this_day_empty_key_uses_today():
    """No key → source computes today's UTC date."""
    captured_url = {"url": None}

    def handler(req):
        captured_url["url"] = str(req.url)
        return httpx.Response(200, json=_SAMPLE_RESPONSE)

    src = OnThisDaySource(http_client_factory=_client_factory(handler))
    env = asyncio.run(src.fetch(""))
    assert env.data is not None
    today = datetime.now(timezone.utc)
    expected_path = f"/{today.month:02d}/{today.day:02d}"
    assert expected_path in captured_url["url"]


def test_on_this_day_zero_pads_key():
    captured_url = {"url": None}

    def handler(req):
        captured_url["url"] = str(req.url)
        return httpx.Response(200, json=_SAMPLE_RESPONSE)

    src = OnThisDaySource(http_client_factory=_client_factory(handler))
    asyncio.run(src.fetch("5/9"))
    assert "/05/09" in captured_url["url"]


# ── failure paths ──────────────────────────────────────────────────────


def test_on_this_day_http_error_returns_null():
    handler = lambda req: httpx.Response(500)
    src = OnThisDaySource(http_client_factory=_client_factory(handler))
    env = asyncio.run(src.fetch("05/29"))
    assert env.data is None
    assert any("HTTP 500" in w for w in env.warnings)


def test_on_this_day_source_name_and_ttl():
    src = OnThisDaySource()
    assert src.name == "on_this_day"
    assert src.default_ttl_seconds == 60 * 60 * 12
