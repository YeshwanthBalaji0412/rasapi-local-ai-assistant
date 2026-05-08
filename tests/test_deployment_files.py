"""
Phase 6 — Raspberry Pi deployment file checks.

These tests are pure file/content/permission assertions. They run offline,
touch no HTTP, and never execute the deployment scripts. They guard the
shape and safety of the deployment artifacts.
"""

import os
import re
import stat
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY_DIR = REPO_ROOT / "deployment" / "raspberry-pi"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _has_bash_shebang(path: Path) -> bool:
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    return first_line.startswith("#!") and "bash" in first_line


# ─── existence ───────────────────────────────────────────────────────────────


def test_setup_pi_md_exists():
    assert (DEPLOY_DIR / "setup-pi.md").is_file()


def test_install_sh_exists_with_bash_shebang():
    p = DEPLOY_DIR / "install.sh"
    assert p.is_file()
    assert _has_bash_shebang(p)


def test_install_sh_is_executable():
    mode = (DEPLOY_DIR / "install.sh").stat().st_mode
    assert mode & stat.S_IXUSR, "install.sh should have the user-execute bit set"


def test_smoke_test_sh_exists_with_bash_shebang():
    p = DEPLOY_DIR / "smoke-test.sh"
    assert p.is_file()
    assert _has_bash_shebang(p)


def test_backup_sh_exists_with_bash_shebang():
    p = DEPLOY_DIR / "backup.sh"
    assert p.is_file()
    assert _has_bash_shebang(p)


def test_restore_sh_exists_with_bash_shebang():
    p = DEPLOY_DIR / "restore.sh"
    assert p.is_file()
    assert _has_bash_shebang(p)


def test_rasapi_service_exists():
    assert (DEPLOY_DIR / "rasapi.service").is_file()


def test_env_example_pi_exists():
    assert (DEPLOY_DIR / "env.example.pi").is_file()


def test_troubleshooting_md_exists():
    assert (DEPLOY_DIR / "troubleshooting.md").is_file()


def test_top_level_deployment_doc_exists():
    assert (REPO_ROOT / "docs" / "deployment.md").is_file()


# ─── systemd unit content ────────────────────────────────────────────────────


def test_rasapi_service_does_not_run_as_root():
    body = _read(DEPLOY_DIR / "rasapi.service")
    # Permit a comment that says "do not run as root"; reject an actual setting.
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "User=root" not in stripped, (
            "rasapi.service must not contain User=root; found in: " + line
        )


def test_rasapi_service_uses_placeholder_user():
    body = _read(DEPLOY_DIR / "rasapi.service")
    assert "<PI_USER>" in body, (
        "rasapi.service should ship with a <PI_USER> placeholder, "
        "not a hardcoded username"
    )


def test_rasapi_service_has_restart_on_failure():
    body = _read(DEPLOY_DIR / "rasapi.service")
    assert re.search(r"^\s*Restart\s*=\s*on-failure\s*$", body, flags=re.MULTILINE), (
        "rasapi.service must contain Restart=on-failure"
    )


def test_rasapi_service_uses_uvicorn_main_app():
    body = _read(DEPLOY_DIR / "rasapi.service")
    assert "uvicorn" in body and "main:app" in body


def test_rasapi_service_default_binds_to_localhost():
    body = _read(DEPLOY_DIR / "rasapi.service")
    # The active (uncommented) ExecStart line should contain 127.0.0.1.
    active_exec_lines = [
        line for line in body.splitlines()
        if line.strip().startswith("ExecStart=") and not line.strip().startswith("#")
    ]
    assert active_exec_lines, "expected at least one ExecStart line"
    assert all("127.0.0.1" in line for line in active_exec_lines), (
        "default ExecStart should bind to 127.0.0.1; LAN binding lives in a comment"
    )


# ─── env.example.pi content ──────────────────────────────────────────────────


def test_env_example_pi_has_no_real_credentials():
    body = _read(DEPLOY_DIR / "env.example.pi")
    # Reject things that look like real keys.
    bad_patterns = [
        r"sk-[A-Za-z0-9]{20,}",       # OpenAI-style
        r"ghp_[A-Za-z0-9]{20,}",      # GitHub PAT
        r"AKIA[0-9A-Z]{16}",          # AWS access key id
        r"Bearer\s+[A-Za-z0-9_\-\.]+",
        r"xoxb-[A-Za-z0-9-]{20,}",    # Slack
    ]
    for pat in bad_patterns:
        assert re.search(pat, body) is None, f"env.example.pi looks like it leaks a real secret matching {pat!r}"


