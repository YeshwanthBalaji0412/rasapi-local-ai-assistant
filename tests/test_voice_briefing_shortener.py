"""Phase 11 — voice-only briefing shortener tests."""

import asyncio
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from briefing.formatter import IMMIGRATION_DISCLAIMER, format_daily_briefing
from config import settings
from voice import briefing_shortener
from voice import session as session_module
from voice import stt as stt_module
from voice import tts as tts_module


def _make_briefing() -> str:
    items = {
        "world_news": [
            {"title": "World 1", "source_name": "BBC"},
            {"title": "World 2", "source_name": "NPR"},
            {"title": "World 3", "source_name": "BBC"},
        ],
        "ai_news": [
            {"title": "AI 1", "source_name": "HF"},
            {"title": "AI 2", "source_name": "Google AI"},
        ],
        "tech_news": [
            {"title": "Tech 1", "source_name": "Ars"},
        ],
        "developer_news": [],
        "boston_weather": [
            {"title": "Sunny, 72F"},
        ],
        "immigration_updates": [
            {"title": "F-1 update", "source_name": "USCIS"},
            {"title": "OPT update", "source_name": "USCIS"},
        ],
    }
    return format_daily_briefing(items)


# ─── pure shortener ──────────────────────────────────────────────────────────


def test_non_briefing_response_unchanged_when_short():
    out = briefing_shortener.maybe_shorten_for_voice(
        intent="time",
        response="It is 3pm.",
        max_spoken_chars=1200,
        briefing_items_per_category=1,
    )
    assert out == "It is 3pm."


def test_non_briefing_response_truncated_when_too_long():
    long = "x" * 5000
    out = briefing_shortener.maybe_shorten_for_voice(
        intent="fallback",
        response=long,
        max_spoken_chars=200,
        briefing_items_per_category=1,
    )
    assert len(out) <= 220  # 200 + ellipsis padding
    assert out.endswith("…")


def test_empty_response_returns_empty():
    out = briefing_shortener.maybe_shorten_for_voice(
        intent="daily_briefing",
        response="",
        max_spoken_chars=1200,
        briefing_items_per_category=1,
    )
    assert out == ""


def test_daily_briefing_keeps_one_item_per_category():
    full = _make_briefing()
    short = briefing_shortener.maybe_shorten_for_voice(
        intent="daily_briefing",
        response=full,
        max_spoken_chars=10_000,
        briefing_items_per_category=1,
    )
    assert "World 1" in short
    assert "World 2" not in short
    assert "World 3" not in short
    assert "AI 1" in short
    assert "AI 2" not in short
    assert "Tech 1" in short  # only one item to start with


def test_daily_briefing_keeps_all_category_headers():
    full = _make_briefing()
    short = briefing_shortener.maybe_shorten_for_voice(
        intent="daily_briefing",
        response=full,
        max_spoken_chars=10_000,
        briefing_items_per_category=1,
    )
    for header in ("WORLD NEWS", "AI NEWS", "TECH NEWS", "WEATHER", "IMMIGRATION UPDATES"):
        assert header in short


def test_daily_briefing_preserves_immigration_disclaimer():
    full = _make_briefing()
    short = briefing_shortener.maybe_shorten_for_voice(
        intent="daily_briefing",
        response=full,
        max_spoken_chars=10_000,
        briefing_items_per_category=1,
    )
    # The whole disclaimer (or its leading clause) must survive.
    assert IMMIGRATION_DISCLAIMER[:40] in short


def test_daily_briefing_respects_max_spoken_chars():
    full = _make_briefing()
    short = briefing_shortener.maybe_shorten_for_voice(
        intent="daily_briefing",
        response=full,
        max_spoken_chars=200,
        briefing_items_per_category=5,
    )
    assert len(short) <= 220


def test_daily_briefing_with_zero_items_per_category_drops_items_but_keeps_headers():
    full = _make_briefing()
    short = briefing_shortener.maybe_shorten_for_voice(
        intent="daily_briefing",
        response=full,
        max_spoken_chars=10_000,
        briefing_items_per_category=0,
    )
    assert "WORLD NEWS" in short
    assert "World 1" not in short


def test_daily_briefing_no_items_passthrough():
    msg = "No briefing items yet. Run POST /briefing/refresh to populate, or try again in a moment."
    out = briefing_shortener.maybe_shorten_for_voice(
        intent="daily_briefing",
        response=msg,
        max_spoken_chars=1200,
        briefing_items_per_category=1,
    )
    assert out == msg


# ─── voice session integration ───────────────────────────────────────────────


@pytest.fixture
def voice_on(monkeypatch):
    monkeypatch.setattr(settings, "enable_voice", True)


def test_voice_session_shortens_briefing_for_tts_only(voice_on, monkeypatch):
    """TTS payload is shortened; the VoiceResult.response remains full."""
    full = _make_briefing()

    async def fake_process(*, query, request_id):
        return ("daily_briefing", full, "local")

    monkeypatch.setattr(stt_module, "DEFAULT_MOCK_TRANSCRIPT", "daily briefing")
    monkeypatch.setattr(session_module.orchestration, "process_query", fake_process)
    monkeypatch.setattr(settings, "voice_max_spoken_chars", 10_000)
    monkeypatch.setattr(settings, "voice_briefing_items_per_category", 1)

    tts_module.reset_mock_history()
    result = asyncio.run(session_module.run_session_once())
    spoken = list(tts_module.MockTTS.spoken)

    # JSON result keeps the full briefing
    assert result.response == full
    # The thing actually spoken is shorter and includes only first items
    assert any("World 1" in s for s in spoken)
    assert not any("World 2" in s for s in spoken)
    assert any(IMMIGRATION_DISCLAIMER[:40] in s for s in spoken)


def test_voice_session_does_not_shorten_non_briefing(voice_on, monkeypatch):
    async def fake_process(*, query, request_id):
        return ("greeting", "Hello there!", "local")

    monkeypatch.setattr(stt_module, "DEFAULT_MOCK_TRANSCRIPT", "hello")
    monkeypatch.setattr(session_module.orchestration, "process_query", fake_process)

    tts_module.reset_mock_history()
    result = asyncio.run(session_module.run_session_once())
    spoken = list(tts_module.MockTTS.spoken)

    assert result.response == "Hello there!"
    assert any("Hello there!" in s for s in spoken)
