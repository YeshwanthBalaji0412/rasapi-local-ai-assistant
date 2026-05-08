import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from briefing import generator, rss_client
from briefing.formatter import IMMIGRATION_DISCLAIMER, format_daily_briefing
from briefing.sources import Source
from config import settings
from storage.database import db_session


def _stub_rss_items(category: str, n: int = 2) -> list[dict]:
    return [
        {
            "title": f"{category} headline {i}",
            "url": f"https://example.com/{category}/{i}",
            "published_at": "2026-05-08",
            "summary": f"summary {i}",
        }
        for i in range(1, n + 1)
    ]


def _patch_sources(*sources):
    return patch("briefing.generator.SOURCES", tuple(sources))


# ─── refresh writes a run row ────────────────────────────────────────────────


def test_refresh_creates_briefing_run_row():
    one_source = Source("FakeWorld", "world_news", "rss", "https://example.com/world")
    with _patch_sources(one_source), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=_stub_rss_items("world_news"),
    ):
        result = generator.refresh_briefing(request_id="r-1")

    assert result["status"] == "success"
    assert result["item_count"] == 2

    with db_session() as conn:
        rows = conn.execute("SELECT * FROM briefing_runs").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "success"
    assert rows[0]["item_count"] == 2


def test_refresh_partial_success_when_one_source_fails():
    good = Source("Good", "world_news", "rss", "https://example.com/good")
    bad = Source("Bad", "ai_news", "rss", "https://example.com/bad")

    def side_effect(source: Source):
        if source.name == "Bad":
            raise rss_client.SourceFetchError("simulated failure")
        return _stub_rss_items("ok", n=1)

    with _patch_sources(good, bad), patch(
        "briefing.generator.rss_client.fetch_rss_items", side_effect=side_effect
    ):
        result = generator.refresh_briefing(request_id="r-2")

    assert result["status"] == "partial"
    assert result["item_count"] == 1
    assert any(e["source"] == "Bad" for e in result["errors"])


def test_refresh_dedupes_repeated_urls():
    s = Source("Dedup", "world_news", "rss", "https://example.com/d")
    items = _stub_rss_items("world_news", n=2)
    with _patch_sources(s), patch(
        "briefing.generator.rss_client.fetch_rss_items", return_value=items
    ):
        first = generator.refresh_briefing(request_id="r-3a")
        second = generator.refresh_briefing(request_id="r-3b")

    assert first["item_count"] == 2
    assert second["item_count"] == 0   # all duplicates


def test_refresh_handles_weather_source():
    weather_src = Source("Weather", "boston_weather", "weather", None)
    fake_weather = {
        "temperature_c": 5.0,
        "condition": "clear",
        "high_c": 8.0,
        "low_c": -1.0,
        "weathercode": 0,
    }
    with _patch_sources(weather_src), patch(
        "briefing.generator.weather_module.fetch_weather", return_value=fake_weather
    ):
        result = generator.refresh_briefing(request_id="r-w")

    assert result["status"] == "success"
    assert result["item_count"] == 1
    items = generator.get_recent_items(request_id="r-w-list", category="boston_weather")
    assert len(items) == 1
    assert "Boston" in items[0]["title"]


def test_refresh_handles_weather_failure_as_partial():
    weather_src = Source("Weather", "boston_weather", "weather", None)
    with _patch_sources(weather_src), patch(
        "briefing.generator.weather_module.fetch_weather", return_value=None
    ):
        result = generator.refresh_briefing(request_id="r-wf")
    assert result["status"] == "partial"


# ─── reads / formatting ──────────────────────────────────────────────────────


def test_get_recent_items_filters_by_category():
    s_world = Source("W", "world_news", "rss", "https://example.com/w")
    s_ai = Source("A", "ai_news", "rss", "https://example.com/a")

    def side_effect(source: Source):
        return _stub_rss_items(source.category, n=2)

    with _patch_sources(s_world, s_ai), patch(
        "briefing.generator.rss_client.fetch_rss_items", side_effect=side_effect
    ):
        generator.refresh_briefing(request_id="r-4")

    ai = generator.get_recent_items(request_id="r-4-ai", category="ai_news")
    assert ai
    assert all(it["category"] == "ai_news" for it in ai)


