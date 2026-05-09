"""
Phase 4 routing & cross-phase regression tests.
"""

import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

from briefing.sources import Source
from config import settings
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def _stub_items(category: str, n: int = 2) -> list[dict]:
    return [
        {
            "title": f"{category} story {i}",
            "url": f"https://example.com/{category}/{i}",
            "published_at": "2026-05-08",
            "summary": "summary",
        }
        for i in range(1, n + 1)
    ]


def _patched_world_only():
    s = Source("World", "world_news", "rss", "https://example.com/w")
    return patch("briefing.generator.SOURCES", (s,)), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=_stub_items("world_news"),
    )


# ─── /ask routes correctly to each briefing intent ───────────────────────────


def test_daily_briefing_intent(client):
    src_patch, fetch_patch = _patched_world_only()
    with src_patch, fetch_patch:
        resp = client.post("/ask", json={"query": "what's happening today"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "daily_briefing"


def test_world_briefing_intent(client):
    src_patch, fetch_patch = _patched_world_only()
    with src_patch, fetch_patch:
        resp = client.post("/ask", json={"query": "world news"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "world_briefing"


def test_ai_briefing_intent(client):
    s = Source("AI", "ai_news", "rss", "https://example.com/ai")
    with patch("briefing.generator.SOURCES", (s,)), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=_stub_items("ai_news"),
    ):
        resp = client.post("/ask", json={"query": "give me AI news"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "ai_briefing"


def test_tech_briefing_intent(client):
    s = Source("Tech", "tech_news", "rss", "https://example.com/t")
    with patch("briefing.generator.SOURCES", (s,)), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=_stub_items("tech_news"),
    ):
        resp = client.post("/ask", json={"query": "tech news"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "tech_briefing"


def test_developer_briefing_intent(client):
    s = Source("HN", "developer_news", "rss", "https://example.com/hn")
    with patch("briefing.generator.SOURCES", (s,)), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=_stub_items("developer_news"),
    ):
        resp = client.post("/ask", json={"query": "hacker news"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "developer_briefing"


def test_weather_briefing_intent(client):
    s = Source("WX", "boston_weather", "weather", None)
    with patch("briefing.generator.SOURCES", (s,)), patch(
        "briefing.generator.weather_module.fetch_weather",
        return_value={"temperature_c": 5.0, "condition": "clear",
                      "high_c": 8.0, "low_c": -1.0, "weathercode": 0},
    ):
        resp = client.post("/ask", json={"query": "Boston weather"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "weather_briefing"


def test_immigration_briefing_includes_disclaimer(client):
    s = Source("USCIS", "immigration_updates", "rss", "https://example.com/u")
    with patch("briefing.generator.SOURCES", (s,)), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=_stub_items("immigration_updates"),
    ):
        resp = client.post("/ask", json={"query": "F1 OPT updates"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "immigration_briefing"
    assert "not legal advice" in body["response"]


# ─── briefing path never invokes command runner or conversational LLM ───────


def test_briefing_intent_does_not_invoke_command_runner(client):
    src_patch, fetch_patch = _patched_world_only()
    with src_patch, fetch_patch, patch(
        "core.command_runner.run_command",
        side_effect=AssertionError("must not be called"),
    ):
        resp = client.post("/ask", json={"query": "daily briefing"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "daily_briefing"


def test_briefing_intent_does_not_invoke_conversational_llm(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_local_llm", True)
    src_patch, fetch_patch = _patched_world_only()
    with src_patch, fetch_patch, patch(
        "core.orchestration.local_llm.generate_chat_response",
        new_callable=AsyncMock,
    ) as mock_llm:
        resp = client.post("/ask", json={"query": "daily briefing"})
    assert resp.status_code == 200
    mock_llm.assert_not_called()


# ─── briefing package does not import user-data services ────────────────────


def test_briefing_package_does_not_import_memory_or_tasks_or_subprocess():
    """Structural test: no module under briefing/ imports core/memory.py,
    core/tasks.py, core/command_runner.py, or subprocess."""
    import ast
    from pathlib import Path

    import briefing as briefing_pkg

    forbidden_modules = {
        "core.memory", "core.tasks", "core.command_runner",
        "subprocess",
    }
    forbidden_names = {"run_command"}

    pkg_dir = Path(briefing_pkg.__file__).parent
    offenders = []
    for path in pkg_dir.glob("*.py"):
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_modules:
                        offenders.append(f"{path.name} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module in forbidden_modules:
                    offenders.append(f"{path.name} imports from {node.module}")
                for alias in node.names:
                    if alias.name in forbidden_names:
                        offenders.append(f"{path.name} imports {alias.name}")

    assert not offenders, "Briefing package leaks user-data deps: " + "; ".join(offenders)


# ─── earlier-phase regressions ───────────────────────────────────────────────


def test_phase1_time_intent_still_works(client):
    resp = client.post("/ask", json={"query": "what time is it"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "time"


def test_phase3_save_memory_still_works(client):
    resp = client.post("/ask", json={"query": "remember that I love python"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "save_memory"


def test_phase3_add_task_still_works(client):
    resp = client.post("/ask", json={"query": "add task ship phase 4"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "add_task"


def test_phase2_llm_fallback_still_works_for_non_briefing_unknowns(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_local_llm", True)
    with patch(
        "core.orchestration.local_llm.generate_chat_response",
        new=AsyncMock(return_value="A duck is a waterfowl."),
    ):
        resp = client.post("/ask", json={"query": "tell me a fun fact about ducks"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "llm_fallback"