def test_env_example_pi_starts_with_local_llm_disabled():
    body = _read(DEPLOY_DIR / "env.example.pi")
    assert re.search(r"^\s*ENABLE_LOCAL_LLM\s*=\s*false\s*$", body, flags=re.MULTILINE)


# ─── setup-pi.md content ─────────────────────────────────────────────────────


def test_setup_pi_warns_against_public_exposure():
    body = _read(DEPLOY_DIR / "setup-pi.md")
    assert "public internet" in body.lower() or "do not port-forward" in body.lower()


def test_setup_pi_mentions_chmod_600_env():
    body = _read(DEPLOY_DIR / "setup-pi.md")
    assert "chmod 600 .env" in body


def test_setup_pi_mentions_chmod_700_for_data_and_logs():
    body = _read(DEPLOY_DIR / "setup-pi.md")
    assert "700" in body and "backend/data" in body and "logs" in body


# ─── docs/deployment.md links to the Pi guide ────────────────────────────────


def test_deployment_doc_links_to_pi_setup():
    body = _read(REPO_ROOT / "docs" / "deployment.md")
    assert "raspberry-pi/setup-pi.md" in body


# ─── smoke-test.sh content ───────────────────────────────────────────────────


def test_smoke_test_uses_base_url_var():
    body = _read(DEPLOY_DIR / "smoke-test.sh")
    assert "BASE_URL" in body
    assert "BASE_URL:-http://127.0.0.1:8000" in body


def test_smoke_test_hits_health_endpoint():
    body = _read(DEPLOY_DIR / "smoke-test.sh")
    assert "/health" in body


def test_smoke_test_hits_ask_endpoint_with_memory_query():
    body = _read(DEPLOY_DIR / "smoke-test.sh")
    assert "/ask" in body
    # The test plan says smoke includes a "remember that ..." memory request.
    assert "remember that my project is RasaPi" in body


# ─── install.sh safety ───────────────────────────────────────────────────────


def test_install_sh_does_not_execute_apt_install():
    """install.sh must instruct the user, never run sudo apt install itself."""
    body = _read(DEPLOY_DIR / "install.sh")
    # A bare invocation would appear at the start of a non-comment line.
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Permit string assignment / echo / printf usage.
        if stripped.startswith(('echo ', 'printf ', 'APT_HINT=', '"', "'")):
            continue
        assert not re.match(r"^sudo\s+apt(-get)?\s+install", stripped), (
            f"install.sh should not execute apt install; offending line: {line}"
        )


def test_install_sh_creates_data_and_logs_dirs():
    body = _read(DEPLOY_DIR / "install.sh")
    # The script may use shell variables for the paths.
    assert "DATA_DIR" in body or "backend/data" in body
    assert "LOGS_DIR" in body or "/logs" in body
    assert "mkdir" in body


def test_install_sh_does_not_overwrite_existing_env():
    body = _read(DEPLOY_DIR / "install.sh")
    # Look for a check that .env exists before copying.
    assert re.search(r"\[\s+-f\s+\"\$ENV_FILE\"\s+\]", body) or "already exists" in body


# ─── backup.sh excludes .env ─────────────────────────────────────────────────


def test_backup_script_does_not_copy_env_file():
    body = _read(DEPLOY_DIR / "backup.sh")
    # The script must not contain a copy/include of .env.
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith(('echo ', 'printf ')):
            continue
        # Reject any line that copies/moves/tars .env.
        if re.search(r"\.env\b", stripped) and any(
            cmd in stripped for cmd in ("cp ", "mv ", "tar", "rsync")
        ):
            pytest.fail(f"backup.sh appears to include .env: {stripped}")


def test_backup_script_documents_env_exclusion():
    body = _read(DEPLOY_DIR / "backup.sh")
    # Must explicitly mention that .env is intentionally excluded.
    assert ".env" in body and (
        "intentionally not" in body.lower() or "not included" in body.lower() or "excluded" in body.lower()
    )


# ─── restore.sh ──────────────────────────────────────────────────────────────


def test_restore_requires_backup_path_argument():
    body = _read(DEPLOY_DIR / "restore.sh")
    assert re.search(r"\$#\s*-ne\s*1", body) or "Usage:" in body


def test_restore_does_not_overwrite_env():
    body = _read(DEPLOY_DIR / "restore.sh")
    # Same structural rule as backup: no copy of .env.
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith(('echo ', 'printf ')):
            continue
        if re.search(r"\.env\b", stripped) and any(
            cmd in stripped for cmd in ("cp ", "mv ", "tar", "rsync")
        ):
            pytest.fail(f"restore.sh appears to overwrite .env: {stripped}")
