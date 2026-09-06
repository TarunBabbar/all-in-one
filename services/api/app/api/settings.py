"""Settings + connector routes.

- GET  /settings            -> effective config grouped by jira/github (masked)
- PUT  /settings            -> persist connector details (UI Settings page)
- GET  /settings/test/jira  -> live Jira health check
- GET  /settings/test/github-> live GitHub health check (+ repo reachability)
- POST /connectors/jira/fetch -> fetch + normalize one Jira issue
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..connectors.github import GitHubConnector
from ..connectors.jira import JiraConnector, JiraError
from ..core.settings_store import SettingsStore
from ..db.core import get_session

router = APIRouter(tags=["settings"])


def get_settings_store() -> SettingsStore:
    return SettingsStore()


@router.get("/settings")
async def get_settings_all(
    session: AsyncSession = Depends(get_session),
    store: SettingsStore = Depends(get_settings_store),
) -> dict:
    return await store.all(session, masked=True)


@router.put("/settings")
async def put_settings(
    body: dict,
    session: AsyncSession = Depends(get_session),
    store: SettingsStore = Depends(get_settings_store),
) -> dict:
    await store.put(session, body)
    return {"ok": True, "message": "Settings saved."}


@router.get("/settings/test/jira")
async def test_jira(
    session: AsyncSession = Depends(get_session),
    store: SettingsStore = Depends(get_settings_store),
) -> dict:
    cfg = await store.jira_config(session)
    return await JiraConnector(cfg).health_check()


@router.get("/settings/test/github")
async def test_github(
    session: AsyncSession = Depends(get_session),
    store: SettingsStore = Depends(get_settings_store),
) -> dict:
    cfg = await store.github_config(session)
    gh = GitHubConnector(cfg)
    user = await gh.health_check()
    if not user.get("ok"):
        return user
    repo = await gh.repo_health()
    return {"ok": repo.get("ok", False), "user": user.get("login"), **repo}


@router.post("/connectors/jira/fetch")
async def jira_fetch_issue(
    body: dict,
    session: AsyncSession = Depends(get_session),
    store: SettingsStore = Depends(get_settings_store),
) -> dict:
    issue_key: str = (body.get("issue_key") or "").strip()
    if not issue_key:
        raise HTTPException(status_code=400, detail="issue_key is required")
    cfg = await store.jira_config(session)
    connector = JiraConnector(cfg)
    if not connector.configured():
        raise HTTPException(status_code=400, detail="Jira is not configured (URL + credentials).")
    try:
        issue = await connector.fetch_issue(issue_key)
    except JiraError as exc:
        raise HTTPException(status_code=exc.status or 500, detail=str(exc)) from exc
    return {"issue": issue}


@router.post("/connectors/github/push")
async def github_push(
    body: dict,
    session: AsyncSession = Depends(get_session),
    store: SettingsStore = Depends(get_settings_store),
) -> dict:
    path: str = (body.get("path") or "").strip()
    content: str = body.get("content") or ""
    message: str = body.get("message") or ""
    if not path:
        raise HTTPException(status_code=400, detail="path is required")
    cfg = await store.github_config(session)
    gh = GitHubConnector(cfg)
    if not gh.configured():
        raise HTTPException(status_code=400, detail="GitHub is not configured (token + repo).")
    try:
        result = await gh.write_file(path, content, message)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.post("/connectors/github/push-files")
async def github_push_files(
    body: dict,
    session: AsyncSession = Depends(get_session),
    store: SettingsStore = Depends(get_settings_store),
) -> dict:
    """Push multiple files (e.g. a generated suite) to the repo.

    Body: { files: [{ path, content }], prefix?, message?, branch? }
    Each file goes through the Contents API under an optional prefix dir.
    """
    files: list[dict] = body.get("files") or []
    prefix: str = (body.get("prefix") or "").strip().strip("/")
    message: str = body.get("message") or "chore: update generated QA artifacts"
    if not files:
        raise HTTPException(status_code=400, detail="files is required")
    cfg = await store.github_config(session)
    gh = GitHubConnector(cfg)
    if not gh.configured():
        raise HTTPException(status_code=400, detail="GitHub is not configured (token + repo).")
    if body.get("branch"):
        gh.branch = str(body.get("branch")).strip()

    results = []
    for f in files:
        path = f.get("path") or ""
        content = f.get("content") or ""
        if not path:
            continue
        full = f"{prefix}/{path}" if prefix else path
        try:
            res = await gh.write_file(full, content, message)
            results.append({"path": full, "ok": True, "commit_sha": res.get("commit_sha")})
        except Exception as exc:  # noqa: BLE001 — report per-file
            results.append({"path": full, "ok": False, "error": str(exc)})
    return {"ok": all(r["ok"] for r in results), "results": results}


@router.get("/connectors/github/read")
async def github_read(
    path: str,
    session: AsyncSession = Depends(get_session),
    store: SettingsStore = Depends(get_settings_store),
) -> dict:
    """Read a file from the connected repo (pull)."""
    if not path:
        raise HTTPException(status_code=400, detail="path is required")
    cfg = await store.github_config(session)
    gh = GitHubConnector(cfg)
    if not gh.configured():
        raise HTTPException(status_code=400, detail="GitHub is not configured (token + repo).")
    try:
        result = await gh.read_file(path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, **result}
