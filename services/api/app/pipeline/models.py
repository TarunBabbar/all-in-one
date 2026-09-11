"""Pipeline domain models — artifacts and state shared by every engine.

These are the canonical contracts from docs/module-contracts.md. Engines
produce/consume these; the orchestrator stores them per project and advances
the pipeline stage by stage behind approval gates.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


class ApprovalState(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    BLOCKED = "blocked"


class StageId(StrEnum):
    INTAKE = "intake"
    DOCTOR = "doctor"
    TEST_PLAN = "test_plan"
    EVAL_PLAN = "eval_plan"
    TEST_CASES = "test_cases"
    EVAL_CASES = "eval_cases"
    CODEGEN = "codegen"
    EVAL_CODE = "eval_code"
    RUN = "run"
    TRIAGE = "triage"
    VISUAL = "visual"
    RELEASE = "release"


# Ordered pipeline definition. Each generator is followed by its eval gate, so
# a weak artifact stops the chain at the gate that detected it rather than
# propagating downstream. The gates are deterministic and cost no tokens.
PIPELINE_STAGES: list[StageId] = [
    StageId.INTAKE,
    StageId.DOCTOR,
    StageId.TEST_PLAN,
    StageId.EVAL_PLAN,
    StageId.TEST_CASES,
    StageId.EVAL_CASES,
    StageId.CODEGEN,
    StageId.EVAL_CODE,
    StageId.RUN,
    StageId.TRIAGE,
    StageId.VISUAL,
    StageId.RELEASE,
]

# Visual stage is OPTIONAL: pipelines without screenshots skip it. Absent
# optional stages never block advancement.
SKIPPABLE_STAGES: set[StageId] = {StageId.VISUAL}

# Eval gates: deterministic scoring stages. Listed here so the UI can render
# them compactly (they produce a metric table, not a document).
EVAL_STAGES: set[StageId] = {StageId.EVAL_PLAN, StageId.EVAL_CASES, StageId.EVAL_CODE}


class Project(BaseModel):
    id: str
    name: str
    created_at: datetime = Field(default_factory=utcnow)


class Artifact(BaseModel):
    """A stage output: typed JSON payload stored for review/approval."""

    id: str
    project_id: str
    stage: StageId
    kind: str  # e.g. "requirement", "doctor_report", "test_cases", ...
    payload: dict[str, Any]
    state: ApprovalState = ApprovalState.AWAITING_APPROVAL
    created_at: datetime = Field(default_factory=utcnow)


class StageRun(BaseModel):
    """One execution of one pipeline stage within a project."""

    id: str
    project_id: str
    stage: StageId
    state: ApprovalState = ApprovalState.DRAFT
    input_artifact_id: str | None = None
    output_artifact_id: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Pipeline(BaseModel):
    """A project's end-to-end pipeline: ordered stage runs + current pointer."""

    id: str
    project_id: str
    stage_runs: dict[StageId, StageRun] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    current_stage: StageId = StageId.INTAKE
    created_at: datetime = Field(default_factory=utcnow)

    def next_pending_stage(self) -> StageId | None:
        """First stage whose run is not yet approved, or None if all approved.

        Skips optional stages (e.g. visual) that were never started, so an
        absent optional stage does not block the pipeline.
        """
        for stage in PIPELINE_STAGES:
            run = self.stage_runs.get(stage)
            if run is None:
                if stage in SKIPPABLE_STAGES:
                    continue  # optional and never run — skip it
                return stage
            if run.state != ApprovalState.APPROVED:
                return stage
        return None
