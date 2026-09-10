"""Pipeline + engine API routes.

Exposes the orchestrator: create projects, run engines as pipeline stages,
and approve/request-changes/block stage outputs. Also allows running any
engine standalone (the tool pages call these same endpoints).

All handlers are async and pull an AsyncSession from the app dependency so
every pipeline write is transactional and survives restarts (Postgres).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.llm import LLMRouter
from ..core.settings import get_settings
from ..db.core import get_session
from ..engines import modules as _engine_modules  # noqa: F401  (import triggers self-registration)
from ..pipeline import registry
from ..pipeline import runner as chain_runner
from ..pipeline.chain import detect_target_url
from ..pipeline.models import (
    PIPELINE_STAGES,
    Artifact,
    Project,
    StageId,
)
from ..pipeline.store import (
    InvalidTransitionError,
    PipelineNotFoundError,
    PipelineStore,
)

router = APIRouter(tags=["pipeline"])


def get_store() -> PipelineStore:
    return PipelineStore()


# ---- projects ----


@router.post("/projects", response_model=Project)
async def create_project(
    name: str, session: AsyncSession = Depends(get_session)
) -> Project:
    return await get_store().create_project(session, name)


@router.get("/projects", response_model=list[Project])
async def list_projects(session: AsyncSession = Depends(get_session)) -> list[Project]:
    return await get_store().list_projects(session)


@router.get("/projects/{project_id}", response_model=Project)
async def get_project(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> Project:
    try:
        return await get_store().get_project(session, project_id)
    except PipelineNotFoundError:
        raise HTTPException(status_code=404, detail="project not found") from None


# ---- pipeline state ----


@router.get("/pipeline/{project_id}", response_model=dict)
async def get_pipeline_state(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    try:
        pipeline = await get_store().get_pipeline(session, project_id)
    except PipelineNotFoundError:
        raise HTTPException(status_code=404, detail="pipeline not found") from None

    stages: dict[str, dict] = {}
    for stage in PIPELINE_STAGES:
        run = pipeline.stage_runs.get(stage)
        stages[stage.value] = {
            "state": run.state.value if run else "not_started",
            "output_artifact_id": run.output_artifact_id if run else None,
            "error": run.error if run else None,
        }
    return {
        "project_id": project_id,
        "current_stage": pipeline.current_stage.value,
        "stages": stages,
        "inputs": pipeline.inputs,
        "running": chain_runner.is_running(project_id),
    }


# ---- automatic pipeline chain (start / resume / status / stop) ----


@router.post("/pipeline/{project_id}/start")
async def start_pipeline_chain(
    project_id: str,
    body: dict | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Kick off the automatic multi-agent chain for a project.

    Body: {requirement?: str, source?: str, start_stage?: str, overrides?: {...}}
    Stages run back-to-back; on failure the chain stops at the failed stage.
    """
    body = body or {}
    store = get_store()
    try:
        await store.get_pipeline(session, project_id)
    except PipelineNotFoundError:
        raise HTTPException(status_code=404, detail="pipeline not found") from None

    start_stage = None
    if body.get("start_stage"):
        try:
            start_stage = StageId(body["start_stage"])
        except ValueError:
            stage_name = str(body["start_stage"])
            raise HTTPException(status_code=400, detail=f"unknown stage {stage_name}") from None

    try:
        chain_runner.launch_chain(
            project_id,
            start_stage=start_stage,
            requirement=body.get("requirement"),
            source=body.get("source", "text"),
            overrides=body.get("overrides"),
        )
    except chain_runner.PipelineAlreadyRunningError:
        raise HTTPException(status_code=409, detail="pipeline is already running") from None

    return {"ok": True, "project_id": project_id, "running": True}


