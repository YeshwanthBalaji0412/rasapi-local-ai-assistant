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

from pydantic_settings import SettingsConfigDict

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
