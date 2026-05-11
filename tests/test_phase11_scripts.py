"""Phase 11 — scheduler / watchdog / cleanup script tests.

These tests are environment-agnostic. They verify:
  - file existence and the bash shebang
  - executable bit
  - `set -euo pipefail` (strict mode)
  - presence of --dry-run support where promised
  - no hard-coded secrets in the source
  - the watchdog never prints `$RASA_API_KEY` or `$SLACK_WEBHOOK_URL`
  - log-cleanup uses hardcoded relative paths, not env-driven absolute ones
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY_DIR = REPO_ROOT / "deployment" / "raspberry-pi"


PHASE_11_SCRIPTS = [
    "run-daily-briefing.sh",
    "run-backup.sh",
    "run-health-watchdog.sh",
    "run-log-cleanup.sh",
]

DRY_RUN_SCRIPTS = [
    "run-backup.sh",
    "run-log-cleanup.sh",
]


SYSTEMD_FILES = [
    "rasapi-watchdog.timer",
    "rasapi-watchdog.service",
    "rasapi-briefing.timer",
    "rasapi-briefing.service",
]


# ─── existence + permissions ─────────────────────────────────────────────────


@pytest.mark.parametrize("name", PHASE_11_SCRIPTS)
def test_script_exists(name):
    assert (DEPLOY_DIR / name).is_file()


@pytest.mark.parametrize("name", PHASE_11_SCRIPTS)
def test_script_is_executable(name):
    mode = (DEPLOY_DIR / name).stat().st_mode
    assert mode & stat.S_IXUSR, f"{name} missing user-execute bit"


@pytest.mark.parametrize("name", PHASE_11_SCRIPTS)
def test_script_bash_shebang(name):
    line = (DEPLOY_DIR / name).read_text(encoding="utf-8").splitlines()[0]
    assert line.startswith("#!") and "bash" in line


@pytest.mark.parametrize("name", PHASE_11_SCRIPTS)
def test_script_uses_strict_mode(name):
    body = (DEPLOY_DIR / name).read_text(encoding="utf-8")
    assert "set -euo pipefail" in body, f"{name} missing strict-mode line"


@pytest.mark.parametrize("name", PHASE_11_SCRIPTS)
def test_script_syntax_valid(name):
    """bash -n parses the script without executing it."""
    result = subprocess.run(
        ["bash", "-n", str(DEPLOY_DIR / name)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# ─── dry-run support ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", DRY_RUN_SCRIPTS)
def test_dry_run_flag_supported(name):
    body = (DEPLOY_DIR / name).read_text(encoding="utf-8")
    assert "--dry-run" in body
    assert "DRY_RUN" in body


def test_log_cleanup_dry_run_runs_clean(tmp_path):
    """--dry-run completes successfully and prints nothing destructive."""
    env = os.environ.copy()
    result = subprocess.run(
        ["bash", str(DEPLOY_DIR / "run-log-cleanup.sh"), "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    # No real deletions surfaced.
    assert "Removed log:" not in result.stdout
    assert "Removed audio:" not in result.stdout


def test_backup_dry_run_runs_clean(tmp_path):
    env = os.environ.copy()
    env["BACKUP_ROOT"] = str(tmp_path / "rasapi-backups")
    result = subprocess.run(
        ["bash", str(DEPLOY_DIR / "run-backup.sh"), "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "DRY-RUN" in result.stdout
    # No real backup snapshot under the temp root.
    assert not (tmp_path / "rasapi-backups").exists()


# ─── safety properties ──────────────────────────────────────────────────────


@pytest.mark.parametrize("name", PHASE_11_SCRIPTS)
def test_script_does_not_embed_api_key_or_webhook(name):
    """No literal secret value in the script."""
    body = (DEPLOY_DIR / name).read_text(encoding="utf-8")
    # No literal Slack webhook URLs.
    assert "hooks.slack.com/services/T" not in body
    # No long-lived HA tokens (rough heuristic: 'eyJ' + 50+ chars).
    assert "eyJhbGciOi" not in body


def test_log_cleanup_uses_hardcoded_paths():
    """run-log-cleanup.sh must derive LOGS_DIR and AUDIO_DIR from REPO_ROOT,
    not from arbitrary env vars. This prevents env-injection from
    redirecting deletion to /etc or /home."""
    body = (DEPLOY_DIR / "run-log-cleanup.sh").read_text(encoding="utf-8")
    assert 'LOGS_DIR="$REPO_ROOT/logs"' in body
    assert 'AUDIO_DIR="$REPO_ROOT/backend/data/audio_tmp"' in body
    # Crucially, those two are NOT taken from the env.
    assert "LOGS_DIR=${LOGS_DIR" not in body
    assert "AUDIO_DIR=${AUDIO_DIR" not in body


def test_log_cleanup_only_targets_audit_jsonl():
    """The find expression for logs must match audit-*.jsonl only,
    so an unrelated file in logs/ is never removed."""
    body = (DEPLOY_DIR / "run-log-cleanup.sh").read_text(encoding="utf-8")
    assert "-name 'audit-*.jsonl'" in body


def test_backup_refuses_empty_or_root_backup_root():
    body = (DEPLOY_DIR / "run-backup.sh").read_text(encoding="utf-8")
    assert 'BACKUP_ROOT" = "/"' in body
    assert "Refusing to rotate" in body


def test_watchdog_does_not_echo_webhook_url():
    """The watchdog must never print $webhook_url or $SLACK_WEBHOOK_URL."""
    body = (DEPLOY_DIR / "run-health-watchdog.sh").read_text(encoding="utf-8")
    # No echo/printf of those variables.
    for forbidden in (
        'echo "$webhook_url"',
        "echo $webhook_url",
        'printf "%s" "$webhook_url"',
        'echo "$SLACK_WEBHOOK_URL"',
        "echo $SLACK_WEBHOOK_URL",
    ):
        assert forbidden not in body
    # And the URL is unset after use.
    assert "unset webhook_url" in body


def test_watchdog_does_not_echo_api_key():
    body = (DEPLOY_DIR / "run-health-watchdog.sh").read_text(encoding="utf-8")
    # /health and /readiness are public — watchdog has no reason to touch a key.
    assert "RASA_API_KEY" not in body
    assert "X-RasaPi-Key" not in body


def test_briefing_script_does_not_echo_api_key():
    body = (DEPLOY_DIR / "run-daily-briefing.sh").read_text(encoding="utf-8")
    # The api_key variable is unset after use.
    assert "unset api_key" in body
    # And not printed.
    for forbidden in (
        'echo "$api_key"',
        "echo $api_key",
        'echo "$RASA_API_KEY"',
        "echo $RASA_API_KEY",
    ):
        assert forbidden not in body


def test_watchdog_does_not_restart_services():
    """Only check executable (non-comment) lines so the safety-claim
    comments at the top don't trip the test."""
    body = (DEPLOY_DIR / "run-health-watchdog.sh").read_text(encoding="utf-8")
    code_lines = [
        line for line in body.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    code = "\n".join(code_lines)
    for forbidden in (
        "systemctl restart",
        "systemctl stop",
        "reboot",
        "shutdown",
    ):
        assert forbidden not in code, f"watchdog has executable {forbidden!r}"


# ─── systemd unit files ──────────────────────────────────────────────────────


@pytest.mark.parametrize("name", SYSTEMD_FILES)
def test_systemd_unit_exists(name):
    assert (DEPLOY_DIR / name).is_file()


def test_watchdog_timer_uses_oncalendar_or_active_sec():
    body = (DEPLOY_DIR / "rasapi-watchdog.timer").read_text(encoding="utf-8")
    assert "OnUnitActiveSec=" in body or "OnCalendar=" in body
    assert "[Install]" in body


def test_briefing_timer_uses_oncalendar():
    body = (DEPLOY_DIR / "rasapi-briefing.timer").read_text(encoding="utf-8")
    assert "OnCalendar=" in body


def test_scheduler_doc_exists():
    assert (DEPLOY_DIR / "scheduler.md").is_file()
    body = (DEPLOY_DIR / "scheduler.md").read_text(encoding="utf-8")
    # Mentions both wiring options.
    assert "cron" in body.lower()
    assert "systemd" in body.lower()
