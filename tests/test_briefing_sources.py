import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import httpx
import pytest

from briefing import rss_client, sources, weather as weather_module
from briefing.sources import Source


FIXTURES = Path(__file__).parent / "fixtures"


# ─── source registry ─────────────────────────────────────────────────────────


def test_sources_cover_expected_categories():
    cats = {s.category for s in sources.SOURCES}
    assert "world_news" in cats
    assert "ai_news" in cats
    assert "tech_news" in cats
    assert "developer_news" in cats
    assert "boston_weather" in cats
    assert "immigration_updates" in cats


def test_list_sources_safe_does_not_leak_secrets():
    listing = sources.list_sources_safe()
    # Each entry has exactly the expected public fields.
    for entry in listing:
        assert set(entry.keys()) == {"name", "category", "kind", "url"}
    # No env-var-looking values.
    blob = repr(listing)
    assert "API_KEY" not in blob
    assert "SECRET" not in blob


def test_categories_constant_includes_personalized_stub():
    assert "personalized_action_items" in sources.CATEGORIES


def test_is_valid_category_rejects_unknown():
    assert sources.is_valid_category("ai_news") is True
    assert sources.is_valid_category("not_a_real_category") is False


# ─── RSS client ──────────────────────────────────────────────────────────────


def _mock_response(content: bytes, status: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.content = content
    resp.status_code = status
    if status >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "err", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


@pytest.fixture
def sample_source():
    return Source("Sample", "world_news", "rss", "https://example.com/feed")


def test_rss_client_parses_fixture(sample_source):
    content = (FIXTURES / "sample_rss.xml").read_bytes()
    with patch("briefing.rss_client.httpx.get", return_value=_mock_response(content)):
        items = rss_client.fetch_rss_items(sample_source)
    titles = [it["title"] for it in items]
    assert "First headline about local AI" in titles
    assert "Second headline on Raspberry Pi" in titles


def test_rss_client_deduplicates_same_url(sample_source):
    content = (FIXTURES / "sample_rss.xml").read_bytes()
    with patch("briefing.rss_client.httpx.get", return_value=_mock_response(content)):
        items = rss_client.fetch_rss_items(sample_source)
    urls = [it["url"] for it in items]
    # Fixture has 3 items; two share the same URL → only one kept.
    assert urls.count("https://example.com/articles/2") == 1


def test_rss_client_handles_empty_feed(sample_source):
    empty = b"<?xml version='1.0'?><rss><channel></channel></rss>"
    with patch("briefing.rss_client.httpx.get", return_value=_mock_response(empty)):
        items = rss_client.fetch_rss_items(sample_source)
    assert items == []


def test_rss_client_handles_malformed_feed(sample_source):
    garbage = b"not actually xml at all <<>>"
    with patch("briefing.rss_client.httpx.get", return_value=_mock_response(garbage)):
        items = rss_client.fetch_rss_items(sample_source)
    assert items == []


def test_rss_client_raises_on_timeout(sample_source):
    with patch("briefing.rss_client.httpx.get", side_effect=httpx.TimeoutException("slow")):
        with pytest.raises(rss_client.SourceFetchError, match="timeout"):
            rss_client.fetch_rss_items(sample_source)


def test_rss_client_raises_on_connection_error(sample_source):
    with patch("briefing.rss_client.httpx.get", side_effect=httpx.ConnectError("nope")):
        with pytest.raises(rss_client.SourceFetchError):
            rss_client.fetch_rss_items(sample_source)


def test_rss_client_raises_on_5xx(sample_source):
    with patch("briefing.rss_client.httpx.get", return_value=_mock_response(b"err", status=503)):
        with pytest.raises(rss_client.SourceFetchError):
            rss_client.fetch_rss_items(sample_source)


# ─── weather ─────────────────────────────────────────────────────────────────


def _weather_response(payload: dict) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


def test_weather_parses_open_meteo_payload():
    payload = {
        "current_weather": {"temperature": 5.2, "weathercode": 2},
        "daily": {
            "temperature_2m_max": [8.0],
            "temperature_2m_min": [-1.0],
            "weathercode": [2],
        },
    }
    with patch("briefing.weather.httpx.get", return_value=_weather_response(payload)):
        result = weather_module.fetch_weather(42.36, -71.06)
    assert result is not None
    assert result["temperature_c"] == 5.2
    assert result["condition"] == "partly cloudy"
    assert result["high_c"] == 8.0


def test_weather_returns_none_on_failure():
    with patch("briefing.weather.httpx.get", side_effect=httpx.ConnectError("boom")):
        result = weather_module.fetch_weather(42.36, -71.06)
    assert result is None


def test_weather_format_title_includes_location_and_temp():
    title = weather_module.format_weather_title(
        {"temperature_c": 12.0, "condition": "clear"}, "Boston, MA"
    )
    assert "Boston" in title
    assert "12" in title
    assert "clear" in title
