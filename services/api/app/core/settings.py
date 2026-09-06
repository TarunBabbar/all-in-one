"""Application settings loaded from env with pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "QA/One API"

    # LLM provider: mock | cmdc | commandcode
    #   mock        — deterministic offline (tests/CI, no keys)
    #   cmdc        — local `cmdc -p ... --yolo` headless CLI (authenticated
    #                 session; DeepSeek V4 Flash Fast by default)
    #   commandcode — Command Code Provider REST API (Bearer key in .env)
    llm_provider: str = "mock"
    cmdc_bin: str = "cmdc"
    cmd_api_key: str = ""
    cmd_model: str = "deepseek/deepseek-v4-flash-fast"
    cmd_api_base: str = "https://api.commandcode.ai/provider/v1"

    # Postgres (Neon in .env) or local. sqlite fallback keeps dev light.
    database_url: str = "sqlite+aiosqlite:///./data/qahub.db"

    runner_url: str = "http://localhost:8787"
    cors_origins: str = "http://localhost:3000"

    # --- Jira (REST, pattern from jira-qa-crew-next) ---
    jira_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_bearer_token: str = ""
    jira_auth_mode: str = "basic"  # basic | bearer
    jira_api_version: str = "3"
    jira_acceptance_criteria_field: str = ""
    jira_include_comments: bool = False
    jira_max_comments: int = 20
    jira_timeout_seconds: int = 30
    jira_key_pattern: str = r"^[A-Z][A-Z0-9_]+-\d+$"

    # --- GitHub (push/pull code via REST) ---
    github_token: str = ""
    github_repo: str = ""  # owner/repo
    github_branch: str = "master"
    github_api_base: str = "https://api.github.com"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
