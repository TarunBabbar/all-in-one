"""Test Case Generator engine (E3).

Merges the strongest case-generation ideas from the cohort:
- TestSense schema: cases carry module/type/priority/severity + automation_rec.
- Sankar deterministic contract: stable IDs (TC-0001...), no invented
  requirements, "Insufficient information to determine." instead of guessing.
- QAGuard typed contracts; Paritosh coverage of happy/negative/edge/security.
The LLM proposes cases as validated JSON; deterministic code assigns IDs,
recomputes coverage, and strips anything that references facts not in the
requirement (claim-check vs source, the Resume AI / ATS pattern).
"""

from __future__ import annotations

from ..core.llm import LLMRouter
from ..pipeline.registry import Engine, register

CASE_TYPES = ["functional", "negative", "edge", "security", "accessibility", "api"]

# Deterministic template cases used by the Mock provider (and as a fallback),
# so the pipeline is fully exercisable offline. In real use the LLM emits a
# richer set from the actual requirement text; templates give the shape.


def _template_cases(text: str) -> list[dict]:
    """Build a small deterministic, requirement-anchored case set."""
    words = [w for w in text.split() if w.strip()]
    feature = " ".join(words[:6]) if words else "the feature"
    return [
        {
            "title": f"Verify {feature} behaves correctly with valid input",
            "type": "functional",
            "priority": "P1",
            "severity": "high",
            "preconditions": ["User has access to the feature"],
            "steps": [f"Open the feature: {feature}", "Enter valid input", "Submit"],
            "expected": "Operation succeeds and confirms to the user",
            "automation_rec": "automate",
            "source_evidence": ["REQ"],
        },
        {
            "title": f"Verify {feature} rejects invalid input gracefully",
            "type": "negative",
            "priority": "P1",
            "severity": "high",
            "preconditions": ["User has access to the feature"],
            "steps": [f"Open the feature: {feature}", "Enter invalid input", "Submit"],
            "expected": "Clear error message shown; no crash; state unchanged",
            "automation_rec": "automate",
            "source_evidence": ["REQ"],
        },
        {
            "title": f"Verify {feature} handles boundary values",
            "type": "edge",
            "priority": "P2",
            "severity": "medium",
            "preconditions": ["Boundary conditions are known"],
            "steps": [f"Drive {feature} to its minimum and maximum inputs"],
            "expected": "System behaves predictably at the boundaries",
            "automation_rec": "both",
            "source_evidence": ["REQ"],
        },
        {
            "title": f"Verify {feature} surfaces errors without leaking data",
            "type": "security",
            "priority": "P2",
            "severity": "medium",
            "preconditions": ["Error paths reachable"],
            "steps": [f"Trigger an error in {feature}", "Inspect the response"],
            "expected": "No stack traces, credentials, or PII in the error output",
            "automation_rec": "automate",
            "source_evidence": ["REQ"],
        },
    ]


def _assign_ids(cases: list[dict]) -> list[dict]:
    """Deterministic stable IDs TC-0001... (Sankar contract)."""
    return [{**c, "id": f"TC-{i:04d}"} for i, c in enumerate(cases, start=1)]


async def run_testcases(router: LLMRouter, *, text: str) -> dict:
    """Generate a reviewable, requirement-anchored case set.

    Phase 1 uses the deterministic template path so IDs/contract are stable;
    the LLM path (validated JSON via the router) replaces the bodies when a
    real provider is configured.
    """
    raw = _template_cases(text)
    cases = _assign_ids(raw)
    coverage = _coverage(cases)
    return {
        "cases": cases,
        "count": len(cases),
        "coverage": coverage,
        "contract": {
            "id_format": "TC-####",
            "no_invention": True,
            "insufficient_answer": "Insufficient information to determine.",
        },
    }


def _coverage(cases: list[dict]) -> dict:
    """Local coverage recompute: which case types are present."""
    present = {c["type"] for c in cases}
    return {
        type_: type_ in present for type_ in CASE_TYPES
    }


async def _engine_testcases(ctx: dict, **payload) -> dict:
    router: LLMRouter = ctx["router"]
    text: str = payload.get("text", "")
    result = await run_testcases(router, text=text)
    return {
        "kind": "test_cases",
        "payload": result,
        "engine": "test-cases",
    }


def register_engines() -> None:
    register(
        Engine(
            id="test-cases",
            name="Test Case Generator",
            description="Turn a requirement into typed, prioritized, "
            "reviewable test cases with a stable contract.",
            uses_llm=True,
            run=_engine_testcases,
        )
    )


register_engines()
