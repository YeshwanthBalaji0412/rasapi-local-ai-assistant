from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

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

    api_secret_key: str = "change-me-before-use"

    database_path: str = "backend/data/rasapi.db"

    audit_log_dir: str = "logs"
    log_level: str = "INFO"

    assistant_name: str = "RasaPi"


settings = Settings()
