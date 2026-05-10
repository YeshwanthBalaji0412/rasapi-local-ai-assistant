"""Phase 10 — verify the four new operator scripts exist, are executable,
have a bash shebang, and follow the safety rules:

  - no bare `sudo apt install` execution (string mentions allowed)
  - no `rm -rf` of operator data without explicit operator action
  - no printing of secrets
"""

import os
import re
import stat
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY_DIR = REPO_ROOT / "deployment" / "raspberry-pi"


PHASE_10_SCRIPTS = [
    "check-readiness.sh",
    "health-check.sh",
    "update-rasapi.sh",
    "doctor.sh",
]


@pytest.mark.parametrize("script_name", PHASE_10_SCRIPTS)
def test_script_exists(script_name):
    assert (DEPLOY_DIR / script_name).is_file()


@pytest.mark.parametrize("script_name", PHASE_10_SCRIPTS)
def test_script_has_bash_shebang(script_name):
    first_line = (DEPLOY_DIR / script_name).read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("#!") and "bash" in first_line


@pytest.mark.parametrize("script_name", PHASE_10_SCRIPTS)
def test_script_is_executable(script_name):
    mode = (DEPLOY_DIR / script_name).stat().st_mode
    assert mode & stat.S_IXUSR, f"{script_name} missing user-execute bit"


@pytest.mark.parametrize("script_name", PHASE_10_SCRIPTS)
def test_script_does_not_run_sudo_apt_install(script_name):
    """Operator scripts must instruct, never execute, package install."""
    body = (DEPLOY_DIR / script_name).read_text(encoding="utf-8")
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Allow inside quoted strings, echo/printf statements, assignments.
        if stripped.startswith(("echo ", "printf ", "abort ", '"', "'")):
            continue
        if "=" in stripped.split(None, 1)[0] if stripped.split() else False:
            continue
        assert not re.match(r"^sudo\s+apt(-get)?\s+install", stripped), (
            f"{script_name}: line executes apt install: {line}"
        )


@pytest.mark.parametrize("script_name", PHASE_10_SCRIPTS)
def test_script_does_not_delete_data_directories(script_name):
    """No rm -rf of backend/data, logs, .env. These are operator-managed."""
    body = (DEPLOY_DIR / script_name).read_text(encoding="utf-8")
    forbidden_patterns = [
        r"rm\s+-rf?\s+.*backend/data",
        r"rm\s+-rf?\s+.*\.env\b",
        r"rm\s+-rf?\s+.*logs\b",
    ]
    for pat in forbidden_patterns:
        assert not re.search(pat, body), (
            f"{script_name} contains a rm pattern matching {pat!r}"
        )


# ─── content-specific checks ────────────────────────────────────────────────


def test_check_readiness_uses_base_url_and_api_key():
    body = (DEPLOY_DIR / "check-readiness.sh").read_text(encoding="utf-8")
    assert "BASE_URL" in body
    assert "RASA_API_KEY" in body
    assert "/health" in body
    assert "/readiness" in body
    assert "/config/status" in body


def test_health_check_is_lightweight():
    body = (DEPLOY_DIR / "health-check.sh").read_text(encoding="utf-8")
    assert "/health" in body
    # Should not depend on auth — /health is always public.
    assert "RASA_API_KEY" not in body or "optional" in body.lower()


def test_update_rasapi_refuses_uncommitted_changes():
    body = (DEPLOY_DIR / "update-rasapi.sh").read_text(encoding="utf-8")
    assert "git diff" in body
    # Refuses to run with uncommitted changes
    assert "uncommitted" in body.lower() or "abort" in body.lower()


def test_doctor_never_prints_env_contents():
    """doctor.sh must show .env presence + mode + key count, but never the
    actual content."""
    body = (DEPLOY_DIR / "doctor.sh").read_text(encoding="utf-8")
    # We do not cat or grep -v out the .env contents into stdout.
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # cat "$REPO_ROOT/.env" would be a leak.
        assert not re.search(r"\bcat\s+.*\.env\b", stripped), (
            f"doctor.sh appears to cat .env: {line}"
        )
        # head/tail of .env would also be a leak.
        assert not re.search(r"\b(head|tail)\s+.*\.env\b", stripped), (
            f"doctor.sh appears to head/tail .env: {line}"
        )
