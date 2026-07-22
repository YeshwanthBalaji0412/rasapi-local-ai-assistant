"""
Regression tests for the .env resolution bug that shipped through Phase 11.

Symptom on real hardware:
  - The operator ran deployment/raspberry-pi/install.sh which created .env at
    the repo root (~/rasapi-local-ai-assistant/.env).
  - The systemd service ran with WorkingDirectory=backend/ and pydantic-settings
    loaded env_file=".env" relative to that CWD, which resolved to
    backend/.env — a file the installer never touched.
  - Result: the running service loaded whatever stale defaults happened to be
    in backend/.env (or none, falling back to config.py defaults). API-key auth
    silently failed against the value the operator thought they'd configured.

Fix (backend/config.py): resolve env_file to an ABSOLUTE path anchored on
config.py's own directory. That's canonically backend/.env regardless of the
CWD the service was launched from (systemd, uvicorn from the repo root, pytest,
whatever). These tests lock that invariant in place.
"""

from __future__ import annotations

from pathlib import Path

from config import Settings


def test_env_file_is_absolute_path():
    """env_file must not be a bare '.env' — that's how the CWD bug shipped."""
    env_file = Settings.model_config.get("env_file")
    assert env_file is not None, "env_file must be set on Settings.model_config"
    resolved = Path(env_file)
    assert resolved.is_absolute(), (
        f"env_file must be absolute so the service reads the same .env "
        f"regardless of CWD. Got: {env_file!r}"
    )


def test_env_file_points_at_backend_directory():
    """The canonical .env lives in backend/ (alongside config.py itself)."""
    env_file = Path(Settings.model_config["env_file"])
    config_dir = Path(__file__).resolve().parent.parent / "backend"
    assert env_file.parent == config_dir, (
        f"env_file must resolve to backend/.env, got parent {env_file.parent!r} "
        f"(expected {config_dir!r})"
    )
    assert env_file.name == ".env"


def test_env_file_model_config_uses_settings_config_dict():
    """Sanity check: model_config is the pydantic-settings SettingsConfigDict,
    not a plain dict that lost its type when someone edited it."""
    assert isinstance(Settings.model_config, dict)
    # SettingsConfigDict is a TypedDict subclass — a plain dict passes isinstance
    # against dict, so also check the well-known keys are present.
    for key in ("env_file", "env_file_encoding", "case_sensitive"):
        assert key in Settings.model_config, f"missing model_config key: {key}"


# ── Path-typed settings must resolve to the repo root, NOT the CWD ─────
#
# The same class of bug that produced backend/.env-vs-repo-root/.env also
# produced backend/backend/data/rasapi.db (systemd CWD=backend/, and the
# default database_path was the relative string "backend/data/rasapi.db",
# so pydantic-settings didn't rewrite it and Python resolved it against
# CWD, doubling the "backend/" prefix). The field_validator in config.py
# now anchors these paths to the repo root. Lock the invariant here.


def test_database_path_default_resolves_under_repo_root():
    """A fresh Settings() with the shipped default should resolve
    database_path to <repo>/backend/data/rasapi.db — never
    <repo>/backend/backend/data/rasapi.db."""
    repo_root = Path(__file__).resolve().parent.parent
    settings = Settings()
    db_path = Path(settings.database_path)
    assert db_path.is_absolute(), (
        f"database_path must resolve to an absolute path, got: {db_path!r}"
    )
    assert db_path == repo_root / "backend" / "data" / "rasapi.db", (
        f"database_path resolved to {db_path!r}; "
        f"expected {repo_root / 'backend' / 'data' / 'rasapi.db'!r}. "
        f"If you see backend/backend/data/... the CWD-nesting bug is back."
    )


def test_audit_log_dir_default_resolves_under_repo_root():
    repo_root = Path(__file__).resolve().parent.parent
    settings = Settings()
    audit_dir = Path(settings.audit_log_dir)
    assert audit_dir.is_absolute()
    assert audit_dir == repo_root / "logs"


def test_voice_audio_temp_dir_default_resolves_under_repo_root():
    repo_root = Path(__file__).resolve().parent.parent
    settings = Settings()
    audio_dir = Path(settings.voice_audio_temp_dir)
    assert audio_dir.is_absolute()
    assert audio_dir == repo_root / "backend" / "data" / "audio_tmp"


def test_absolute_path_settings_pass_through_unchanged():
    """Operators who pin a path to somewhere outside the repo (SD card mount,
    tmpfs, etc.) must not have it silently rewritten. Absolute paths bypass
    the validator's anchoring."""
    import os

    external = os.path.abspath("/var/lib/rasapi/rasapi.db")
    s = Settings(database_path=external)
    assert s.database_path == external
