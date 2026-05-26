"""Central settings, loaded once from environment / .env.

Every module imports `settings` from here instead of reading os.environ directly,
so there is a single, typed source of truth for configuration.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    mock_llm: bool = True

    # Pipeline
    pipeline_rate_limit_per_min: int = 10
    pipeline_poll_seconds: int = 5

    # Database
    database_url: str = "sqlite:///data/smartsupport.db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
