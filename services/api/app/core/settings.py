"""Application settings loaded from env with pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "QA/One API"
    database_url: str = "sqlite+aiosqlite:///./data/qahub.db"
    llm_provider: str = "mock"  # mock | anthropic | openai | groq | gemini | openrouter
    runner_url: str = "http://localhost:8787"
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
