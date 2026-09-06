"""GitHub REST connector.

Uses a Personal Access Token (stored via Settings UI/.env). Supports:
- health check (GET /user)
- read a file from the repo (pull)
- create/update a file via the Contents API (push, returns commit sha)

Pattern mirrors how the hackathon projects used GitHub: token auth + REST
contents API for reading/writing repo files.
"""

from __future__ import annotations

import base64

import httpx


class GitHubError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class GitHubConnector:
    def __init__(self, config: dict) -> None:
        self.token = config.get("token") or ""
        self.repo = (config.get("repo") or "").strip()
        self.branch = config.get("branch") or "master"
        self.api_base = (config.get("api_base") or "https://api.github.com").rstrip("/")

    def _headers(self) -> dict[str, str]:
        h = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def configured(self) -> bool:
        return bool(self.token and self.repo)

    async def health_check(self) -> dict:
        if not self.token:
            return {"ok": False, "error": "GitHub token is not set."}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(f"{self.api_base}/user", headers=self._headers())
            if resp.status_code == 200:
                data = resp.json()
                return {"ok": True, "login": data.get("login", ""), "url": self.api_base}
            if resp.status_code in (401, 403):
                return {"ok": False, "error": f"GitHub rejected token (HTTP {resp.status_code})."}
            return {"ok": False, "error": f"GitHub returned HTTP {resp.status_code}."}
        except httpx.HTTPError as exc:
            return {"ok": False, "error": f"GitHub unreachable: {exc}"}

    async def repo_health(self) -> dict:
        """Verify the repo is reachable + returns its default branch."""
        if not self.configured():
            return {"ok": False, "error": "GitHub token + repo required."}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(f"{self.api_base}/repos/{self.repo}", headers=self._headers())
            if resp.status_code == 200:
                data = resp.json()
                return {"ok": True, "full_name": data.get("full_name"), "default_branch": data.get("default_branch")}
            return {"ok": False, "error": f"Repo {self.repo}: HTTP {resp.status_code}."}
        except httpx.HTTPError as exc:
            return {"ok": False, "error": f"GitHub unreachable: {exc}"}

    async def read_file(self, path: str) -> dict:
        """Pull a file's content (and current sha) from the repo."""
        url = f"{self.api_base}/repos/{self.repo}/contents/{path}"
        params = {"ref": self.branch}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, params=params, headers=self._headers())
        if resp.status_code == 404:
            raise GitHubError(f"{path} not found in {self.repo}@{self.branch}.", 404)
        if resp.status_code >= 400:
            raise GitHubError(f"GitHub returned HTTP {resp.status_code}.", resp.status_code)
        data = resp.json()
        content = base64.b64decode(data.get("content", "")).decode("utf-8", "replace")
        return {"path": path, "content": content, "sha": data.get("sha"), "size": data.get("size")}

    async def write_file(self, path: str, content: str, message: str) -> dict:
        """Create or update a file (push). Returns the new commit sha."""
        try:
            existing = await self.read_file(path)
            sha = existing.get("sha")
        except GitHubError:
            sha = None  # new file
        body = {
            "message": message or f"chore: update {path}",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": self.branch,
        }
        if sha:
            body["sha"] = sha
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.put(
                f"{self.api_base}/repos/{self.repo}/contents/{path}",
                json=body,
                headers=self._headers(),
            )
        if resp.status_code not in (200, 201):
            raise GitHubError(f"GitHub push failed: HTTP {resp.status_code} {resp.text[:200]}", resp.status_code)
        data = resp.json()
        return {"path": path, "commit_sha": data.get("commit", {}).get("sha"), "message": message}
