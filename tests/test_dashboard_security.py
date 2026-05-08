import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

from briefing.sources import Source
from config import settings
from core import memory
from main import app
from security import audit_reader


@pytest.fixture
def client():
    return TestClient(app)


# ─── No secrets in HTML ──────────────────────────────────────────────────────


def test_dashboard_does_not_contain_api_key_string(client):
    body = client.get("/dashboard").text
    # The literal value of api_secret_key must not appear.
    assert settings.api_secret_key not in body
    assert "API_KEY" not in body


def test_dashboard_does_not_contain_secret_key_string(client):
    body = client.get("/dashboard").text
    assert "SECRET" not in body
    assert "OPENAI" not in body
    assert "CLAUDE_API_KEY" not in body


def test_dashboard_does_not_contain_env_file_marker(client, monkeypatch):
    """Sentinel test: even if a future bug projects env onto the view model,
    a unique token planted in api_secret_key must not surface."""
    sentinel = "SENTINEL-DO-NOT-LEAK-7c3d"
    monkeypatch.setattr(settings, "api_secret_key", sentinel)
    body = client.get("/dashboard").text
    assert sentinel not in body


# ─── HTML escaping & truncation ──────────────────────────────────────────────


def test_html_in_memory_value_is_escaped(client):
    memory.save_memory(value="<script>alert(1)</script>", request_id="esc")
    body = client.get("/dashboard").text
    # Raw script tag must not appear; escaped form must.
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body or "&lt;script" in body


def test_long_memory_value_is_truncated(client):
    long_value = "x" * 1000
    memory.save_memory(value=long_value, request_id="trunc")
    body = client.get("/dashboard").text
    # The full 1000-char string must NOT appear; a truncated-to-200 + ellipsis must.
    assert "x" * 1000 not in body
    # Find the longest run of x's in the response.
    longest_x = max((len(m.group(0)) for m in re.finditer(r"x+", body)), default=0)
    assert longest_x <= 210, f"truncation failed; saw a run of {longest_x} x's"


# ─── DB path masking ─────────────────────────────────────────────────────────


def test_db_path_masked_in_overview(monkeypatch):
    """get_overview() must mask absolute paths when dashboard_mask_db_path=True."""
    from dashboard import service as dash_service

    monkeypatch.setattr(settings, "dashboard_mask_db_path", True)
    monkeypatch.setattr(
        settings, "database_path", "/Users/someone/secret/data/rasapi.db"
    )
    overview = dash_service.get_overview()
    assert "/Users/someone/secret" not in overview["database_path"]
    assert "data/rasapi.db" in overview["database_path"]


def test_db_path_unmasked_when_flag_off(monkeypatch):
    from dashboard import service as dash_service

    monkeypatch.setattr(settings, "dashboard_mask_db_path", False)
    monkeypatch.setattr(
        settings, "database_path", "/Users/someone/visible/rasapi.db"
    )
    overview = dash_service.get_overview()
    assert overview["database_path"] == "/Users/someone/visible/rasapi.db"


def test_dashboard_default_render_does_not_show_absolute_path(client):
    """End-to-end: with masking on (default), the rendered HTML doesn't leak
    a /Users/ or /home/ prefix."""
    body = client.get("/dashboard").text
    # The configured path may be relative ("backend/data/test.db") or absolute
    # (tmp_path inside /private/var/...). Either way, masking should keep
    # only the last two segments visible.
    assert "/Users/" not in body
    assert "/private/var/" not in body
    assert "/home/" not in body


# ─── Form actions are restricted ─────────────────────────────────────────────


_ALLOWED_FORM_ACTION_PREFIXES = (
    "/dashboard/briefing/refresh",
    "/dashboard/tasks/",  # /tasks/{id}/complete
)


def test_dashboard_only_has_whitelisted_form_actions(client):
    body = client.get("/dashboard").text
    actions = re.findall(r'<form\b[^>]*\baction="([^"]+)"', body)
    assert actions, "expected at least one form on the dashboard"
    for action in actions:
        assert any(action.startswith(p) for p in _ALLOWED_FORM_ACTION_PREFIXES), (
            f"unexpected form action in dashboard: {action}"
        )


# ─── audit_reader robustness ─────────────────────────────────────────────────


def test_audit_reader_skips_malformed_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "audit_log_dir", str(tmp_path))
    f = tmp_path / "audit-2026-05-08.jsonl"
    f.write_text(
        '{"timestamp":"t1","event_type":"request"}\n'
        "this is not json\n"
        '{"timestamp":"t2","event_type":"command_exec","outcome":"allowed"}\n'
        "\n"   # blank line
        "{not json either}\n",
        encoding="utf-8",
    )
    events = audit_reader.read_recent(limit=10)
    assert len(events) == 2
    types = {e["event_type"] for e in events}
    assert types == {"request", "command_exec"}


def test_audit_reader_returns_empty_when_log_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "audit_log_dir", str(tmp_path / "nope"))
    assert audit_reader.read_recent(limit=10) == []
    assert audit_reader.read_security_events(limit=10) == []


def test_security_events_endpoint_includes_blocked_memory(client, monkeypatch):
    memory.save_memory(value="my password is hunter2", request_id="block-test")
    resp = client.get("/dashboard/security-events")
    assert resp.status_code == 200
    types = {e["event_type"] for e in resp.json()["events"]}
    assert "sensitive_memory_blocked" in types


# ─── Dashboard write paths cannot reach the command runner ──────────────────


def test_dashboard_briefing_refresh_does_not_invoke_command_runner(client):
    fake = Source("World", "world_news", "rss", "https://example.com/w")
    with patch("briefing.generator.SOURCES", (fake,)), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=[
            {"title": "x", "url": "https://example.com/w/1", "published_at": "", "summary": ""}
        ],
    ), patch(
        "core.command_runner.run_command",
        side_effect=AssertionError("must not be called"),
    ):
        resp = client.post(
            "/dashboard/briefing/refresh", follow_redirects=False
        )
    assert resp.status_code == 303


def test_dashboard_complete_task_does_not_invoke_command_runner(client):
    from core import tasks
    _, _, t_id = tasks.add_task(title="x", request_id="setup")
    with patch(
        "core.command_runner.run_command",
        side_effect=AssertionError("must not be called"),
    ):
        resp = client.post(
            f"/dashboard/tasks/{t_id}/complete", follow_redirects=False
        )
    assert resp.status_code == 303
