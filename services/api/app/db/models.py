"""ORM models for the pipeline entities.

Maps the Pydantic API models (pipeline/models.py) to Postgres tables:
- projects        (one row per project)
- pipelines       (one row per project; current_stage pointer)
- stage_runs      (per-stage run rows keyed project_id + stage)
- artifacts       (engine outputs; payload stored as JSON)

Strings for enums (stage, state) keep the schema simple; the Pydantic
re-construction validates on read.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .core import Base


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PipelineRow(Base):
    __tablename__ = "pipelines"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    current_stage: Mapped[str] = mapped_column(String, nullable=False, default="intake")
    # Project-level pipeline inputs (requirement + per-stage overrides) so a
    # reload or a failure-resume can reconstruct the start form and edited
    # inputs without the client holding them.
    inputs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StageRunRow(Base):
    __tablename__ = "stage_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    input_artifact_id: Mapped[str | None] = mapped_column(String, nullable=True)
    output_artifact_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ArtifactRow(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(String, nullable=False, default="awaiting_approval")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppSettingRow(Base):
    """Runtime-settable connector config (seeded from .env on first read).

    key is e.g. 'jira.url', 'jira.api_token', 'github.token'. Storing here
    means the UI Settings page can persist connector details without editing
    the .env file; env vars remain the boot defaults.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PipelineEventRow(Base):
    """Append-only event log for automatic pipeline runs (live UI log).

    The chain runner appends one row per state change / log line; the UI polls
    GET /pipeline/{id}/status and renders these as a live log pane.
    """

    __tablename__ = "pipeline_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    stage: Mapped[str | None] = mapped_column(String, nullable=True)
    level: Mapped[str] = mapped_column(String, nullable=False, default="info")
    message: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
