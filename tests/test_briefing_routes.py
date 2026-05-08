import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

from briefing.sources import Source
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def _stub_items(category: str, n: int = 2) -> list[dict]:
    return [
        {
            "title": f"{category} headline {i}",
            "url": f"https://example.com/{category}/{i}",
            "published_at": "2026-05-08",
            "summary": "summary",
        }
        for i in range(1, n + 1)
    ]


# ─── /briefing/sources ───────────────────────────────────────────────────────


def test_get_sources_endpoint_returns_categories(client):
    resp = client.get("/briefing/sources")
    assert resp.status_code == 200
    body = resp.json()
    cats = {s["category"] for s in body["sources"]}
    assert "world_news" in cats
    assert "boston_weather" in cats
    assert "personalized_action_items" in body["categories"]


def test_get_sources_does_not_expose_secrets(client):
    resp = client.get("/briefing/sources")
    blob = resp.text
    assert "API_KEY" not in blob
    assert "SECRET" not in blob


# ─── /briefing/refresh ───────────────────────────────────────────────────────


def test_post_refresh_returns_run_metadata(client):
    fake = Source("FakeWorld", "world_news", "rss", "https://example.com/w")
    with patch("briefing.generator.SOURCES", (fake,)), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=_stub_items("world_news"),
    ):
        resp = client.post("/briefing/refresh")

    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] >= 1
    assert body["status"] in {"success", "partial"}
    assert body["item_count"] >= 1


# ─── /briefing/daily ─────────────────────────────────────────────────────────


def test_get_daily_after_refresh_returns_grouped_items(client):
    fake = Source("FakeAI", "ai_news", "rss", "https://example.com/a")
    with patch("briefing.generator.SOURCES", (fake,)), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=_stub_items("ai_news"),
    ):
        client.post("/briefing/refresh")
        resp = client.get("/briefing/daily")

    assert resp.status_code == 200
    body = resp.json()
    assert "AI NEWS" in body["text"]
    assert len(body["items_by_category"]["ai_news"]) >= 1


def test_get_daily_when_empty_returns_explanatory_text(client):
    """No sources = empty briefing, but still 200, not 500."""
    with patch("briefing.generator.SOURCES", ()):
        resp = client.get("/briefing/daily")
    assert resp.status_code == 200
    assert "No briefing items" in resp.json()["text"] or resp.json()["text"]


# ─── /briefing/category/{category} ───────────────────────────────────────────


def test_get_category_returns_only_that_category(client):
    fake_ai = Source("FakeAI", "ai_news", "rss", "https://example.com/a")
    fake_world = Source("FakeW", "world_news", "rss", "https://example.com/w")
    with patch("briefing.generator.SOURCES", (fake_ai, fake_world)), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        side_effect=lambda s: _stub_items(s.category),
    ):
        client.post("/briefing/refresh")
        resp = client.get("/briefing/category/ai_news")

    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] == "ai_news"
    assert all(it["category"] == "ai_news" for it in body["items"])


def test_get_unknown_category_returns_400(client):
    resp = client.get("/briefing/category/not_a_real_category")
    assert resp.status_code == 400


def test_get_immigration_category_returns_disclaimer(client):
    fake = Source("USCIS", "immigration_updates", "rss",
                  "https://example.com/uscis")
    with patch("briefing.generator.SOURCES", (fake,)), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=_stub_items("immigration_updates"),
    ):
        client.post("/briefing/refresh")
        resp = client.get("/briefing/category/immigration_updates")

    body = resp.json()
    assert body["disclaimer"] is not None
    assert "not legal advice" in body["disclaimer"]
    assert "not legal advice" in body["text"]
