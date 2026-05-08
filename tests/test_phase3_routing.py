"""
Phase 3 routing & security regression tests.

These check that adding the memory/task layer didn't break Phase 1/2 and
that the new layer respects the same security boundaries.
"""

import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

from config import settings
from core import memory, tasks
from main import app
from storage.database import db_session


@pytest.fixture
def client():
    return TestClient(app)


# ─── Phase 1 still works ──────────────────────────────────────────────────────


def test_phase1_time_intent_still_works(client):
    resp = client.post("/ask", json={"query": "what time is it"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "time"


def test_phase1_memory_usage_intent_still_works(client):
    """The renamed Phase 1 intent (memory → memory_usage) still answers RAM."""
    resp = client.post("/ask", json={"query": "free memory"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "memory_usage"


def test_show_memory_routes_to_phase3_not_phase1(client):
    """Disambiguation: 'show memory' must hit list_memory, not memory_usage."""
    memory.save_memory(value="dummy", request_id="t-pre")
    resp = client.post("/ask", json={"query": "show memory"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "list_memory"


# ─── Phase 2 LLM fallback still works for unknown queries ─────────────────────


def test_unknown_query_still_reaches_llm_when_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_local_llm", True)
    with patch(
        "api.routes.assistant.local_llm.generate_chat_response",
        new=AsyncMock(return_value="Sure, here's a fact about ducks."),
    ) as mock_llm:
        resp = client.post("/ask", json={"query": "tell me a fun fact about ducks"})
        assert resp.status_code == 200
        assert resp.json()["intent"] == "llm_fallback"
        mock_llm.assert_awaited_once()


# ─── Memory operations never call the LLM ────────────────────────────────────


def test_memory_intent_skips_llm(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_local_llm", True)
    with patch("api.routes.assistant.local_llm.generate_chat_response", new_callable=AsyncMock) as mock_llm:
        resp = client.post("/ask", json={"query": "remember that I love python"})
        assert resp.status_code == 200
        assert resp.json()["intent"] == "save_memory"
        mock_llm.assert_not_called()


def test_task_intent_skips_llm(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_local_llm", True)
    with patch("api.routes.assistant.local_llm.generate_chat_response", new_callable=AsyncMock) as mock_llm:
        resp = client.post("/ask", json={"query": "add task review pull requests"})
        assert resp.status_code == 200
        assert resp.json()["intent"] == "add_task"
        mock_llm.assert_not_called()


# ─── LLM cannot create memory or tasks ───────────────────────────────────────


def test_llm_response_does_not_create_memory(client, monkeypatch):
    """
    Even if the LLM returns text saying 'I'll remember that for you', no
    memory row is written. The LLM has no path to save_memory.
    """
    monkeypatch.setattr(settings, "enable_local_llm", True)
    with patch(
        "api.routes.assistant.local_llm.generate_chat_response",
        new=AsyncMock(return_value="Sure, I'll remember that. Saved!"),
    ):
        # Genuinely unknown query — falls through router to LLM.
        resp = client.post("/ask", json={"query": "tell me something philosophical"})
        assert resp.status_code == 200
        assert resp.json()["intent"] == "llm_fallback"

    with db_session() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM memory_items").fetchone()["c"]
    assert count == 0


def test_llm_response_does_not_create_tasks(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_local_llm", True)
    with patch(
        "api.routes.assistant.local_llm.generate_chat_response",
        new=AsyncMock(return_value="I've created a task for you to do that."),
    ):
        resp = client.post("/ask", json={"query": "tell me something philosophical"})
        assert resp.status_code == 200

    with db_session() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"]
    assert count == 0


# ─── Memory/task ops never invoke the command runner ─────────────────────────


def test_memory_save_does_not_invoke_command_runner(client):
    with patch("core.command_runner.run_command", side_effect=AssertionError("must not be called")):
        resp = client.post("/ask", json={"query": "remember that today is sunny"})
        assert resp.status_code == 200
        assert resp.json()["intent"] == "save_memory"


def test_task_add_does_not_invoke_command_runner(client):
    with patch("core.command_runner.run_command", side_effect=AssertionError("must not be called")):
        resp = client.post("/ask", json={"query": "add task ship phase 3"})
        assert resp.status_code == 200
        assert resp.json()["intent"] == "add_task"
