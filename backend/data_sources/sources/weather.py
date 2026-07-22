"""
Weather source (Open-Meteo).

Public API, no key required. Two upstream calls per fetch:
  1. Geocoding — city name → (latitude, longitude, timezone, country)
  2. Forecast  — coords → current weather block

Both are cached inside the source's fetch cache (one entry per city key),
so /data/weather/boston makes at most one geocode + one forecast every
15 minutes.

Key convention: URL-slug city name. Empty key falls back to the first
entry of DATA_WEATHER_LOCATIONS (or the Phase 4 briefing default).
"""
from __future__ import annotations

from typing import Any, Callable

import httpx

from config import settings
from data_sources.base import DataSource

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather code → short human label. Documented at open-meteo.com.
# Kept small and non-emoji; the UI can decorate.
_WEATHER_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Light rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Light snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Light snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with light hail",
    99: "Thunderstorm with heavy hail",
}


def _c_to_f(c: float) -> float:
    return round(c * 9.0 / 5.0 + 32.0, 1)


class WeatherSource(DataSource):
    name = "weather"
    default_ttl_seconds = 900  # 15 minutes

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
            headers={"User-Agent": "RasaPi (+github.com/YeshwanthBalaji0412/rasapi-local-ai-assistant)"},
        )

    def _resolve_key(self, key: str) -> str:
        """Empty key → configured default city."""
        if key:
            return key
        locations = (settings.__dict__.get("data_weather_locations")
                     or getattr(settings, "briefing_default_location", "Boston, MA"))
        if isinstance(locations, str) and "|" in locations:
            return locations.split("|", 1)[0].strip()
        if isinstance(locations, str):
            return locations
        return "Boston, MA"

    async def _do_fetch(self, key: str, warnings: list[str]) -> Any | None:
        query = self._resolve_key(key)
        async with self._client_factory() as client:
            geocode_resp = await client.get(
                GEOCODE_URL, params={"name": query, "count": 1, "language": "en", "format": "json"}
            )
            if geocode_resp.status_code != 200:
                warnings.append(f"geocode HTTP {geocode_resp.status_code}")
                return None
            geocode_json = geocode_resp.json()
            results = geocode_json.get("results") or []
            if not results:
                warnings.append(f"no geocode match for {query!r}")
                return None
            location = results[0]

            forecast_resp = await client.get(
                FORECAST_URL,
                params={
                    "latitude": location["latitude"],
                    "longitude": location["longitude"],
                    "current_weather": "true",
                    "timezone": location.get("timezone") or "UTC",
                },
            )
            if forecast_resp.status_code != 200:
                warnings.append(f"forecast HTTP {forecast_resp.status_code}")
                return None
            forecast_json = forecast_resp.json()
            current = forecast_json.get("current_weather")
            if current is None:
                warnings.append("forecast response missing current_weather")
                return None

        temp_c = current.get("temperature")
        code = current.get("weathercode")
        return {
            "location": {
                "query": query,
                "name": location.get("name"),
                "country": location.get("country"),
                "admin1": location.get("admin1"),
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude"),
                "timezone": location.get("timezone"),
            },
            "current": {
                "temperature_c": temp_c,
                "temperature_f": _c_to_f(temp_c) if isinstance(temp_c, (int, float)) else None,
                "wind_speed_kmh": current.get("windspeed"),
                "wind_direction_deg": current.get("winddirection"),
                "weather_code": code,
                "weather_description": _WEATHER_CODES.get(code, "Unknown"),
                "observed_at": current.get("time"),
            },
        }
