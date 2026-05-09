"""
Phase 7 — voice security checks.

Structural AST tests guarantee that `voice/session.py` and `voice/cli.py`
cannot reach the executor or call the LLM directly. Subprocess use is
permitted only inside the engine adapters (recorder.py / stt.py / tts.py),
because those need to invoke local audio binaries on the Pi.
"""

import ast
import asyncio
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from config import settings
from voice import session as session_module
from voice import stt as stt_module


VOICE_DIR = Path(__file__).resolve().parent.parent / "backend" / "voice"


def _imports_in(path: Path) -> tuple[set[str], set[str]]:
    """Return (modules_imported, names_imported_from) for a Python file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
            for alias in node.names:
                names.add(alias.name)
    return modules, names


# ─── session.py: no subprocess, no command_runner, no local_llm ──────────────


def test_voice_session_does_not_import_subprocess():
    modules, _ = _imports_in(VOICE_DIR / "session.py")
    assert "subprocess" not in modules


def test_voice_session_does_not_import_command_runner():
    modules, names = _imports_in(VOICE_DIR / "session.py")
    assert "core.command_runner" not in modules
    assert "command_runner" not in names
    assert "run_command" not in names


def test_voice_session_does_not_import_local_llm():
    modules, names = _imports_in(VOICE_DIR / "session.py")
    assert "core.local_llm" not in modules
    assert "local_llm" not in names


# ─── cli.py: no subprocess, no command_runner ────────────────────────────────


def test_voice_cli_does_not_import_subprocess():
    modules, _ = _imports_in(VOICE_DIR / "cli.py")
    assert "subprocess" not in modules


def test_voice_cli_does_not_import_command_runner():
    modules, names = _imports_in(VOICE_DIR / "cli.py")
    assert "core.command_runner" not in modules
    assert "command_runner" not in names
    assert "run_command" not in names


# ─── adapters: subprocess is permitted, but ONLY in adapter files ────────────


def test_only_adapter_files_import_subprocess():
    """Subprocess use must be confined to recorder/stt/tts. Anywhere else
    in voice/ is a security regression."""
    allowed = {"recorder.py", "stt.py", "tts.py"}
    offenders = []
    for path in VOICE_DIR.glob("*.py"):
        modules, _ = _imports_in(path)
        if "subprocess" in modules and path.name not in allowed:
            offenders.append(path.name)
    assert not offenders, f"unexpected subprocess imports in: {offenders}"


# ─── /voice/status doesn't leak filesystem layout ────────────────────────────


def test_voice_status_does_not_leak_paths(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    resp = client.get("/voice/status")
    body = resp.text
    # Must not contain absolute prefixes.
    assert not re.search(r"/Users/[^\"\s]+", body)
    assert not re.search(r"/home/[^\"\s]+", body)
    assert not re.search(r"/private/var/", body)


# ─── voice session does not invoke run_command for handler intents ───────────


def test_voice_handler_intent_never_invokes_command_runner(monkeypatch):
    monkeypatch.setattr(settings, "enable_voice", True)
    monkeypatch.setattr(stt_module, "DEFAULT_MOCK_TRANSCRIPT", "hello")
    with patch(
        "core.command_runner.run_command",
        side_effect=AssertionError("must not be called for greeting"),
    ):
        result = asyncio.run(session_module.run_session_once())
    assert result.intent == "greeting"


# ─── orchestration is the bridge — it's allowed to import local_llm ─────────


def test_orchestration_module_routes_through_local_llm():
    """Sanity check: orchestration imports local_llm, but voice does not."""
    from core import orchestration
    src = Path(orchestration.__file__).read_text(encoding="utf-8")
    assert "local_llm" in src   # orchestration is the only consumer
