"""
Tests for data_sources.sources.currency.CurrencySource.
"""
from __future__ import annotations

import asyncio

import httpx

from data_sources.sources.currency import CurrencySource


def _client_factory(handler):
    def factory():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return factory


_SAMPLE_OK = {
    "result": "success",
    "base_code": "USD",
    "provider": "https://www.exchangerate-api.com",
    "time_last_update_utc": "Wed, 29 May 2026 00:00:00 +0000",
    "time_next_update_utc": "Thu, 30 May 2026 00:00:00 +0000",
    "rates": {
        "USD": 1.0,
        "EUR": 0.92,
        "GBP": 0.79,
        "INR": 83.5,
        "XYZ": 0.001,  # will be dropped: not in _COMMON_QUOTES
    },
}


# ── happy path ─────────────────────────────────────────────────────────


def test_currency_happy_path():
    handler = lambda req: httpx.Response(200, json=_SAMPLE_OK)
    src = CurrencySource(http_client_factory=_client_factory(handler))
    env = asyncio.run(src.fetch("USD"))
    assert env.data is not None
    assert env.data["base"] == "USD"
    assert env.data["rates_common"]["EUR"] == 0.92
    assert env.data["rates_common"]["INR"] == 83.5
    # XYZ isn't in _COMMON_QUOTES; must be dropped from the trimmed payload.
    assert "XYZ" not in env.data["rates_common"]
    # rates_all_count reflects the ORIGINAL raw count.
    assert env.data["rates_all_count"] == 5


def test_currency_key_upcased():
    captured_url = {"url": None}

    def handler(req):
        captured_url["url"] = str(req.url)
        return httpx.Response(200, json=_SAMPLE_OK)

    src = CurrencySource(http_client_factory=_client_factory(handler))
    asyncio.run(src.fetch("usd"))
    assert "/USD" in captured_url["url"]


def test_currency_invalid_key_falls_back_to_usd():
    captured_url = {"url": None}

    def handler(req):
        captured_url["url"] = str(req.url)
        return httpx.Response(200, json=_SAMPLE_OK)

    src = CurrencySource(http_client_factory=_client_factory(handler))
    asyncio.run(src.fetch("!!!"))
    assert "/USD" in captured_url["url"]


# ── failure paths ──────────────────────────────────────────────────────


def test_currency_http_error_returns_null():
    handler = lambda req: httpx.Response(503)
    src = CurrencySource(http_client_factory=_client_factory(handler))
    env = asyncio.run(src.fetch("USD"))
    assert env.data is None
    assert any("HTTP 503" in w for w in env.warnings)


def test_currency_upstream_result_error_returns_null():
    handler = lambda req: httpx.Response(
        200, json={"result": "error", "error-type": "unsupported-code"}
    )
    src = CurrencySource(http_client_factory=_client_factory(handler))
    env = asyncio.run(src.fetch("USD"))
    assert env.data is None
    assert any("upstream result=" in w for w in env.warnings)


def test_currency_source_name_and_ttl():
    src = CurrencySource()
    assert src.name == "currency"
    assert src.default_ttl_seconds == 60 * 60 * 6
