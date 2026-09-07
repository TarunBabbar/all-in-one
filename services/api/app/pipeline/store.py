"""Pipeline orchestrator — Postgres-backed store + approval state machine.

The state machine is the QAGuard/Manish human-in-the-loop pattern: an engine
writes a draft artifact -> state becomes awaiting_approval -> a human approves,
requests changes, or blocks -> only APPROVED artifacts advance to the next
stage. Visual stage is OPTIONAL: pipelines may skip it.

Every method is async and takes an AsyncSession so callers control
transactions. Rows are mapped to the Pydantic API models on read.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import models as db
from ..pipeline.models import (
    ApprovalState,
    Artifact,
    Pipeline,
    Project,
    StageId,
    StageRun,
)


class PipelineNotFoundError(KeyError):
    pass


class InvalidTransitionError(RuntimeError):
    pass


class PipelineStore:
    """Async store over Postgres (or sqlite in tests)."""

    # ---- projects ----

    async def create_project(self, session: AsyncSession, name: str) -> Project:
        project_id = uuid.uuid4().hex
        session.add(db.ProjectRow(id=project_id, name=name))
        session.add(db.PipelineRow(id=uuid.uuid4().hex, project_id=project_id))
        await session.commit()
        return Project(id=project_id, name=name)

    async def get_project(self, session: AsyncSession, project_id: str) -> Project:
        row = await session.get(db.ProjectRow, project_id)
        if row is None:
            raise PipelineNotFoundError(project_id)
        return Project(id=row.id, name=row.name, created_at=row.created_at)

    async def list_projects(self, session: AsyncSession) -> list[Project]:
        rows = (
            await session.execute(select(db.ProjectRow).order_by(db.ProjectRow.created_at.desc()))
        ).scalars().all()
        return [Project(id=r.id, name=r.name, created_at=r.created_at) for r in rows]

    # ---- pipelines ----

    async def get_pipeline(self, session: AsyncSession, project_id: str) -> Pipeline:
        prow = (
            await session.execute(
                select(db.PipelineRow).where(db.PipelineRow.project_id == project_id)
            )
        ).scalar_one_or_none()
        if prow is None:
            raise PipelineNotFoundError(project_id)
        runs = (
            await session.execute(
                select(db.StageRunRow).where(db.StageRunRow.project_id == project_id)
            )
        ).scalars().all()
        return Pipeline(
            id=prow.id,
            project_id=project_id,
            current_stage=StageId(prow.current_stage),
            inputs=dict(prow.inputs or {}),
            stage_runs={StageId(r.stage): _to_stage_run(r) for r in runs},
            created_at=prow.created_at,
        )

    async def set_pipeline_inputs(
        self, session: AsyncSession, project_id: str, inputs: dict
    ) -> None:
        """Persist project-level pipeline inputs (requirement + overrides)."""
        prow = (
            await session.execute(
                select(db.PipelineRow).where(db.PipelineRow.project_id == project_id)
            )
        ).scalar_one_or_none()
        if prow is None:
            raise PipelineNotFoundError(project_id)
        prow.inputs = inputs
        await session.commit()

    # ---- stage runs ----

    async def get_stage_run(
        self, session: AsyncSession, project_id: str, stage: StageId
    ) -> StageRun:
        row = (
            await session.execute(
                select(db.StageRunRow).where(
                    db.StageRunRow.project_id == project_id,
                    db.StageRunRow.stage == stage.value,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise PipelineNotFoundError(f"{project_id}:{stage.value}")
        return _to_stage_run(row)

    async def _upsert_run(
        self, session: AsyncSession, project_id: str, stage: StageId, **fields
    ) -> StageRun:
        """Insert or update a stage run row and return the Pydantic model."""
        row = (
            await session.execute(
                select(db.StageRunRow).where(
                    db.StageRunRow.project_id == project_id,
                    db.StageRunRow.stage == stage.value,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = db.StageRunRow(
                id=uuid.uuid4().hex,
                project_id=project_id,
                stage=stage.value,
            )
            session.add(row)
        for key, value in fields.items():
            setattr(row, key, value)
        # Keep current_stage pointer in sync.
        prow = (
            await session.execute(
                select(db.PipelineRow).where(db.PipelineRow.project_id == project_id)
            )
        ).scalar_one_or_none()
        if prow is not None:
            prow.current_stage = stage.value
        await session.commit()
        await session.refresh(row)
        return _to_stage_run(row)

    async def start_stage(
        self, session: AsyncSession, project_id: str, stage: StageId
    ) -> StageRun:
        return await self._upsert_run(
            session,
            project_id,
            stage,
            state=ApprovalState.DRAFT.value,
            output_artifact_id=None,
            error=None,
        )

    async def set_stage_running(
        self,
        session: AsyncSession,
        project_id: str,
        stage: StageId,
        input_artifact_id: str | None = None,
    ) -> StageRun:
        """Mark a stage as executing (automatic chain, live UI state)."""
        return await self._upsert_run(
            session,
            project_id,
            stage,
            state=ApprovalState.RUNNING.value,
            error=None,
            input_artifact_id=input_artifact_id or None,
        )

    async def complete_stage_auto(
        self,
        session: AsyncSession,
        project_id: str,
        stage: StageId,
        artifact: Artifact,
    ) -> StageRun:
        """Store a stage output and mark the stage approved in one step.

        Used by the automatic chain runner: a successful stage output is
        accepted without a human approval gate and execution continues to the
        next stage.
        """
        session.add(
            db.ArtifactRow(
                id=artifact.id,
                project_id=project_id,
                stage=stage.value,
                kind=artifact.kind,
                payload=artifact.payload,
                state=ApprovalState.APPROVED.value,
            )
        )
        run = await self._upsert_run(
            session,
            project_id,
            stage,
            output_artifact_id=artifact.id,
            state=ApprovalState.APPROVED.value,
            error=None,
        )
        return run

    async def complete_stage(
        self, session: AsyncSession, project_id: str, stage: StageId, artifact: Artifact
    ) -> StageRun:
        # Persist the artifact first.
        session.add(
            db.ArtifactRow(
                id=artifact.id,
                project_id=project_id,
                stage=stage.value,
                kind=artifact.kind,
                payload=artifact.payload,
                state=artifact.state.value,
            )
        )
        run = await self._upsert_run(
            session,
            project_id,
            stage,
            output_artifact_id=artifact.id,
            state=ApprovalState.AWAITING_APPROVAL.value,
        )
        return run

    async def fail_stage(
        self, session: AsyncSession, project_id: str, stage: StageId, error: str
    ) -> StageRun:
        return await self._upsert_run(
            session,
            project_id,
            stage,
            state=ApprovalState.BLOCKED.value,
            error=error,
        )

    # ---- approvals ----

    async def set_approval(
        self, session: AsyncSession, project_id: str, stage: StageId, action: str
    ) -> StageRun:
        """Human gate: approve | request_changes | block the stage output."""
        row = (
            await session.execute(
                select(db.StageRunRow).where(
                    db.StageRunRow.project_id == project_id,
                    db.StageRunRow.stage == stage.value,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise PipelineNotFoundError(f"{project_id}:{stage.value}")
        if row.state != ApprovalState.AWAITING_APPROVAL.value:
            raise InvalidTransitionError(
                f"stage {stage.value} is {row.state}, not awaiting_approval"
            )
        if action == "approve":
            row.state = ApprovalState.APPROVED.value
        elif action == "request_changes":
            row.state = ApprovalState.CHANGES_REQUESTED.value
        elif action == "block":
            row.state = ApprovalState.BLOCKED.value
        else:
            raise InvalidTransitionError(f"unknown action {action}")
        # Advance current_stage past the approved/settled stage.
        await self._advance_row(session, project_id)
        await session.commit()
        await session.refresh(row)
        return _to_stage_run(row)

    async def _advance_row(self, session: AsyncSession, project_id: str) -> None:
        pipeline = await self.get_pipeline(session, project_id)
        nxt = pipeline.next_pending_stage()
        prow = (
            await session.execute(
                select(db.PipelineRow).where(db.PipelineRow.project_id == project_id)
            )
        ).scalar_one()
        prow.current_stage = (nxt or pipeline.current_stage).value

    async def advance(self, session: AsyncSession, project_id: str) -> StageId | None:
        """After an approval, move the pointer to the next non-approved stage."""
        pipeline = await self.get_pipeline(session, project_id)
        prow = (
            await session.execute(
                select(db.PipelineRow).where(db.PipelineRow.project_id == project_id)
            )
        ).scalar_one()
        nxt = pipeline.next_pending_stage()
        prow.current_stage = (nxt or pipeline.current_stage).value
        await session.commit()
        return nxt or pipeline.current_stage

    # ---- artifacts ----

    async def get_artifact(self, session: AsyncSession, artifact_id: str) -> Artifact:
        row = await session.get(db.ArtifactRow, artifact_id)
        if row is None:
            raise PipelineNotFoundError(artifact_id)
        return _to_artifact(row)

    async def list_artifacts(self, session: AsyncSession, project_id: str) -> list[Artifact]:
        rows = (
            await session.execute(
                select(db.ArtifactRow)
                .where(db.ArtifactRow.project_id == project_id)
                .order_by(db.ArtifactRow.created_at)
            )
        ).scalars().all()
        return [_to_artifact(r) for r in rows]

    async def get_latest_artifact(
        self, session: AsyncSession, project_id: str, stage: StageId
    ) -> Artifact | None:
        """Most recent artifact stored for a stage (chain input resolution)."""
        row = (
            await session.execute(
                select(db.ArtifactRow)
                .where(
                    db.ArtifactRow.project_id == project_id,
                    db.ArtifactRow.stage == stage.value,
                )
                .order_by(db.ArtifactRow.created_at.desc())
            )
        ).scalars().first()
        return _to_artifact(row) if row else None

    # ---- pipeline events (live log) ----

    async def add_event(
        self,
        session: AsyncSession,
        project_id: str,
        message: str,
        *,
        stage: StageId | str | None = None,
        level: str = "info",
        run_id: str | None = None,
    ) -> None:
        """Append one line to the pipeline's event log."""
        session.add(
            db.PipelineEventRow(
                id=uuid.uuid4().hex,
                project_id=project_id,
                run_id=run_id,
                stage=stage.value if isinstance(stage, StageId) else stage,
                level=level,
                message=message,
            )
        )
        await session.commit()

    async def list_events(
        self,
        session: AsyncSession,
        project_id: str,
        *,
        limit: int = 500,
        since_id: str | None = None,
    ) -> list[dict]:
        """Most recent event rows oldest-first (for the live UI log)."""
        stmt = (
            select(db.PipelineEventRow)
            .where(db.PipelineEventRow.project_id == project_id)
            .order_by(db.PipelineEventRow.created_at.asc(), db.PipelineEventRow.id.asc())
        )
        if since_id:
            stmt = stmt.where(db.PipelineEventRow.id > since_id)
        rows = (await session.execute(stmt.limit(limit))).scalars().all()
        return [
            {
                "id": r.id,
                "stage": r.stage,
                "level": r.level,
                "message": r.message,
                "created_at": r.created_at,
            }
            for r in rows
        ]


# ---- mappers ----


def _to_stage_run(row: db.StageRunRow) -> StageRun:
    return StageRun(
        id=row.id,
        project_id=row.project_id,
        stage=StageId(row.stage),
        state=ApprovalState(row.state),
        input_artifact_id=row.input_artifact_id,
        output_artifact_id=row.output_artifact_id,
        error=row.error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_artifact(row: db.ArtifactRow) -> Artifact:
    return Artifact(
        id=row.id,
        project_id=row.project_id,
        stage=StageId(row.stage),
        kind=row.kind,
        payload=row.payload,
        state=ApprovalState(row.state),
        created_at=row.created_at,
    )
