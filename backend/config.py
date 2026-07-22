from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Canonical .env location: alongside this file, i.e. backend/.env.
# Using an absolute path here means the service reads the SAME .env
# regardless of the CWD it was launched from (systemd, uvicorn from repo
# root, pytest from anywhere). Historically this was ".env" (relative),
# which silently disagreed with deployment/raspberry-pi/install.sh — that
# script created .env at the repo root while the service kept reading a
# non-existent backend/.env, resulting in placeholder secrets slipping
# through and auth failing in surprising ways.
_ENV_FILE = Path(__file__).resolve().parent / ".env"

# The repo root — parent of the backend/ folder that houses this module.
# Path-typed settings whose defaults start with "backend/" or "logs/"
# assume they're resolved relative to this location, NOT relative to
# whatever CWD systemd (or uvicorn, or pytest) happens to launch under.
# The `_resolve_repo_relative` validator below enforces that.
#
# History: this used to be broken. `database_path` defaulted to
# "backend/data/rasapi.db", systemd set WorkingDirectory=backend/, so the
# path silently doubled to backend/backend/data/rasapi.db. Meanwhile every
# operator tool assumed backend/data/. check-readiness.sh even had a
# "no accidental backend/backend nesting" check — a symptom, not a fix.
# Anchoring to _REPO_ROOT here is the fix.
_REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @field_validator(
        "database_path",
        "voice_audio_temp_dir",
        "audit_log_dir",
        mode="after",
    )
    @classmethod
    def _resolve_repo_relative(cls, v: str) -> str:
        """Anchor filesystem-path settings to the repo root when they're
        relative. Absolute paths (as set in tests via monkeypatch, or by
        operators who pin data elsewhere) pass through unchanged."""
        if not v:
            return v
        p = Path(v)
        if p.is_absolute():
            return str(p)
        return str(_REPO_ROOT / p)

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # ── Local LLM (Phase 2) ───────────────────────────────────────────────
    # Off by default. Set ENABLE_LOCAL_LLM=true in .env to opt in.
    enable_local_llm: bool = False
    local_llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    local_llm_model: str = "llama3.2:1b"
    local_llm_timeout_seconds: int = 20

    # ── Daily Briefing (Phase 4) ──────────────────────────────────────────
    enable_briefing: bool = True
    enable_llm_briefing_summary: bool = False
    briefing_max_items_per_category: int = 5
    briefing_default_location: str = "Boston, MA"
    briefing_weather_lat: float = 42.3601
    briefing_weather_lon: float = -71.0589
    briefing_fetch_timeout_seconds: int = 10
    briefing_cache_minutes: int = 60

    # ── Dashboard (Phase 5) ───────────────────────────────────────────────
    # When true, the dashboard renders only the last two segments of the
    # configured database path so the absolute filesystem location is hidden.
    dashboard_mask_db_path: bool = True

    # ── Voice I/O (Phase 7) ──────────────────────────────────────────────
    # Voice is OFF by default. The deterministic intent router is still the
    # only thing that decides what runs — voice is a thin record/STT/TTS
    # layer that hands transcripts to the same orchestration.process_query
    # path that /ask uses.
    enable_voice: bool = False
    voice_recorder_engine: str = "mock"  # mock | arecord | sounddevice
    voice_stt_engine: str = "mock"       # mock | whisper
    voice_tts_engine: str = "mock"       # mock | piper | espeak
    voice_record_seconds: int = 5
    voice_audio_temp_dir: str = "backend/data/audio_tmp"
    voice_save_audio: bool = False
    voice_log_transcripts: bool = True
    voice_max_transcript_chars: int = 1000
    voice_require_push_to_talk: bool = True
    voice_device_input: str = ""
    voice_device_output: str = ""
    # Phase 10 polish: explicit model paths instead of symlinks + wrappers.
    # All optional at config-load time; the relevant engine checks them
    # at runtime and raises a clear EngineNotAvailable with setup advice
    # if the file is missing.
    voice_whisper_model_path: str = ""
    voice_piper_model_path: str = ""
    voice_piper_config_path: str = ""
    # auto | paplay | aplay. Picks the playback binary for Piper output.
    # `auto` prefers paplay (PipeWire / PulseAudio routes Bluetooth output
    # correctly) and falls back to aplay if paplay isn't installed.
    voice_tts_playback_command: str = "auto"

    # ── Authentication (Phase 8) ──────────────────────────────────────────
    # Auth is OFF by default to preserve the current local-dev workflow.
    # When ENABLE_AUTH=true, the four AUTH_PROTECT_* flags decide which
    # surfaces require credentials. /health and /commands stay public always.
    # API_SECRET_KEY is the single shared secret used for both API-key
    # header auth and dashboard login session signing.
    enable_auth: bool = False
    auth_protect_dashboard: bool = True
    auth_protect_ask: bool = True
    auth_protect_voice: bool = True
    auth_protect_mutations: bool = True
    auth_protect_integrations: bool = True
    session_cookie_name: str = "rasapi_session"
    session_ttl_minutes: int = 720
    cookie_secure: bool = False
    csrf_cookie_name: str = "rasapi_csrf"

    # ── Integrations (Phase 9) ────────────────────────────────────────────
    # Slack incoming webhook (no bot OAuth in Phase 9).
    enable_slack: bool = False
    slack_webhook_url: str = ""
    slack_default_channel: str = ""
    slack_send_briefing_enabled: bool = False
    slack_send_audit_alerts_enabled: bool = False

    # Home Assistant REST API + long-lived access token.
    enable_home_assistant: bool = False
    home_assistant_url: str = ""
    home_assistant_token: str = ""
    home_assistant_allowed_entities: str = ""    # comma-separated
    home_assistant_allowed_domains: str = "light,switch,sensor"
    home_assistant_require_confirmation: bool = True

    # ── Phase 11: Interaction layer + reliability ─────────────────────────
    # voice_max_spoken_chars caps any TTS payload to avoid long sessions /
    # timeouts. voice_briefing_items_per_category trims daily-briefing voice
    # output to N items per category. Both apply only in the voice path —
    # /ask, /dashboard, and /briefing/refresh still return the full briefing.
    voice_max_spoken_chars: int = 1200
    voice_briefing_items_per_category: int = 1
    # Retention windows used by deployment/raspberry-pi/run-log-cleanup.sh
    # and run-backup.sh. Cleanup is opt-in (operator runs the script via
    # cron or systemd-timer); the backend never auto-deletes.
    log_retention_days: int = 30
    audio_tmp_retention_hours: int = 24
    backup_retention_days: int = 14
    # Health watchdog disk-usage alert threshold (percent). The watchdog
    # script reads this only via env passed by the operator — the backend
    # surfaces the value via /config/status for visibility.
    watchdog_disk_threshold_pct: int = 90
    watchdog_slack_on_alert: bool = False

    # ── Phase 12: Data expansion layer ────────────────────────────────────
    # Read-only cache-backed public data sources. See backend/data_sources/.
    # Each source gates on its own config; these are the shared framework
    # knobs (cache, timeout, refresh loop).
    data_cache_enabled: bool = True
    data_stale_fallback: bool = True
    data_memory_cache_max_entries: int = 500
    data_fetch_timeout_seconds: int = 10
    data_background_refresh_enabled: bool = True

    api_secret_key: str = "change-me-before-use"

    database_path: str = "backend/data/rasapi.db"

    audit_log_dir: str = "logs"
    log_level: str = "INFO"

    assistant_name: str = "RasaPi"


settings = Settings()
