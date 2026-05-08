import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

from briefing.sources import Source
from core import memory, tasks
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def _stub_items(category: str, n: int = 1) -> list[dict]:
    return [
        {
            "title": f"{category} story {i}",
            "url": f"https://example.com/{category}/{i}",
            "published_at": "2026-05-08",
            "summary": "summary",
        }
        for i in range(1, n + 1)
    ]


# ─── HTML page ───────────────────────────────────────────────────────────────


def test_dashboard_returns_200_html(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


def test_dashboard_contains_app_name(client):
    assert "RasaPi" in client.get("/dashboard").text


def test_dashboard_contains_version(client):
    assert "0.5.0" in client.get("/dashboard").text


def test_dashboard_contains_phase_label(client):
    assert "Phase 5" in client.get("/dashboard").text


def test_dashboard_renders_all_section_headings(client):
    body = client.get("/dashboard").text
    for heading in [
        "Overview",
        "System Health",
        "Assistant Commands",
        "Memory, Notes",
        "Daily Briefing",
        "Local LLM",
        "Recent Audit Events",
        "Security Events",
    ]:
        assert heading in body, f"missing heading: {heading}"


# ─── JSON endpoints ──────────────────────────────────────────────────────────


def test_dashboard_health_returns_json(client):
    resp = client.get("/dashboard/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "python_version" in body
    assert "platform" in body
    assert "disk_total_gb" in body


def test_dashboard_audit_recent_returns_list(client):
    resp = client.get("/dashboard/audit/recent")
    assert resp.status_code == 200
    body = resp.json()
    assert "events" in body
    assert isinstance(body["events"], list)


def test_dashboard_security_events_returns_list(client):
    resp = client.get("/dashboard/security-events")
    assert resp.status_code == 200
    assert isinstance(resp.json()["events"], list)


# ─── empty-state robustness ──────────────────────────────────────────────────


def test_dashboard_works_when_db_is_empty(client):
    """No memory, no notes, no tasks, no briefing — page must still render."""
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "No memory items yet" in resp.text
    assert "No notes yet" in resp.text


def test_dashboard_works_when_audit_log_dir_is_missing(client, tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "audit_log_dir", str(tmp_path / "doesnotexist"))
    resp = client.get("/dashboard")
    assert resp.status_code == 200


# ─── safe write actions ──────────────────────────────────────────────────────


def test_dashboard_briefing_refresh_returns_redirect(client):
    fake = Source("World", "world_news", "rss", "https://example.com/w")
    with patch("briefing.generator.SOURCES", (fake,)), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=_stub_items("world_news"),
    ):
        resp = client.post("/dashboard/briefing/refresh", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"


def test_dashboard_complete_task_marks_done(client):
    _, _, task_id = tasks.add_task(title="ship phase 5", request_id="setup")
    resp = client.post(
        f"/dashboard/tasks/{task_id}/complete", follow_redirects=False
    )
    assert resp.status_code == 303
    # Task should now be done.
    open_tasks = tasks.list_tasks(request_id="verify")
    assert all(t["id"] != task_id for t in open_tasks)


def test_dashboard_complete_unknown_task_still_redirects(client):
    """Missing task → service returns False, but the dashboard still redirects
    so the user gets a sane page (the failure is recorded in audit)."""
    resp = client.post(
        "/dashboard/tasks/9999/complete", follow_redirects=False
    )
    assert resp.status_code == 303


def test_dashboard_renders_memory_and_tasks(client):
    memory.save_memory(value="my hobby is climbing", request_id="setup")
    tasks.add_task(title="write phase 5 docs", request_id="setup")
    body = client.get("/dashboard").text
    assert "my hobby is climbing" in body
    assert "write phase 5 docs" in body
