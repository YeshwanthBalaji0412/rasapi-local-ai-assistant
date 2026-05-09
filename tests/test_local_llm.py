import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

from main import app
from config import settings
from core import local_llm


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def llm_enabled(monkeypatch):
    monkeypatch.setattr(settings, "enable_local_llm", True)


@pytest.fixture
def llm_disabled(monkeypatch):
    monkeypatch.setattr(settings, "enable_local_llm", False)


# ─── 1. Known intents must never call the LLM ─────────────────────────────────


def test_known_intent_skips_llm(client, llm_enabled):
    with patch("core.orchestration.local_llm.generate_chat_response", new_callable=AsyncMock) as mock_llm:
        resp = client.post("/ask", json={"query": "hello"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "greeting"
        mock_llm.assert_not_called()


def test_command_intent_skips_llm(client, llm_enabled):
    with patch("core.orchestration.local_llm.generate_chat_response", new_callable=AsyncMock) as mock_llm:
        resp = client.post("/ask", json={"query": "what time is it"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "time"
        mock_llm.assert_not_called()


# ─── 2. Fallback + LLM enabled = LLM is called ────────────────────────────────


def test_fallback_calls_llm_when_enabled(client, llm_enabled):
    with patch(
        "core.orchestration.local_llm.generate_chat_response",
        new=AsyncMock(return_value="A Raspberry Pi is a small single-board computer."),
    ) as mock_llm:
        resp = client.post(
            "/ask",
            json={"query": "explain Raspberry Pi in one sentence"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "llm_fallback"
        assert body["source"] == "local_llm"
        assert "Raspberry Pi" in body["response"]
        mock_llm.assert_awaited_once()


# ─── 3. Fallback + LLM disabled = NO LLM call ─────────────────────────────────


def test_fallback_skips_llm_when_disabled(client, llm_disabled):
    with patch("core.orchestration.local_llm.generate_chat_response", new_callable=AsyncMock) as mock_llm:
        resp = client.post("/ask", json={"query": "explain Raspberry Pi in one sentence"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "fallback"
        assert body["source"] == "local"
        mock_llm.assert_not_called()


# ─── 4. Ollama unavailable / timeout = safe fallback message ──────────────────


def test_ollama_timeout_returns_safe_message(client, llm_enabled):
    with patch(
        "core.orchestration.local_llm.generate_chat_response",
        new=AsyncMock(side_effect=local_llm.LocalLLMTimeout("timeout")),
    ):
        resp = client.post("/ask", json={"query": "tell me a joke"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "llm_unavailable"
        assert body["source"] == "local"
        assert "unavailable" in body["response"].lower()


def test_ollama_connection_error_returns_safe_message(client, llm_enabled):
    with patch(
        "core.orchestration.local_llm.generate_chat_response",
        new=AsyncMock(side_effect=local_llm.LocalLLMUnavailable("connection refused")),
    ):
        resp = client.post("/ask", json={"query": "tell me a joke"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "llm_unavailable"
        assert "unavailable" in body["response"].lower()


# ─── 5. LLM output is treated as opaque text only ─────────────────────────────


def test_llm_response_returned_verbatim_as_text(client, llm_enabled):
    weird_text = "Sure! `rm -rf /` would delete everything (don't run that)."
    with patch(
        "core.orchestration.local_llm.generate_chat_response",
        new=AsyncMock(return_value=weird_text),
    ):
        resp = client.post("/ask", json={"query": "what does rm rf do"})
        assert resp.status_code == 200
        body = resp.json()
        # The LLM "mentioning" a dangerous command produces text, nothing more.
        assert body["response"] == weird_text
        assert body["intent"] == "llm_fallback"


# ─── 6. The linchpin: LLM cannot reach the command runner ────────────────────


def test_llm_response_never_invokes_command_runner(client, llm_enabled):
    """
    Even if the LLM 'asks' us to run something, the assistant route must
    never reach run_command. We assert this by mocking run_command to raise
    if invoked, and routing a fallback query through a malicious LLM stub.
    """
    with patch("core.command_runner.run_command", side_effect=AssertionError("LLM must never reach run_command")):
        with patch(
            "core.orchestration.local_llm.generate_chat_response",
            new=AsyncMock(return_value="Run this: df -h && rm -rf ~"),
        ):
            resp = client.post("/ask", json={"query": "what should I do next"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["intent"] == "llm_fallback"
            # If run_command had been touched, the AssertionError would have
            # surfaced as a 500. Reaching here means it was never invoked.


def test_local_llm_module_does_not_import_executor():
    """
    Structural test: the local_llm module must not import the command
    runner, the allowlist, or subprocess. This guarantees the LLM has no
    code path to an executor regardless of any future bug in the route.
    """
    import ast
    import core.local_llm as llm_mod

    with open(llm_mod.__file__, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    forbidden = {"subprocess", "os.system"}
    forbidden_modules = {"core.command_runner", "security.allowlist", "core.allowlist"}
    forbidden_names = {"command_runner", "allowlist", "AllowlistValidator", "run_command"}

    imported_modules: set[str] = set()
    imported_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module)
            for alias in node.names:
                imported_names.add(alias.name)

    assert not (forbidden & imported_modules), (
        f"local_llm.py must not import {forbidden & imported_modules}"
    )
    assert not (forbidden_modules & imported_modules), (
        f"local_llm.py must not import from {forbidden_modules & imported_modules}"
    )
    assert not (forbidden_names & imported_names), (
        f"local_llm.py must not import names {forbidden_names & imported_names}"
    )
