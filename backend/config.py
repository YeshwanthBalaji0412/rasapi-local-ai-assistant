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

    api_secret_key: str = "change-me-before-use"

    database_path: str = "backend/data/rasapi.db"

    audit_log_dir: str = "logs"
    log_level: str = "INFO"

    assistant_name: str = "RasaPi"


settings = Settings()