@router.post("/pipeline/{project_id}/resume")
async def resume_pipeline_chain(
    project_id: str,
    body: dict | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Resume a stopped pipeline from its failed stage with edited inputs."""
    body = body or {}
    stage_raw = body.get("stage")
    if not stage_raw:
        raise HTTPException(status_code=400, detail="stage is required to resume")
    try:
        stage = StageId(stage_raw)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"unknown stage {stage_raw}") from None

    try:
        chain_runner.launch_chain(
            project_id,
            start_stage=stage,
            requirement=body.get("requirement"),
            overrides=body.get("overrides"),
        )
    except chain_runner.PipelineAlreadyRunningError:
        raise HTTPException(status_code=409, detail="pipeline is already running") from None

    return {"ok": True, "project_id": project_id, "running": True}


@router.post("/pipeline/{project_id}/stop")
async def stop_pipeline_chain(
    project_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Cancel the running chain (if any) for a project."""
    try:
        chain_runner.cancel_chain(project_id)
    except chain_runner.PipelineNotRunningError:
        raise HTTPException(status_code=409, detail="pipeline is not running") from None
    return {"ok": True, "project_id": project_id, "running": False}


@router.get("/pipeline/{project_id}/status")
async def get_pipeline_status(
    project_id: str,
    since_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Polled by the UI: stage states + live event log + env defaults."""
    store = get_store()
    try:
        pipeline = await store.get_pipeline(session, project_id)
    except PipelineNotFoundError:
        raise HTTPException(status_code=404, detail="pipeline not found") from None

    stages: dict[str, dict] = {}
    for stage in PIPELINE_STAGES:
        run = pipeline.stage_runs.get(stage)
        stages[stage.value] = {
            "state": run.state.value if run else "not_started",
            "output_artifact_id": run.output_artifact_id if run else None,
            "error": run.error if run else None,
        }

    events = await store.list_events(session, project_id, since_id=since_id)
    settings = get_settings()
    # The app under test is whatever URL the requirement names. Prefer the URL
    # persisted at start (inputs.app_url); fall back to detecting it from the
    # stored requirement text; the env default is the last resort.
    requirement_text = str(pipeline.inputs.get("requirement") or "")
    effective_base_url = str(
        pipeline.inputs.get("app_url")
        or detect_target_url(requirement_text)
        or settings.app_base_url
    )
    return {
        "project_id": project_id,
        "running": chain_runner.is_running(project_id),
        "current_stage": pipeline.current_stage.value,
        "inputs": pipeline.inputs,
        "stages": stages,
        "log": events,
        "defaults": {
            "base_url": effective_base_url,
            "runner_url": settings.runner_url,
        },
    }


# ---- engine execution (standalone + pipeline stages) ----


def _artifact_from_engine_result(
    project_id: str, stage: StageId, result: dict
) -> Artifact:
    """Wrap an engine result dict into a stored Artifact."""
    kind = result.get("kind", "artifact")
    payload = result.get("payload", result)
    return Artifact(
        id=uuid.uuid4().hex,
        project_id=project_id,
        stage=stage,
        kind=kind,
        payload=payload,
    )


@router.post("/pipeline/{project_id}/run-stage/{stage}")
async def run_stage(
    project_id: str,
    stage: StageId,
    body: dict | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Run one pipeline stage's engine, storing its output for approval."""
    body = body or {}
    store = get_store()
    engine_id = body.get("engine") or _engine_for_stage(stage)
    engine = registry.get_engine(engine_id)
    if engine is None:
        raise HTTPException(status_code=404, detail=f"no engine {engine_id}")

    llm = LLMRouter.from_settings(get_settings())
    ctx = {"router": llm, "store": store, "session": session, "project_id": project_id}

    try:
        fn = engine.run
        if fn is None:
            raise HTTPException(status_code=501, detail=f"engine {engine.id} not implemented")
        result = await fn(ctx, **body.get("input", {}))
    except HTTPException:
        raise
    except Exception as exc:  # engine failure -> stage blocked
        run = await store.fail_stage(session, project_id, stage, str(exc))
        return {"stage": stage.value, "state": run.state.value, "error": run.error}

    artifact = _artifact_from_engine_result(project_id, stage, result)
    run = await store.complete_stage(session, project_id, stage, artifact)
    await store.advance(session, project_id)
    return {
        "stage": stage.value,
        "state": run.state.value,
        "artifact_id": artifact.id,
        "payload": artifact.payload,
    }


def _engine_for_stage(stage: StageId) -> str:
    """Map a pipeline stage to its default engine."""
    return {
        StageId.INTAKE: "intake",
        StageId.DOCTOR: "requirement-doctor",
        StageId.TEST_CASES: "test-cases",
        StageId.CODEGEN: "codegen",
        StageId.RUN: "executor",
        StageId.TRIAGE: "failure-triage",
        StageId.VISUAL: "visual",
        StageId.RELEASE: "release-gate",
    }.get(stage, "demo")


# ---- approvals ----


@router.post("/pipeline/{project_id}/approve/{stage}")
async def approve_stage(
    project_id: str,
    stage: StageId,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await _set_approval(project_id, stage, "approve", session)


@router.post("/pipeline/{project_id}/request-changes/{stage}")
async def request_changes_stage(
    project_id: str,
    stage: StageId,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await _set_approval(project_id, stage, "request_changes", session)


@router.post("/pipeline/{project_id}/block/{stage}")
async def block_stage(
    project_id: str,
    stage: StageId,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await _set_approval(project_id, stage, "block", session)


async def _set_approval(
    project_id: str, stage: StageId, action: str, session: AsyncSession
) -> dict:
    store = get_store()
    try:
        run = await store.set_approval(session, project_id, stage, action)
    except PipelineNotFoundError:
        raise HTTPException(status_code=404, detail="stage not found") from None
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return {"stage": stage.value, "state": run.state.value}


# ---- artifacts ----


@router.get("/artifacts/{artifact_id}")
async def get_artifact(
    artifact_id: str, session: AsyncSession = Depends(get_session)
) -> Artifact:
    try:
        return await get_store().get_artifact(session, artifact_id)
    except PipelineNotFoundError:
        raise HTTPException(status_code=404, detail="artifact not found") from None


@router.get("/projects/{project_id}/artifacts", response_model=list[Artifact])
async def list_artifacts(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> list[Artifact]:
    return await get_store().list_artifacts(session, project_id)


@router.post("/export/cases")
def export_cases_route(body: dict) -> dict:
    """Export test cases to csv|jira|json. Body: {cases: [...], format: str}."""
    from ..export.cases import export_cases

    cases: list[dict] = body.get("cases", [])
    fmt: str = body.get("format", "csv")
    if not cases:
        raise HTTPException(status_code=400, detail="no cases to export")
    content, content_type = export_cases(cases, fmt)
    return {"format": fmt, "content_type": content_type, "content": content}


# ---- engines (registry introspection) ----


@router.get("/engines")
def list_engines() -> list[dict]:
    return [
        {
            "id": e.id,
            "name": e.name,
            "description": e.description,
            "uses_llm": e.uses_llm,
            "uses_runner": e.uses_runner,
        }
        for e in registry.all_engines()
    ]


@router.post("/engines/{engine_id}/run")
async def run_engine_standalone(
    engine_id: str, body: dict | None = None, session: AsyncSession = Depends(get_session)
) -> dict:
    """Run any engine standalone (tool pages call this). No project needed."""
    body = body or {}
    engine = registry.get_engine(engine_id)
    if engine is None:
        raise HTTPException(status_code=404, detail=f"no engine {engine_id}")

    llm = LLMRouter.from_settings(get_settings())
    store = get_store()
    ctx = {"router": llm, "store": store, "session": session, "project_id": None}

    try:
        fn = engine.run
        if fn is None:
            raise HTTPException(status_code=501, detail=f"engine {engine.id} not implemented")
        result = await fn(ctx, **body.get("input", {}))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — surface engine errors cleanly
        raise HTTPException(status_code=500, detail=f"{engine_id} failed: {exc}") from exc

    return {
        "engine": engine_id,
        "kind": result.get("kind", "result"),
        "payload": result.get("payload", result),
    }
