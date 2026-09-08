"""Automatic pipeline chain runner.

Runs the stage engines back-to-back in a background asyncio task so the UI can
stream live progress. Each successful stage output is stored and auto-approved;
execution advances to the next stage. On failure the chain stops at the failed
stage (state=blocked) so a user can edit that stage's inputs and resume.

Concurrency: a per-project in-memory registry guards against double-starts
(one running task per project). Suitable for the single-process dev/demo API;
a multi-worker deployment would need a DB-backed lock or job queue instead.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.llm import LLMRouter
from ..core.settings import get_settings
from ..db.core import get_session_factory
from ..engines import modules as _engine_modules  # noqa: F401  (self-register)
from ..pipeline import registry
from ..pipeline.chain import detect_target_url, resolve_stage_inputs, stage_order
from ..pipeline.models import (
    ApprovalState,
    Artifact,
    StageId,
)
from ..pipeline.store import PipelineStore

# Default engine per pipeline stage (mirrors the old per-stage route mapping).
_ENGINE_FOR_STAGE: dict[StageId, str] = {
    StageId.INTAKE: "intake",
    StageId.DOCTOR: "requirement-doctor",
    StageId.TEST_CASES: "test-cases",
    StageId.CODEGEN: "codegen",
    StageId.RUN: "executor",
    StageId.TRIAGE: "failure-triage",
    StageId.VISUAL: "visual",
    StageId.RELEASE: "release-gate",
}


class PipelineAlreadyRunningError(RuntimeError):
    pass


class PipelineNotRunningError(RuntimeError):
    pass


class ChainRun:
    """Handle to one in-flight chain task for a project."""

    def __init__(self, project_id: str, task: asyncio.Task, run_id: str) -> None:
        self.project_id = project_id
        self.task = task
        self.run_id = run_id

    @property
    def done(self) -> bool:
        return self.task.done()


# In-memory registry of active chains keyed by project_id.
_ACTIVE: dict[str, ChainRun] = {}


def is_running(project_id: str) -> bool:
    run = _ACTIVE.get(project_id)
    return run is not None and not run.done


def get_run_id(project_id: str) -> str | None:
    run = _ACTIVE.get(project_id)
    return run.run_id if run is not None else None


def launch_chain(
    project_id: str,
    *,
    start_stage: StageId | None = None,
    requirement: str | None = None,
    source: str = "text",
    overrides: dict[str, dict[str, Any]] | None = None,
) -> ChainRun:
    """Start (or resume) the automatic chain for a project in the background."""
    if is_running(project_id):
        raise PipelineAlreadyRunningError("pipeline is already running")

    run_id = uuid.uuid4().hex
    task = asyncio.create_task(
        _run_chain(
            project_id,
            start_stage=start_stage,
            requirement=requirement,
            source=source,
            overrides=overrides,
            run_id=run_id,
        )
    )
    run = ChainRun(project_id, task, run_id)
    _ACTIVE[project_id] = run
    task.add_done_callback(lambda _t: _ACTIVE.pop(project_id, None))
    return run


def cancel_chain(project_id: str) -> None:
    run = _ACTIVE.get(project_id)
    if run is None or run.done:
        raise PipelineNotRunningError("pipeline is not running")
    run.task.cancel()


def _artifact_from_result(project_id: str, stage: StageId, result: dict) -> Artifact:
    kind = result.get("kind", "artifact")
    payload = result.get("payload", result)
    return Artifact(
        id=uuid.uuid4().hex,
        project_id=project_id,
        stage=stage,
        kind=kind,
        payload=payload,
    )


def _is_hard_failure(result: dict) -> bool:
    """Engines that swallow operational errors into a success-shaped payload.

    The executor returns `runner_unreachable` / empty-files results instead of
    raising; under automation those must stop the chain so a user can fix the
    runner URL and resume.
    """
    payload = result.get("payload", {}) or {}
    if payload.get("runner_unreachable"):
        return True
    if payload.get("error"):
        return True
    return False


def _failure_message(stage: StageId, result: dict) -> str:
    payload = result.get("payload", {}) or {}
    if payload.get("runner_unreachable"):
        runner = payload.get("runner") or "the runner"
        error = payload.get("error")
        detail = f" ({error})" if error else ""
        return (
            f"Runner unreachable at {runner}{detail}. Start the runner (or edit "
            "the runner URL) then resume from this stage."
        )
    return str(payload.get("error") or f"{stage.value} stage failed")


async def _run_chain(
    project_id: str,
    *,
    start_stage: StageId | None,
    requirement: str | None,
    source: str,
    overrides: dict[str, dict[str, Any]] | None,
    run_id: str,
) -> None:
    store = PipelineStore()
    session_factory = get_session_factory()
    llm = LLMRouter.from_settings(get_settings())

    # 1. Persist the project inputs (requirement + overrides) so status
    #    reloads and resumes reconstruct the same form.
    async with session_factory() as session:
        pipeline = await store.get_pipeline(session, project_id)
        inputs = dict(pipeline.inputs or {})
        if requirement is not None:
            inputs["requirement"] = requirement
            inputs["source"] = source
            # Detect the app-under-test URL from the requirement (user may
            # paste a link / `url:` prefix). Empty -> resolver uses env fallback.
            detected = detect_target_url(requirement)
            if detected:
                inputs["app_url"] = detected
        merged_overrides = dict(inputs.get("overrides", {}) or {})
        for stage, ov in (overrides or {}).items():
            merged_overrides[stage] = {**merged_overrides.get(stage, {}), **(ov or {})}
        inputs["overrides"] = merged_overrides
        await store.set_pipeline_inputs(session, project_id, inputs)
        await store.add_event(
            session,
            project_id,
            f"Pipeline started (run {run_id[:8]})",
            run_id=run_id,
        )

    try:
        # 2. Walk the stages from the resume point (or the first pending one).
        stages = stage_order()
        start_idx = 0
        if start_stage is not None and start_stage in stages:
            start_idx = stages.index(start_stage)

        for stage in stages[start_idx:]:
            async with session_factory() as session:
                pipeline = await store.get_pipeline(session, project_id)
                if pipeline.stage_runs.get(stage) is not None:
                    run_state = pipeline.stage_runs[stage].state
                    if run_state == ApprovalState.APPROVED:
                        continue  # already done — move to the next stage
                    if run_state == ApprovalState.RUNNING:
                        # A stale running row from a previous crashed run:
                        # treat as rerunnable.
                        pass

            async with session_factory() as session:
                await store.add_event(
                    session,
                    project_id,
                    f"Starting {stage.value}…",
                    stage=stage,
                    level="info",
                    run_id=run_id,
                )

            # 3. Resolve inputs from prior artifacts + persisted overrides.
            async with session_factory() as session:
                pipeline = await store.get_pipeline(session, project_id)
                artifact_by_stage = {}
                for prior in stages[: stages.index(stage)]:
                    if prior in pipeline.stage_runs:
                        aid = pipeline.stage_runs[prior].output_artifact_id
                        if aid:
                            artifact_by_stage[prior] = await store.get_artifact(session, aid)
                stage_inputs = resolve_stage_inputs(
                    stage=stage,
                    artifacts=artifact_by_stage,
                    inputs=pipeline.inputs,
                )
                await store.set_stage_running(
                    session,
                    project_id,
                    stage,
                    input_artifact_id=artifact_by_stage.get(stage) is not None
                    and artifact_by_stage[stage].id
                    or None,
                )

            # 4. Execute the engine.
            engine_id = _ENGINE_FOR_STAGE.get(stage, "demo")
            engine = registry.get_engine(engine_id)
            if engine is None or engine.run is None:
                await _fail(
                    store, session_factory, project_id, stage, run_id,
                    f"no engine registered for stage {stage.value}",
                )
                return

            ctx = {"router": llm, "store": store, "session": None, "project_id": project_id}
            try:
                result = await engine.run(ctx, **stage_inputs)
            except Exception as exc:  # noqa: BLE001 — any engine error stops the chain
                await _fail(
                    store, session_factory, project_id, stage, run_id, str(exc)
                )
                return

            # 5. Success → store + auto-approve + log; failure → stop.
            if _is_hard_failure(result):
                await _fail(
                    store, session_factory, project_id, stage, run_id,
                    _failure_message(stage, result),
                )
                return

            artifact = _artifact_from_result(project_id, stage, result)
            async with session_factory() as session:
                await store.complete_stage_auto(session, project_id, stage, artifact)
                summary = _summarize(stage, artifact.payload)
                await store.add_event(
                    session,
                    project_id,
                    f"{stage.value} complete — {summary}",
                    stage=stage,
                    level="success",
                    run_id=run_id,
                )

        async with session_factory() as session:
            await store.add_event(
                session,
                project_id,
                "Pipeline finished",
                level="success",
                run_id=run_id,
            )
    except asyncio.CancelledError:
        async with session_factory() as session:
            await store.add_event(
                session,
                project_id,
                "Pipeline stopped by user",
                level="warn",
                run_id=run_id,
            )
        raise


async def _fail(
    store: PipelineStore,
    session_factory,
    project_id: str,
    stage: StageId,
    run_id: str,
    message: str,
) -> None:
    async with session_factory() as session:
        await store.fail_stage(session, project_id, stage, message)
        await store.add_event(
            session,
            project_id,
            f"{stage.value} failed — {message}",
            stage=stage,
            level="error",
            run_id=run_id,
        )


def _summarize(stage: StageId, payload: dict) -> str:
    """One-line human summary of a stage output for the live log."""
    try:
        if stage == StageId.INTAKE:
            words = payload.get("word_count")
            return f"requirement normalized ({words} words)" if words else "requirement captured"
        if stage == StageId.DOCTOR:
            score = (payload.get("diagnosis") or {}).get("quality_score")
            return f"quality score {score}/100" if score is not None else "diagnosis complete"
        if stage == StageId.TEST_CASES:
            return f"{payload.get('count', 0)} test cases"
        if stage == StageId.CODEGEN:
            files = payload.get("files") or {}
            n = len(files.get("tests") or []) if isinstance(files, dict) else 0
            return f"suite with {n} file(s) generated"
        if stage == StageId.RUN:
            results = payload.get("results") or []
            passed = sum(1 for r in results if r.get("status") == "passed")
            return f"{passed}/{len(results)} tests passed"
        if stage == StageId.TRIAGE:
            return f"{payload.get('total_failures', 0)} failure(s) clustered"
        if stage == StageId.VISUAL:
            return "visual report generated"
        if stage == StageId.RELEASE:
            verdict = payload.get("verdict")
            return f"verdict {verdict}" if verdict else "decision complete"
    except Exception:  # noqa: BLE001 — summary is best-effort
        pass
    return "done"
