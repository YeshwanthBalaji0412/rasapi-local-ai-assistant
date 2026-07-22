"""
Currency source (open.er-api.com — free tier of exchangerate-api.com).

Public API, no key required for the `open.er-api.com` endpoint. Returns
rates for ~160 currencies referenced against a single base. Long-lived
cache (6 hours) — the upstream itself refreshes every 24h on the free tier.

Key convention: 3-letter base currency (e.g. "USD"). Empty key falls
back to the value of DATA_CURRENCY_BASE (default USD).

Note on premium features: exchangerate-api.com's *paid* API (v6/latest/USD)
requires a key. Gate 5 will add a paid CurrencyProSource that gates on
EXCHANGERATE_API_KEY for historical rates. This module intentionally uses
only the always-free endpoint.
"""
from __future__ import annotations

from typing import Any, Callable

import httpx

from config import settings
from data_sources.base import DataSource

ENDPOINT = "https://open.er-api.com/v6/latest"

# Only surface rates for a subset of common currencies unless the caller
# explicitly asks for the full set. Keeps the payload small on the wire.
_COMMON_QUOTES: tuple[str, ...] = (
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "CAD",
    "AUD",
    "CHF",
    "CNY",
    "INR",
    "SGD",
    "HKD",
    "MXN",
    "BRL",
    "ZAR",
    "SEK",
    "NOK",
    "NZD",
    "KRW",
    "AED",
)


class CurrencySource(DataSource):
    name = "currency"
    default_ttl_seconds = 60 * 60 * 6  # 6 hours

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

    def _resolve_key(self, key: str) -> str:
        candidate = (key or getattr(settings, "data_currency_base", "USD")).upper()
        if len(candidate) != 3 or not candidate.isalpha():
            return "USD"
        return candidate

    async def _do_fetch(self, key: str, warnings: list[str]) -> Any | None:
        base = self._resolve_key(key)
        url = f"{ENDPOINT}/{base}"

        async with self._client_factory() as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            warnings.append(f"HTTP {resp.status_code}")
            return None
        raw = resp.json()

        if raw.get("result") != "success":
            warnings.append(f"upstream result={raw.get('result')!r}")
            return None

        rates_all = raw.get("rates") or {}
        rates_common: dict[str, float] = {
            code: rates_all[code] for code in _COMMON_QUOTES if code in rates_all
        }
        return {
            "base": raw.get("base_code") or base,
            "provider": raw.get("provider"),
            "time_last_update_utc": raw.get("time_last_update_utc"),
            "time_next_update_utc": raw.get("time_next_update_utc"),
            "rates_common": rates_common,
            "rates_all_count": len(rates_all),
        }
