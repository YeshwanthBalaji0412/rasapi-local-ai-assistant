"""
Weather provider — Open-Meteo (no API key required).

Returns a dict with current temperature, daily high/low, and a simple
condition label, or None if the upstream is unavailable. The generator
treats a None return as a non-fatal source failure.
"""

import logging

import httpx

from config import settings


logger = logging.getLogger(__name__)


_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


# Open-Meteo "weathercode" → human label. Only the buckets we care about.
# Full table: https://open-meteo.com/en/docs
_CODE_LABELS = {
    0: "clear",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog", 48: "fog",
    51: "drizzle", 53: "drizzle", 55: "drizzle",
    61: "rain", 63: "rain", 65: "heavy rain",
    71: "snow", 73: "snow", 75: "heavy snow",
    77: "snow grains",
    80: "rain showers", 81: "rain showers", 82: "violent rain showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm", 99: "thunderstorm",
}


def fetch_weather(lat: float, lon: float) -> dict | None:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": "true",
        "daily": "temperature_2m_max,temperature_2m_min,weathercode",
        "timezone": "auto",
        "forecast_days": 1,
    }
    try:
        resp = httpx.get(
            _OPEN_METEO_URL,
            params=params,
            timeout=settings.briefing_fetch_timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
        logger.warning("Open-Meteo fetch failed: %s", exc)
        return None

    cw = data.get("current_weather") or {}
    daily = data.get("daily") or {}

    def _first(key: str):
        seq = daily.get(key) or []
        return seq[0] if seq else None

    return {
        "temperature_c": cw.get("temperature"),
        "weathercode": cw.get("weathercode"),
        "condition": _CODE_LABELS.get(cw.get("weathercode"), "unknown"),
        "high_c": _first("temperature_2m_max"),
        "low_c": _first("temperature_2m_min"),
    }


def format_weather_title(w: dict, location: str) -> str:
    parts = [location]
    if w.get("temperature_c") is not None:
        parts.append(f"{w['temperature_c']:.0f}°C")
    if w.get("condition"):
        parts.append(w["condition"])
    return ", ".join(parts)


def format_weather_summary(w: dict) -> str:
    bits = []
    if w.get("high_c") is not None and w.get("low_c") is not None:
        bits.append(f"high {w['high_c']:.0f}°C / low {w['low_c']:.0f}°C")
    return "; ".join(bits)
