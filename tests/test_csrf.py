import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

from config import settings
from main import app


_TEST_KEY = "test-secret-VR1Hh7dQrEKaBiu1hqsfO9xNpV0sa1ZwH4bM"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "enable_auth", True)
    monkeypatch.setattr(settings, "api_secret_key", _TEST_KEY)


def _login(client) -> None:
    resp = client.post(
        "/login",
        data={"api_key": _TEST_KEY, "next": "/dashboard"},
        follow_redirects=False,
    )
    assert resp.status_code == 303


def _csrf_token(client) -> str:
    """Visit /dashboard, return the CSRF cookie value the server set."""
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200
    # TestClient persists cookies; read from the jar.
    return client.cookies.get(settings.csrf_cookie_name)


# ─── CSRF cookie behaviour ───────────────────────────────────────────────────


def test_dashboard_get_sets_csrf_cookie(client, auth_on):
    _login(client)
    token = _csrf_token(client)
    assert token is not None
    assert len(token) >= 16


def test_dashboard_html_contains_csrf_input(client, auth_on):
    _login(client)
    body = client.get("/dashboard").text
    assert 'name="_csrf"' in body


# ─── Form POST with valid CSRF + session succeeds ────────────────────────────


def test_briefing_refresh_with_valid_csrf_succeeds(client, auth_on, monkeypatch):
    from briefing.sources import Source
    from unittest.mock import patch

    fake = Source("World", "world_news", "rss", "https://example.com/w")
    _login(client)
    token = _csrf_token(client)

    with patch("briefing.generator.SOURCES", (fake,)), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=[
            {"title": "x", "url": "https://example.com/w/1",
             "published_at": "", "summary": ""}
        ],
    ):
        resp = client.post(
            "/dashboard/briefing/refresh",
            data={"_csrf": token},
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"


# ─── Form POST without / with wrong CSRF fails ───────────────────────────────


def test_briefing_refresh_without_csrf_token_fails(client, auth_on):
    _login(client)
    resp = client.post(
        "/dashboard/briefing/refresh",
        data={},  # no _csrf
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_briefing_refresh_with_mismatched_csrf_fails(client, auth_on):
    _login(client)
    _csrf_token(client)  # ensures cookie is set
    resp = client.post(
        "/dashboard/briefing/refresh",
        data={"_csrf": "totally-different-value"},
        follow_redirects=False,
    )
    assert resp.status_code == 403


# ─── CSRF skipped when auth is disabled (no regression) ─────────────────────


def test_briefing_refresh_without_csrf_succeeds_when_auth_off(client, monkeypatch):
    """Existing local-dev workflow: posts without tokens still work when
    ENABLE_AUTH=false."""
    from briefing.sources import Source
    from unittest.mock import patch

    fake = Source("World", "world_news", "rss", "https://example.com/w")
    with patch("briefing.generator.SOURCES", (fake,)), patch(
        "briefing.generator.rss_client.fetch_rss_items",
        return_value=[
            {"title": "x", "url": "https://example.com/w/1",
             "published_at": "", "summary": ""}
        ],
    ):
        resp = client.post(
            "/dashboard/briefing/refresh", follow_redirects=False
        )
    assert resp.status_code == 303
