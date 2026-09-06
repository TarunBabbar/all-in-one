"""Demo data engine — seeds sample run results for offline pipeline demos.

Pattern from AI QA Detective (31 seeded demo scenarios) and ETL Buddy's
seeded defect DB: honest, clearly-flagged demo fixtures so every engine is
exercisable without a live browser or LLM key. Never masquerades as a real
run (the payload is labeled `demo: true`).
"""

from __future__ import annotations

from ..pipeline.registry import Engine, register

DEMO_RESULTS = [
    {"id": "TC-0001", "title": "Valid input submits", "status": "passed", "priority": "P1"},
    {"id": "TC-0002", "title": "Invalid input rejected", "status": "passed", "priority": "P1"},
    {"id": "TC-0003", "title": "Boundary handling", "status": "passed", "priority": "P2"},
    {"id": "TC-0004", "title": "Error path no data leak", "status": "passed", "priority": "P2"},
    {"id": "TC-0005", "title": "Empty state renders", "status": "failed", "priority": "P1"},
    {"id": "TC-0006", "title": "Concurrent sessions", "status": "passed", "priority": "P2"},
]

DEMO_REQUIREMENT = (
    "As a user, I should be able to search for products by keyword and filter "
    "the results by category and price range. When no results match, the app "
    "must show an empty state with a clear message and a reset-filters button. "
    "Search must handle special characters and invalid input without errors."
)


async def _engine_demo(ctx: dict, **payload) -> dict:
    which = payload.get("which", "run_results")
    if which == "requirement":
        return {"kind": "requirement", "payload": {"text": DEMO_REQUIREMENT}, "engine": "demo"}
    # default: run results
    return {
        "kind": "run_results",
        "payload": {"demo": True, "results": DEMO_RESULTS},
        "engine": "demo",
    }


def register_engines() -> None:
    register(
        Engine(
            id="demo",
            name="Demo Data",
            description="Seed sample requirement / run results for offline demos.",
            uses_llm=False,
            run=_engine_demo,
        )
    )


register_engines()
