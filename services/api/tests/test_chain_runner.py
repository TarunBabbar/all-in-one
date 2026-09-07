"""Automatic chain runner tests: auto-advance, failure stop, and resume.

Exercise the background chain logic directly (no HTTP) against the isolated
sqlite DB from conftest with the mock LLM. The run stage's executor hits the
runner over HTTP, so the tests point it at a closed port to force a
deterministic runner_unreachable failure.
"""

from __future__ import annotations

import asyncio

import pytest

from app.db.core import get_session_factory, init_db
from app.pipeline import runner as chain_runner
from app.pipeline.chain import detect_target_url, resolve_stage_inputs
from app.pipeline.models import StageId
from app.pipeline.store import PipelineStore

REQ = (
    "As a user I should be able to search products by keyword and filter by "
    "category. Search must handle invalid input without errors."
)


async def _new_project(name: str) -> str:
    await init_db()
    store = PipelineStore()
    async with get_session_factory()() as session:
        project = await store.create_project(session, name)
        return project.id


async def _wait_done(pid: str, timeout: float = 20.0) -> None:
    waited = 0.0
    while chain_runner.is_running(pid) and waited < timeout:
        await asyncio.sleep(0.1)
        waited += 0.1


async def _stage_states(pid: str) -> dict[str, str]:
    store = PipelineStore()
    async with get_session_factory()() as session:
        pipeline = await store.get_pipeline(session, pid)
        return {s.value: r.state.value for s, r in pipeline.stage_runs.items()}


async def _events(pid: str) -> list[dict]:
    store = PipelineStore()
    async with get_session_factory()() as session:
        return await store.list_events(session, pid)


@pytest.mark.asyncio
async def test_chain_auto_advances_and_blocks_on_runner_failure() -> None:
    pid = await _new_project("chain-fail")
    # Point the runner override at a port nothing listens on so the run stage
    # fails deterministically (runner_unreachable), stopping the chain there.
    chain_runner.launch_chain(
        pid,
        requirement=REQ,
        overrides={"run": {"runner_url": "http://127.0.0.1:1"}},
    )
    await _wait_done(pid)

    states = await _stage_states(pid)
    assert states["intake"] == "approved"
    assert states["doctor"] == "approved"
    assert states["test_cases"] == "approved"
    assert states["codegen"] == "approved"
    assert states["run"] == "blocked"
    assert "triage" not in states  # downstream never ran
    assert "release" not in states

    evs = await _events(pid)
    assert any(e["level"] == "error" and e["stage"] == "run" for e in evs)


@pytest.mark.asyncio
async def test_chain_resume_from_blocked_stage() -> None:
    pid = await _new_project("chain-resume")
    chain_runner.launch_chain(
        pid,
        requirement=REQ,
        overrides={"run": {"runner_url": "http://127.0.0.1:1"}},
    )
    await _wait_done(pid)
    states = await _stage_states(pid)
    assert states["run"] == "blocked"

    # Resume from the blocked stage with an edited (still closed) runner URL.
    # Earlier stages stay approved; the run stage re-executes and stops again,
    # proving the resume path starts exactly at the blocked stage.
    chain_runner.launch_chain(
        pid,
        start_stage=StageId.RUN,
        overrides={"run": {"runner_url": "http://127.0.0.1:2"}},
    )
    await _wait_done(pid)

    states = await _stage_states(pid)
    assert states["intake"] == "approved"
    assert states["doctor"] == "approved"
    assert states["codegen"] == "approved"
    assert states["run"] == "blocked"
    assert "triage" not in states


@pytest.mark.asyncio
async def test_chain_start_inputs_persisted() -> None:
    """Project inputs (requirement) persist so status reloads + resume work."""
    pid = await _new_project("chain-inputs")
    chain_runner.launch_chain(
        pid,
        requirement=REQ,
        overrides={"run": {"runner_url": "http://127.0.0.1:1"}},
    )
    await _wait_done(pid)

    store = PipelineStore()
    async with get_session_factory()() as session:
        pipeline = await store.get_pipeline(session, pid)
        assert pipeline.inputs["requirement"] == REQ
        assert "overrides" in pipeline.inputs

    states = await _stage_states(pid)
    assert states["intake"] == "approved"
    assert states["doctor"] == "approved"


@pytest.mark.asyncio
async def test_detect_target_url() -> None:
    assert detect_target_url("Test login at https://www.saucedemo.com please") == "https://www.saucedemo.com"
    assert detect_target_url("url: http://localhost:3000 do the thing") == "http://localhost:3000"
    assert detect_target_url("No url in here") == ""
    assert detect_target_url("") == ""


@pytest.mark.asyncio
async def test_resolver_uses_requirement_url_over_env() -> None:
    """A URL in the requirement (stored as inputs.app_url) wins over env default."""
    inputs = {
        "requirement": "Test the checkout at https://shop.example.com",
        "app_url": "https://shop.example.com",
    }
    # codegen should receive the requirement-derived URL as its base_url.
    codegen_inputs = resolve_stage_inputs(
        stage=StageId.CODEGEN,
        artifacts={},
        inputs=inputs,
    )
    assert codegen_inputs["base_url"] == "https://shop.example.com"

    # run should receive it too, plus the configured runner URL.
    run_inputs = resolve_stage_inputs(
        stage=StageId.RUN,
        artifacts={},
        inputs=inputs,
    )
    assert run_inputs["base_url"] == "https://shop.example.com"
    assert run_inputs["files"] == []
