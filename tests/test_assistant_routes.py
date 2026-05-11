"""Phase 11 — /assistant page tests."""

import ast
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

from config import settings
from core import chat_history
from main import app


_TEST_KEY = "test-secret-VR1Hh7dQrEKaBiu1hqsfO9xNpV0sa1ZwH4bM"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "enable_auth", True)
    monkeypatch.setattr(settings, "api_secret_key", _TEST_KEY)


@pytest.fixture(autouse=True)
def _reset_history():
    chat_history.clear_all()
    yield
    chat_history.clear_all()


def _login(client):
    return client.post(
        "/login",
        data={"api_key": _TEST_KEY, "next": "/assistant"},
        follow_redirects=False,
    )


# ─── GET /assistant ──────────────────────────────────────────────────────────


def test_assistant_page_opens_when_auth_off(client):
    resp = client.get("/assistant", follow_redirects=False)
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "Send a message" in resp.text


def test_assistant_page_contains_csrf_token_in_form(client):
    body = client.get("/assistant").text
    assert 'name="_csrf"' in body


def test_assistant_page_links_back_to_dashboard(client):
    body = client.get("/assistant").text
    assert 'href="/dashboard"' in body


def test_assistant_page_redirects_to_login_when_auth_on(client, auth_on):
    resp = client.get("/assistant", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login?next=")
    assert "/assistant" in resp.headers["location"] or "%2Fassistant" in resp.headers["location"]


def test_assistant_page_renders_for_authenticated_browser(client, auth_on):
    _login(client)
    resp = client.get("/assistant", follow_redirects=False)
    assert resp.status_code == 200
    assert "Send a message" in resp.text


# ─── POST /assistant/ask (browser, cookie + CSRF) ────────────────────────────


def test_browser_post_requires_csrf_when_auth_on(client, auth_on):
    _login(client)
    # No _csrf field at all
    resp = client.post(
        "/assistant/ask",
        data={"query": "hello"},
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_browser_post_accepts_valid_csrf_and_redirects(client, auth_on):
    _login(client)
    # First GET to receive a CSRF cookie + token in the form
    page = client.get("/assistant")
    assert page.status_code == 200
    csrf_cookie = client.cookies.get(settings.csrf_cookie_name)
    assert csrf_cookie

    resp = client.post(
        "/assistant/ask",
        data={"query": "hello", "_csrf": csrf_cookie},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/assistant"


def test_no_auth_post_works_without_csrf(client):
    resp = client.post(
        "/assistant/ask",
        data={"query": "what time is it"},
        follow_redirects=False,
    )
    assert resp.status_code == 303


def test_response_appears_on_rerendered_page(client):
    client.post(
        "/assistant/ask",
        data={"query": "what time is it"},
        follow_redirects=False,
    )
    body = client.get("/assistant").text
    assert "what time is it" in body
    # The intent label is rendered alongside the exchange.
    assert "intent: time" in body


def test_empty_query_re_renders_with_error(client):
    resp = client.post(
        "/assistant/ask",
        data={"query": "   "},
        follow_redirects=False,
    )
    # Validation here is server-side after trim; we re-render with an inline
    # error banner instead of redirecting.
    assert resp.status_code == 200
    assert "Type a message" in resp.text


# ─── POST /assistant/ask (API client, header, no CSRF) ───────────────────────


def test_api_header_post_skips_csrf(client, auth_on):
    resp = client.post(
        "/assistant/ask",
        data={"query": "hello"},
        headers={"X-RasaPi-Key": _TEST_KEY},
        follow_redirects=False,
    )
    # Same auth dep as /ask — header alone authenticates and bypasses CSRF.
    assert resp.status_code == 303


def test_api_header_post_with_wrong_key_rejected(client, auth_on):
    resp = client.post(
        "/assistant/ask",
        data={"query": "hello"},
        headers={"X-RasaPi-Key": "wrong"},
        follow_redirects=False,
    )
    assert resp.status_code == 401


# ─── chat history bounding ───────────────────────────────────────────────────


def test_chat_history_caps_at_10(client):
    for i in range(15):
        client.post(
            "/assistant/ask",
            data={"query": f"what time is it #{i}"},
            follow_redirects=False,
        )
    # Internal store reflects the cap.
    # Auth is off, so the session key is the client host.
    keys = list(chat_history._store.keys())
    assert len(keys) == 1
    assert len(chat_history.recent(keys[0])) == 10


def test_logout_clears_chat_history(client, auth_on):
    _login(client)
    page = client.get("/assistant")
    csrf_cookie = client.cookies.get(settings.csrf_cookie_name)
    client.post(
        "/assistant/ask",
        data={"query": "remember this", "_csrf": csrf_cookie},
        follow_redirects=False,
    )
    # History exists.
    assert any(chat_history.recent(k) for k in chat_history._store.keys())

    client.post("/logout", follow_redirects=False)
    # Bucket for that session is gone.
    assert all(
        not chat_history.recent(k) for k in chat_history._store.keys()
    )


# ─── POST /assistant/voice-trigger ───────────────────────────────────────────


def test_voice_trigger_returns_403_when_voice_disabled(client):
    resp = client.post(
        "/assistant/voice-trigger",
        follow_redirects=False,
    )
    assert resp.status_code == 403


def test_voice_trigger_runs_session_when_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_voice", True)
    resp = client.post(
        "/assistant/voice-trigger",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/assistant"
    # The exchange is recorded in chat history.
    keys = list(chat_history._store.keys())
    assert keys
    recents = chat_history.recent(keys[0])
    assert recents
    assert recents[-1].query.startswith("[voice]")


def test_voice_trigger_requires_csrf_for_browser(client, monkeypatch, auth_on):
    monkeypatch.setattr(settings, "enable_voice", True)
    _login(client)
    resp = client.post(
        "/assistant/voice-trigger",
        follow_redirects=False,
    )
    assert resp.status_code == 403


# ─── Structural security ─────────────────────────────────────────────────────


_ASSISTANT_FILE = (
    Path(__file__).resolve().parent.parent
    / "backend"
    / "api"
    / "routes"
    / "assistant.py"
)


def test_assistant_module_does_not_import_command_runner():
    tree = ast.parse(_ASSISTANT_FILE.read_text())
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            imports.append(mod)
            imports.extend(f"{mod}.{a.name}" for a in node.names)
    assert not any("command_runner" in i for i in imports)


def test_assistant_module_does_not_import_local_llm_directly():
    tree = ast.parse(_ASSISTANT_FILE.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert "local_llm" not in (node.module or "")
            for a in node.names:
                assert "local_llm" not in a.name


def test_assistant_module_routes_through_process_query():
    """If the module ever stops calling orchestration.process_query, fail."""
    src = _ASSISTANT_FILE.read_text()
    assert "orchestration.process_query" in src


def test_assistant_page_does_not_leak_api_key(client, auth_on):
    _login(client)
    body = client.get("/assistant").text
    assert _TEST_KEY not in body


def test_assistant_page_does_not_render_unescaped_html(client):
    """Submitted HTML in the query must appear escaped on the rerender."""
    client.post(
        "/assistant/ask",
        data={"query": "<script>alert(1)</script>"},
        follow_redirects=False,
    )
    body = client.get("/assistant").text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script" in body
