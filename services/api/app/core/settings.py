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

    # URL of the Playwright runner worker (see .env RUNNER_URL).
    # NOTE: a real shell/OS environment variable named RUNNER_URL overrides the
    # .env file (pydantic-settings precedence). If you see runs dispatching to
    # an unexpected host, check for a global RUNNER_URL export and unset it.
    runner_url: str = "http://localhost:8787"
    cors_origins: str = "http://localhost:3000"
    # Base URL of the app under test — used as the default target by codegen,
    # the executor (run stage), and the pipeline input resolver.
    app_base_url: str = "http://localhost:3000"

    # --- Run limits -------------------------------------------------------
    # One heal attempt is a full Playwright run, so it gets its own generous
    # timeout rather than sharing one timer across the whole loop.
    # What the API waits for a single runner /run call (seconds).
    runner_call_timeout_s: float = 420.0
    # What the API waits for a single runner /inspect call (seconds).
    inspect_timeout_s: float = 90.0
    # How many times the executor may heal + rerun a failing suite.
    max_heal_attempts: int = 5
    # Hard ceiling for one run stage so a loop cannot spin forever (seconds).
    stage_budget_s: float = 1800.0

    # --- Test case generation --------------------------------------------
    # Cases are coverage-driven (one per criterion per category), not a fixed
    # number. This is a safety cap so a verbose requirement cannot produce an
    # unbounded suite; raise it freely.
    max_test_cases: int = 120

    # --- DeepEval ---------------------------------------------------------
    # Metrics are fully deterministic (no LLM judge), so the eval gates run
    # offline. Set DEEPEVAL_TELEMETRY_OPT_OUT=1 to keep results local.
    deepeval_enabled: bool = True

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
