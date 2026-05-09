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


# ─── No-auth path keeps working ──────────────────────────────────────────────


def test_dashboard_open_when_auth_disabled(client):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200
    assert "RasaPi" in resp.text


# ─── Redirect when not authenticated ─────────────────────────────────────────


def test_dashboard_redirects_to_login_when_auth_on(client, auth_on):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login?next=")
    # The original path is preserved in `next` (encoded or literal — both
    # are valid; what matters is that it points back to /dashboard).
    assert "/dashboard" in resp.headers["location"] or "%2Fdashboard" in resp.headers["location"]


def test_dashboard_audit_endpoint_returns_401_when_auth_on(client, auth_on):
    resp = client.get("/dashboard/audit/recent")
    assert resp.status_code == 401


def test_dashboard_health_remains_public_when_auth_on(client, auth_on):
    resp = client.get("/dashboard/health")
    assert resp.status_code == 200


# ─── Login flow ──────────────────────────────────────────────────────────────


def test_login_form_renders(client, auth_on):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert 'name="api_key"' in resp.text
    assert 'method="post"' in resp.text


def test_login_with_correct_key_sets_cookie_and_redirects(client, auth_on):
    resp = client.post(
        "/login",
        data={"api_key": _TEST_KEY, "next": "/dashboard"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"
    # Cookie was set on the response
    set_cookie = resp.headers.get("set-cookie", "")
    assert settings.session_cookie_name in set_cookie
    assert "HttpOnly" in set_cookie


def test_login_with_wrong_key_does_not_set_cookie(client, auth_on):
    resp = client.post(
        "/login",
        data={"api_key": "totally-wrong-key", "next": "/dashboard"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login?error=1")
    set_cookie = resp.headers.get("set-cookie", "")
    # No session cookie issued
    assert f"{settings.session_cookie_name}=eyJ" not in set_cookie  # signed token starts with eyJ for our payload


def test_authenticated_dashboard_returns_200(client, auth_on):
    # Log in first
    login = client.post(
        "/login",
        data={"api_key": _TEST_KEY, "next": "/dashboard"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    # TestClient persists cookies — subsequent GET should succeed
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200
    assert "RasaPi" in resp.text


def test_logout_clears_cookie(client, auth_on):
    client.post(
        "/login",
        data={"api_key": _TEST_KEY, "next": "/dashboard"},
        follow_redirects=False,
    )
    resp = client.post("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
    set_cookie = resp.headers.get("set-cookie", "")
    # Cookie cleared via Max-Age=0
    assert f"{settings.session_cookie_name}=" in set_cookie
    assert "Max-Age=0" in set_cookie


# ─── Open-redirect protection on `next` ──────────────────────────────────────


def test_login_next_param_rejects_external_url(client, auth_on):
    resp = client.post(
        "/login",
        data={"api_key": _TEST_KEY, "next": "https://evil.com/x"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"


def test_login_next_param_rejects_protocol_relative(client, auth_on):
    resp = client.post(
        "/login",
        data={"api_key": _TEST_KEY, "next": "//evil.com/x"},
        follow_redirects=False,
    )
    assert resp.headers["location"] == "/dashboard"


# ─── Security card renders correct flags ────────────────────────────────────


def test_security_card_shows_disabled_when_auth_off(client):
    body = client.get("/dashboard").text
    assert "<h2>Security</h2>" in body
    # Auth disabled badge should appear


def test_security_card_does_not_leak_api_key(client, auth_on):
    # Authenticated GET
    client.post(
        "/login",
        data={"api_key": _TEST_KEY, "next": "/dashboard"},
        follow_redirects=False,
    )
    body = client.get("/dashboard").text
    assert _TEST_KEY not in body
    assert "API_SECRET_KEY" not in body


def test_voice_status_does_not_leak_api_key(client, auth_on):
    body = client.get("/voice/status").text
    assert _TEST_KEY not in body
