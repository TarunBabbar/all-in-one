"""Jira REST connector.

Faithful port of the pattern from jira-qa-crew-next/lib/jira.ts: fetch an
issue via REST API v3 with Basic auth (email + API token), normalize ADF
description to plain text, health-check via /myself. HTTPX-based.
"""

from __future__ import annotations

import base64

import httpx


class JiraError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class JiraConnector:
    def __init__(self, config: dict) -> None:
        self.url = (config.get("url") or "").rstrip("/")
        self.email = config.get("email") or ""
        self.api_token = config.get("api_token") or ""
        self.bearer_token = config.get("bearer_token") or ""
        self.auth_mode = config.get("auth_mode") or "basic"
        self.api_version = str(config.get("api_version") or "3")
        self.timeout = float(config.get("timeout_seconds") or 30)

    # ---- auth ----

    def _headers(self) -> dict[str, str]:
        if self.auth_mode == "bearer":
            return {
                "Authorization": f"Bearer {self.bearer_token}",
                "Accept": "application/json",
            }
        raw = base64.b64encode(f"{self.email}:{self.api_token}".encode()).decode()
        return {
            "Authorization": f"Basic {raw}",
            "Accept": "application/json",
        }

    def _base(self) -> str:
        return f"{self.url}/rest/api/{self.api_version}"

    def configured(self) -> bool:
        if not self.url:
            return False
        if self.auth_mode == "bearer":
            return bool(self.bearer_token)
        return bool(self.email and self.api_token)

    # ---- calls ----

    async def health_check(self) -> dict:
        """Verify connectivity + credentials via /myself."""
        if not self.configured():
            return {"ok": False, "error": "Jira not configured (URL + credentials)."}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self._base()}/myself", headers=self._headers())
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "ok": True,
                    "display_name": data.get("displayName", ""),
                    "url": self.url,
                }
            if resp.status_code in (401, 403):
                return {"ok": False, "error": f"Jira rejected credentials (HTTP {resp.status_code})."}
            return {"ok": False, "error": f"Jira returned HTTP {resp.status_code}."}
        except httpx.HTTPError as exc:
            return {"ok": False, "error": f"Jira unreachable: {exc}"}

    async def fetch_issue(self, issue_key: str) -> dict:
        """Fetch + normalize a Jira issue."""
        fields = (
            "summary,description,issuetype,status,priority,labels,components,"
            "parent,subtasks,issuelinks,comment"
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self._base()}/issue/{issue_key}",
                params={"fields": fields},
                headers=self._headers(),
            )
        if resp.status_code == 404:
            raise JiraError(f"Issue {issue_key} not found (HTTP 404).", 404)
        if resp.status_code in (401, 403):
            raise JiraError(f"Jira rejected credentials (HTTP {resp.status_code}).", resp.status_code)
        if resp.status_code >= 400:
            raise JiraError(f"Jira REST returned HTTP {resp.status_code}.", resp.status_code)

        payload = resp.json()
        f = payload.get("fields") or {}
        return {
            "key": payload.get("key", issue_key),
            "summary": f.get("summary", ""),
            "description": _normalize_adf(f.get("description")),
            "issue_type": _name_of(f.get("issuetype")),
            "status": _name_of(f.get("status")),
            "priority": _name_of(f.get("priority")),
            "labels": f.get("labels") or [],
            "parent": _key_of(f.get("parent")),
            "url": f"{self.url}/browse/{payload.get('key', issue_key)}",
        }


# ---- ADF normalization (port of jira.ts flattenAdf) ----


def _normalize_adf(input_value: object) -> str:
    if isinstance(input_value, str):
        return input_value.strip()
    if isinstance(input_value, dict) and input_value.get("type") == "doc":
        return _flatten_adf(input_value).strip()
    return ""


def _flatten_adf(node: dict) -> str:
    parts: list[str] = []
    blocks = {
        "paragraph", "heading", "codeBlock", "blockquote", "rule",
        "panel", "listItem", "bulletList", "orderedList", "tableRow", "table",
    }
    for child in node.get("content") or []:
        text = child.get("text") if isinstance(child, dict) else ""
        if not text and isinstance(child, dict):
            text = _flatten_adf(child)
        parts.append(text)
        if child.get("type") in blocks:
            parts.append("\n")
    return " ".join(parts)


def _name_of(container: object) -> str:
    if isinstance(container, dict):
        return str(container.get("name") or container.get("displayName") or "")
    return ""


def _key_of(container: object) -> str:
    if isinstance(container, dict):
        return str(container.get("key") or "")
    return ""
