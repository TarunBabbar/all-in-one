"""Pipeline store + engine tests: the requirement→release flow with gates.

Uses the sqlite-backed TestClient fixture from conftest. Store-level tests
run against a fresh AsyncSession bound to the same DATABASE_URL.
"""

from __future__ import annotations

import pytest

from app.db.core import get_session_factory, init_db
from app.pipeline.models import PIPELINE_STAGES, ApprovalState, Artifact, StageId
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
        for stage in [
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
        ]:
            artifact = Artifact(id=f"a-{stage.value}", project_id=project.id, stage=stage,
                                kind=stage.value, payload={"ok": True})
            await store.complete_stage(session, project.id, stage, artifact)
            await store.set_approval(session, project.id, stage, "approve")
        pipeline = await store.get_pipeline(session, project.id)
        assert pipeline.next_pending_stage().value == "release"

    await _run_store(_exercise)


def test_every_generator_has_an_eval_gate() -> None:
    """Each generator stage must be followed by its eval gate."""
    order = [s.value for s in PIPELINE_STAGES]
    for generator, gate in [
        ("test_plan", "eval_plan"),
        ("test_cases", "eval_cases"),
        ("codegen", "eval_code"),
    ]:
        assert gate in order, f"{gate} missing from the pipeline"
        assert order.index(gate) == order.index(generator) + 1, (
            f"{gate} must immediately follow {generator}"
        )


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

    # The plan is what the case generator conforms to.
    r = client.post(
        f"/pipeline/{pid}/run-stage/test_plan",
        json={"input": {"text": "As a user I should be able to search by keyword."}},
    )
    assert r.status_code == 200
    plan = r.json()["payload"]
    assert plan["criteria"], "the plan must declare criteria"

    r = client.post(f"/pipeline/{pid}/run-stage/test_cases",
                    json={"input": {"text": "As a user I should be able to search by keyword.",
                                    "plan": plan}})
    assert r.status_code == 200
    cases = r.json()["payload"]["cases"]

    # The old engine returned a hardcoded four of the same case every time.
    # Cases are now coverage-driven, so the count follows the plan.
    assert len(cases) > 4
    assert len(cases) == len(plan["criteria"]) * 3
    assert cases[0]["id"] == "TC-0001"
    assert cases[0]["type"] == "positive"
    # Every case is traceable to a criterion and covers the core categories.
    assert all(c["criterion_id"] for c in cases)
    assert {c["type"] for c in cases} >= {"positive", "negative", "edge"}

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
    assert decision["confidence"]["score"] < 100


def test_manual_queue_blocks_release(client) -> None:
    """Tests that could not be healed must keep the run from going GO."""
    r = client.post("/projects", params={"name": "manual"})
    pid = r.json()["id"]
    r = client.post(
        f"/pipeline/{pid}/run-stage/release",
        json={
            "input": {
                "results": [{"id": "TC-0001", "status": "passed", "priority": "P1"}],
                "self_heal": {
                    "attempts": [{"attempt": 1, "total": 2, "passed": 1, "failed": 1}],
                    "auto_fixed": [],
                    "manual_required": [{"test": "logout clears the session"}],
                },
            }
        },
    )
    assert r.status_code == 200
    report = r.json()["payload"]
    assert report["verdict"] == "NO_GO"
    assert "manual" in report["reason"].lower()
    assert report["manual_queue"]


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
        "intake", "requirement-doctor", "test-plan", "test-cases", "codegen", "executor",
        "failure-triage", "visual", "a11y", "api-testing", "etl",
        "release-gate", "leakage", "rag", "agent-security", "prompt-eval", "demo",
        "eval-plan", "eval-cases", "eval-code",
    }
    assert expected <= ids
