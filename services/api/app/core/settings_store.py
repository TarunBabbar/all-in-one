"""Settings store — resolve connector config between DB (runtime) and .env.

Read path: DB row wins if present, else the env-backed Settings value.
Write path: PUT /settings persists to the app_settings table so the UI can
store connector details without editing .env. Secrets are masked on read.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.settings import get_settings
from ..db.models import AppSettingRow

# (db_key, env_attr, secret) — secret=True masks the value on read.
SETTING_KEYS: dict[str, dict] = {
    # --- Jira ---
    "jira.url": {"env": "jira_url", "secret": False},
    "jira.email": {"env": "jira_email", "secret": False},
    "jira.api_token": {"env": "jira_api_token", "secret": True},
    "jira.bearer_token": {"env": "jira_bearer_token", "secret": True},
    "jira.auth_mode": {"env": "jira_auth_mode", "secret": False},
    "jira.api_version": {"env": "jira_api_version", "secret": False},
    "jira.acceptance_criteria_field": {"env": "jira_acceptance_criteria_field", "secret": False},
    # --- GitHub ---
    "github.token": {"env": "github_token", "secret": True},
    "github.repo": {"env": "github_repo", "secret": False},
    "github.branch": {"env": "github_branch", "secret": False},
}

MASK = "********"


def _masked(value: str) -> str:
    if not value:
        return ""
    return MASK


class SettingsStore:
    async def _rows(self, session: AsyncSession) -> dict[str, str]:
        rows = (await session.execute(select(AppSettingRow))).scalars().all()
        return {r.key: r.value for r in rows}

    async def all(self, session: AsyncSession, masked: bool = True) -> dict:
        """Effective config (DB > env) grouped, secrets masked unless masked=False."""
        rows = await self._rows(session)
        env = get_settings()
        out: dict[str, dict] = {"jira": {}, "github": {}}
        for key, meta in SETTING_KEYS.items():
            group, _, name = key.partition(".")
            raw = rows.get(key) or getattr(env, meta["env"], "")
            out.setdefault(group, {})[name] = _masked(raw) if (masked and meta["secret"] and raw) else raw
        return out

    async def put(self, session: AsyncSession, values: dict) -> None:
        """Persist incoming {jira: {...}, github: {...}} over DB rows.

        Secret fields sent as the MASK value are treated as 'unchanged' and
        left as-is.
        """
        rows = await self._rows(session)
        for group, fields in values.items():
            if not isinstance(fields, dict):
                continue
            for name, value in fields.items():
                key = f"{group}.{name}"
                meta = SETTING_KEYS.get(key)
                if meta is None:
                    continue
                value = (value or "").strip() if isinstance(value, str) else str(value or "")
                if meta["secret"] and value == MASK:
                    continue  # keep existing
                row = rows.get(key)
                if row is not None:
                    existing = await session.get(AppSettingRow, key)
                    existing.value = value
                else:
                    session.add(AppSettingRow(key=key, value=value))
        await session.commit()

    def connector_config(self, settings_values: dict, group: str) -> dict:
        """Build a connector config dict from settings group values."""
        return settings_values.get(group, {})

    async def jira_config(self, session: AsyncSession) -> dict:
        return await self._group(session, "jira")

    async def github_config(self, session: AsyncSession) -> dict:
        return await self._group(session, "github")

    async def _group(self, session: AsyncSession, group: str) -> dict:
        vals = await self.all(session, masked=False)
        return vals.get(group, {})
