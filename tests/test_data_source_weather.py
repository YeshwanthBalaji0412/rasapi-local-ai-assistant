"""
Tests for data_sources.sources.weather.WeatherSource.

Injects an httpx MockTransport so no real network calls happen. Verifies:
  - happy path returns the expected envelope
  - empty key falls back to a default
  - geocode 404-ish (empty results) returns null data + warning
  - forecast 500 returns null data + warning
"""
from __future__ import annotations

import asyncio

import httpx

from data_sources.sources.weather import WeatherSource


_GEOCODE_OK = {
    "results": [
        {
            "name": "Boston",
            "country": "United States",
            "admin1": "Massachusetts",
            "latitude": 42.3601,
            "longitude": -71.0589,
            "timezone": "America/New_York",
        }
    ]
}

_FORECAST_OK = {
    "current_weather": {
        "temperature": 20.0,
        "windspeed": 8.5,
        "winddirection": 210,
        "weathercode": 3,
        "time": "2026-05-29T14:00",
    }
}


def _client_factory(handler):
    """Build a factory that yields an httpx.AsyncClient with a MockTransport."""

    def factory():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return factory


# ── happy path ─────────────────────────────────────────────────────────


def test_weather_happy_path():
    def handler(request):
        if "geocoding-api" in str(request.url):
            return httpx.Response(200, json=_GEOCODE_OK)
        return httpx.Response(200, json=_FORECAST_OK)

    src = WeatherSource(http_client_factory=_client_factory(handler))
    env = asyncio.run(src.fetch("Boston"))
    assert env.data is not None
    assert env.data["location"]["name"] == "Boston"
    assert env.data["current"]["temperature_c"] == 20.0
    assert env.data["current"]["temperature_f"] == 68.0  # 20°C = 68°F
    assert env.data["current"]["weather_description"] == "Overcast"
    assert env.warnings == []


def test_weather_empty_key_uses_default_location():
    """No key → the source should still make a valid fetch by resolving
    to a configured/default location."""
    def handler(request):
        if "geocoding-api" in str(request.url):
            return httpx.Response(200, json=_GEOCODE_OK)
        return httpx.Response(200, json=_FORECAST_OK)

    src = WeatherSource(http_client_factory=_client_factory(handler))
    env = asyncio.run(src.fetch(""))
    assert env.data is not None
    # Should have resolved to something — key on envelope stays "" (framework
    # invariant: the URL slug is preserved), but the returned data payload
    # reflects the resolved query.
    assert env.data["location"]["query"] != ""


# ── failure paths ──────────────────────────────────────────────────────


def test_weather_no_geocode_match_returns_null_with_warning():
    def handler(request):
        if "geocoding-api" in str(request.url):
            return httpx.Response(200, json={"results": []})
        return httpx.Response(500)

    src = WeatherSource(http_client_factory=_client_factory(handler))
    env = asyncio.run(src.fetch("Atlantis"))
    assert env.data is None
    assert any("no geocode match" in w for w in env.warnings)


def test_weather_geocode_http_error_returns_null_with_warning():
    def handler(request):
        if "geocoding-api" in str(request.url):
            return httpx.Response(503)
        return httpx.Response(200, json=_FORECAST_OK)

    src = WeatherSource(http_client_factory=_client_factory(handler))
    env = asyncio.run(src.fetch("Boston"))
    assert env.data is None
    assert any("geocode HTTP 503" in w for w in env.warnings)


def test_weather_forecast_http_error_returns_null_with_warning():
    def handler(request):
        if "geocoding-api" in str(request.url):
            return httpx.Response(200, json=_GEOCODE_OK)
        return httpx.Response(500)

    src = WeatherSource(http_client_factory=_client_factory(handler))
    env = asyncio.run(src.fetch("Boston"))
    assert env.data is None
    assert any("forecast HTTP 500" in w for w in env.warnings)


def test_weather_forecast_missing_current_returns_null_with_warning():
    def handler(request):
        if "geocoding-api" in str(request.url):
            return httpx.Response(200, json=_GEOCODE_OK)
        return httpx.Response(200, json={})  # no current_weather key

    src = WeatherSource(http_client_factory=_client_factory(handler))
    env = asyncio.run(src.fetch("Boston"))
    assert env.data is None
    assert any("missing current_weather" in w for w in env.warnings)


# ── envelope invariants ────────────────────────────────────────────────


def test_weather_source_name_and_ttl():
    src = WeatherSource()
    assert src.name == "weather"
    assert src.default_ttl_seconds == 900
