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

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"

    api_secret_key: str = "change-me-before-use"

    audit_log_dir: str = "logs"
    log_level: str = "INFO"

    assistant_name: str = "RasaPi"


settings = Settings()
