"""Sandboxed Executor engine (E5).

Absorbs: QA_AI_Solution (execute generated Playwright, collect evidence),
OmnyGO (planner/driver/verifier — the run happens in a real browser), ETL
Buddy (sandboxed execution of generated tests), QAE2E (Docker-isolated run).

Dispatches the suite produced by the CodeGen engine to the runner worker over
HTTP ({RUNNER_URL}/run) and returns the per-test results as evidence for the
triage + release stages. If the runner is unreachable, returns an honest
`runner_unreachable` payload (never faked results).
"""

from __future__ import annotations

import httpx

from ..core.settings import get_settings
from ..pipeline.registry import Engine, register

DEFAULT_TIMEOUT = 200.0


async def _run_suite(ctx: dict, **payload) -> dict:
    settings = get_settings()
    files: list[dict] = payload.get("files", [])
    suite_id: str = str(payload.get("suite_id", "suite"))
    base_url: str = str(payload.get("base_url") or settings.app_base_url)
    runner = str(payload.get("runner_url") or settings.runner_url)

    if not files:
        return {
            "kind": "run_results",
            "payload": {"error": "no suite files to run."},
            "engine": "executor",
        }

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(
                f"{runner.rstrip('/')}/run",
                json={
                    "suiteId": suite_id,
                    "files": files,
                    "baseUrl": base_url,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        return {
            "kind": "run_results",
            "payload": {
                "runner_unreachable": True,
                "runner": runner,
                "error": str(exc),
                "results": [],
            },
            "engine": "executor",
        }

    results = data.get("results") or []
    ok = bool(data.get("ok"))
    # A reachable runner that reports ok=false produced no usable evidence
    # (playwright failed to launch/run). That must stop the chain with the
    # runner's own output — never auto-approve empty results into triage/release.
    if not ok or not results:
        excerpt = (data.get("raw_stdout_excerpt") or "").strip().replace("\n", " ")[-300:]
        reason = excerpt or data.get("error") or "no tests ran"
        return {
            "kind": "run_results",
            "payload": {
                "runner": runner,
                "suite_id": suite_id,
                "error": f"runner returned ok=false with 0 results — {reason}",
                "results": [],
                "raw_stdout_excerpt": excerpt,
            },
            "engine": "executor",
        }

    return {
        "kind": "run_results",
        "payload": {
            "runner": runner,
            "suite_id": suite_id,
            "results": results,
            "ok": ok,
        },
        "engine": "executor",
    }


def register_engines() -> None:
    register(
        Engine(
            id="executor",
            name="Test Runner",
            description="Dispatch the generated suite to the sandboxed "
            "Playwright runner and return per-test evidence.",
            uses_llm=False,
            uses_runner=True,
            run=_run_suite,
        )
    )


register_engines()