def test_format_daily_briefing_has_multiple_categories():
    grouped = {
        "world_news": [
            {"title": "World thing", "source_name": "BBC"},
        ],
        "ai_news": [
            {"title": "AI thing", "source_name": "HF"},
        ],
        "tech_news": [],
        "developer_news": [],
        "boston_weather": [],
        "immigration_updates": [],
        "personalized_action_items": [],
    }
    text = format_daily_briefing(grouped)
    assert "WORLD NEWS" in text
    assert "AI NEWS" in text
    assert "World thing" in text
    assert "AI thing" in text


def test_format_immigration_includes_disclaimer():
    grouped = {c: [] for c in (
        "world_news", "ai_news", "tech_news", "developer_news",
        "boston_weather", "immigration_updates", "personalized_action_items",
    )}
    grouped["immigration_updates"] = [
        {"title": "USCIS announces something", "source_name": "USCIS"},
    ]
    text = format_daily_briefing(grouped)
    assert IMMIGRATION_DISCLAIMER in text


def test_format_empty_briefing_is_safe():
    grouped = {c: [] for c in (
        "world_news", "ai_news", "tech_news", "developer_news",
        "boston_weather", "immigration_updates", "personalized_action_items",
    )}
    text = format_daily_briefing(grouped)
    assert "No briefing items yet" in text


# ─── LLM summary gating ──────────────────────────────────────────────────────


def test_llm_summary_skipped_when_both_flags_default(monkeypatch):
    # Defaults: enable_local_llm=False, enable_llm_briefing_summary=False
    s = Source("S", "world_news", "rss", "https://example.com/s")
    with _patch_sources(s), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=_stub_rss_items("world_news"),
    ), patch(
        "briefing.generator.local_llm.generate_briefing_summary"
    ) as mock_llm:
        text = generator.get_or_refresh_daily_briefing(request_id="r-6")

    assert "WORLD NEWS" in text
    mock_llm.assert_not_called()


def test_llm_summary_skipped_when_only_briefing_flag_true(monkeypatch):
    monkeypatch.setattr(settings, "enable_local_llm", False)
    monkeypatch.setattr(settings, "enable_llm_briefing_summary", True)
    s = Source("S", "world_news", "rss", "https://example.com/s2")
    with _patch_sources(s), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=_stub_rss_items("world_news"),
    ), patch(
        "briefing.generator.local_llm.generate_briefing_summary"
    ) as mock_llm:
        generator.get_or_refresh_daily_briefing(request_id="r-7")

    mock_llm.assert_not_called()


def test_llm_summary_used_when_both_flags_true(monkeypatch):
    monkeypatch.setattr(settings, "enable_local_llm", True)
    monkeypatch.setattr(settings, "enable_llm_briefing_summary", True)
    s = Source("S", "world_news", "rss", "https://example.com/s3")
    with _patch_sources(s), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=_stub_rss_items("world_news"),
    ), patch(
        "briefing.generator.local_llm.generate_briefing_summary",
        return_value="It was a busy day in world news.",
    ) as mock_llm:
        text = generator.get_or_refresh_daily_briefing(request_id="r-8")

    mock_llm.assert_called_once()
    # Inspect what was sent: only public headlines, no memory/secrets.
    args, kwargs = mock_llm.call_args
    headlines = args[0] if args else kwargs.get("headlines", [])
    blob = " ".join(headlines).lower()
    assert "password" not in blob
    assert "api_key" not in blob
    assert "It was a busy day" in text


def test_llm_summary_failure_falls_back_silently(monkeypatch):
    from core.local_llm import LocalLLMUnavailable
    monkeypatch.setattr(settings, "enable_local_llm", True)
    monkeypatch.setattr(settings, "enable_llm_briefing_summary", True)
    s = Source("S", "world_news", "rss", "https://example.com/s4")
    with _patch_sources(s), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=_stub_rss_items("world_news"),
    ), patch(
        "briefing.generator.local_llm.generate_briefing_summary",
        side_effect=LocalLLMUnavailable("ollama down"),
    ):
        text = generator.get_or_refresh_daily_briefing(request_id="r-9")

    # Briefing still rendered without LLM summary.
    assert "WORLD NEWS" in text
