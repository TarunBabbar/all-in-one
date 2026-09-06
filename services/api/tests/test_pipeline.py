"""Pipeline store + engine tests: the requirement→release flow with gates.

Uses the sqlite-backed TestClient fixture from conftest. Store-level tests
run against a fresh AsyncSession bound to the same DATABASE_URL.
"""

from __future__ import annotations

import pytest

from app.db.core import get_session_factory, init_db
from app.pipeline.models import ApprovalState, Artifact, StageId
from app.pipeline.store import InvalidTransitionError, PipelineStore


async def _run_store(fn):
    """Run an async store exercise against a fresh session + sqlite tables."""
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        return await fn(session)


@pytest.mark.asyncio
async def test_store_create_project_and_pipeline() -> None:
    store = PipelineStore()

    async def _exercise(session):
        project = await store.create_project(session, "test")
        pipeline = await store.get_pipeline(session, project.id)
        assert pipeline.project_id == project.id
        got = await store.get_project(session, project.id)
        assert got.name == "test"

    await _run_store(_exercise)


@pytest.mark.asyncio
async def test_store_approval_state_machine() -> None:
    store = PipelineStore()

    async def _exercise(session):
        project = await store.create_project(session, "flow")
        artifact = Artifact(
            id="a1", project_id=project.id, stage=StageId.DOCTOR, kind="doctor_report",
            payload={"score": 80},
        )
        run = await store.complete_stage(session, project.id, StageId.DOCTOR, artifact)
        assert run.state == ApprovalState.AWAITING_APPROVAL

        run = await store.set_approval(session, project.id, StageId.DOCTOR, "approve")
        assert run.state == ApprovalState.APPROVED

        with pytest.raises(InvalidTransitionError):
            await store.set_approval(session, project.id, StageId.DOCTOR, "block")

    await _run_store(_exercise)


@pytest.mark.asyncio
async def test_optional_visual_stage_is_skipped() -> None:
    """A pipeline that never runs VISUAL must still advance to RELEASE."""
    store = PipelineStore()

    async def _exercise(session):
        project = await store.create_project(session, "skip-visual")
        for stage in [StageId.INTAKE, StageId.DOCTOR, StageId.TEST_CASES, StageId.CODEGEN,
                      StageId.RUN, StageId.TRIAGE]:
            artifact = Artifact(id=f"a-{stage.value}", project_id=project.id, stage=stage,
                                kind=stage.value, payload={"ok": True})
            await store.complete_stage(session, project.id, stage, artifact)
            await store.set_approval(session, project.id, stage, "approve")
        pipeline = await store.get_pipeline(session, project.id)
        assert pipeline.next_pending_stage().value == "release"

    await _run_store(_exercise)


def test_full_pipeline_via_api(client) -> None:
    """End-to-end happy path over the HTTP API with Mock LLM + sqlite."""
    r = client.post("/projects", params={"name": "Search feature"})
    assert r.status_code == 200
    project = r.json()
    pid = project["id"]

    # Run doctor stage
    r = client.post(
        f"/pipeline/{pid}/run-stage/doctor",
        json={"input": {"text": "As a user I should be able to search by keyword."}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "awaiting_approval"
    assert body["payload"]["diagnosis"]["quality_score"] >= 0

    # Approve doctor
    r = client.post(f"/pipeline/{pid}/approve/doctor")
    assert r.status_code == 200
    assert r.json()["state"] == "approved"

    # Run + approve test-cases
    r = client.post(
        f"/pipeline/{pid}/run-stage/test_cases",
        json={"input": {"text": "As a user I should be able to search by keyword."}},
    )
    assert r.status_code == 200
    cases = r.json()["payload"]["cases"]
    assert len(cases) == 4
    assert cases[0]["id"] == "TC-0001"
    assert cases[0]["type"] == "functional"

    r = client.post(f"/pipeline/{pid}/approve/test_cases")
    assert r.status_code == 200

    # Release-gate consumes run results as evidence.
    r = client.post(
        f"/pipeline/{pid}/run-stage/release",
        json={"input": {"results": [
            {"id": "TC-0001", "status": "passed", "priority": "P1"},
            {"id": "TC-0002", "status": "failed", "priority": "P1"},
        ]}},
    )
    assert r.status_code == 200
    decision = r.json()["payload"]
    assert decision["verdict"] == "NO_GO"  # 50% fail > 5% threshold


def test_run_stage_unknown_engine_404(client) -> None:
    r = client.post("/projects", params={"name": "x"})
    pid = r.json()["id"]
    r = client.post(f"/pipeline/{pid}/run-stage/doctor", json={"engine": "nope"})
    assert r.status_code == 404


def test_get_pipeline_state(client) -> None:
    r = client.post("/projects", params={"name": "state"})
    pid = r.json()["id"]
    r = client.get(f"/pipeline/{pid}")
    assert r.status_code == 200
    assert r.json()["current_stage"] == "intake"
    assert r.json()["stages"]["doctor"]["state"] == "not_started"


def test_engines_registry_populated(client) -> None:
    r = client.get("/engines")
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()}
    expected = {
        "intake", "requirement-doctor", "test-cases", "codegen", "executor",
        "failure-triage", "visual", "a11y", "api-testing", "etl",
        "release-gate", "leakage", "rag", "agent-security", "prompt-eval", "demo",
    }
    assert expected <= ids
