"""Test Case Generator engine (E3).

This engine previously ignored the model entirely and returned four hardcoded
templates for every requirement, which is why every run produced the same four
cases. It now generates from the approved test plan and is coverage-driven:
every criterion in the plan is covered across the categories that apply to it.

The model proposes; deterministic code then
  - assigns stable ids (TC-0001…),
  - enforces the plan's traceability (each case names its criterion),
  - recomputes the coverage matrix locally rather than trusting the model's,
  - asks once more for any criterion/category pair still missing.

Anything still missing after that is left missing on purpose — the eval gate
is what decides whether the set is good enough, and a silently padded set would
defeat it.
"""

from __future__ import annotations

from ..core.llm import LLMRouter
from ..core.prompts import CASES_SYSTEM, TestCases, cases_prompt
from ..pipeline.registry import Engine, register

CASE_TYPES = ["positive", "negative", "edge", "e2e", "security", "accessibility", "api"]
REQUIRED_TYPES = ["positive", "negative", "edge"]


def _plan_criteria(plan: dict) -> list[dict]:
    out: list[dict] = []
    for i, item in enumerate(plan.get("criteria") or [], start=1):
        if isinstance(item, dict):
            out.append(
                {
                    "id": str(item.get("id") or f"AC-{i:02d}"),
                    "text": str(item.get("text") or ""),
                    "categories": [str(c).lower() for c in (item.get("categories") or [])],
                }
            )
    return out


def _needed_types(criterion: dict) -> list[str]:
    """Categories that must exist for this criterion.

    Always the core three; e2e is added when the plan says the criterion is a
    flow, because a multi-step criterion cannot be proven by single screens.
    """
    need = list(REQUIRED_TYPES)
    if "e2e" in criterion["categories"]:
        need.append("e2e")
    return need


def _template_cases(requirement: str, plan: dict, limit: int) -> list[dict]:
    """Deterministic offline case set, derived from the plan.

    Used by the mock provider and as the no-key fallback. Unlike the old
    template it is generated *from the plan*, so a plan with eight criteria
    yields cases for all eight instead of a fixed four.
    """
    criteria = _plan_criteria(plan)
    if not criteria:
        words = requirement.split()[:6]
        feature = " ".join(words) if words else "the feature"
        criteria = [
            {"id": "AC-01", "text": f"{feature} behaves correctly", "categories": REQUIRED_TYPES}
        ]

    cases: list[dict] = []
    for criterion in criteria:
        for case_type in _needed_types(criterion):
            cases.append(_template_case(criterion, case_type))
            if len(cases) >= limit:
                return cases
    return cases


def _template_case(criterion: dict, case_type: str) -> dict:
    text = criterion["text"]
    shape = {
        "positive": {
            "title": f"{text} — happy path",
            "steps": [
                f"Open the application for: {text}",
                "Perform the action with valid input",
                "Submit",
            ],
            "expected": f"{text} completes successfully",
            "priority": "P1",
            "severity": "high",
        },
        "negative": {
            "title": f"{text} — invalid input rejected",
            "steps": [
                f"Open the application for: {text}",
                "Perform the action with invalid input",
                "Submit",
            ],
            "expected": "A clear error is shown and the application state is unchanged",
            "priority": "P1",
            "severity": "high",
        },
        "edge": {
            "title": f"{text} — boundary values",
            "steps": [
                f"Open the application for: {text}",
                "Drive the input to its minimum and maximum",
                "Submit",
            ],
            "expected": "The application behaves predictably at both boundaries",
            "priority": "P2",
            "severity": "medium",
        },
        "e2e": {
            "title": f"{text} — end to end flow",
            "steps": [
                f"Start the flow for: {text}",
                "Complete every step in order",
                "Confirm the final state",
            ],
            "expected": "The whole flow completes and leaves the expected final state",
            "priority": "P1",
            "severity": "high",
        },
    }
    body = shape.get(case_type, shape["edge"])
    return {
        "criterion_id": criterion["id"],
        "type": case_type,
        "preconditions": ["The application under test is reachable"],
        "automation_rec": "automate",
        "source_evidence": [criterion["id"]],
        **body,
    }


def _coverage(cases: list[dict], criteria: list[dict]) -> dict:
    """Local recompute of the coverage matrix — never the model's self-report."""
    present = {c["type"] for c in cases}
    by_criterion: dict[str, list[str]] = {}
    for case in cases:
        by_criterion.setdefault(case["criterion_id"], []).append(case["type"])

    gaps = []
    for criterion in criteria:
        have = set(by_criterion.get(criterion["id"], []))
        missing = [t for t in _needed_types(criterion) if t not in have]
        if missing:
            gaps.append({"criterion_id": criterion["id"], "missing": missing})

    return {
        "types_present": {t: t in present for t in CASE_TYPES},
        "criteria_total": len(criteria),
        "criteria_covered": len(criteria) - len(gaps),
        "gaps": gaps,
        "complete": not gaps,
    }


def _missing_pairs(cases: list[dict], criteria: list[dict]) -> list[dict]:
    """Criterion/category pairs that still have no case."""
    by_criterion: dict[str, set[str]] = {}
    for case in cases:
        by_criterion.setdefault(case["criterion_id"], set()).add(case["type"])
    out: list[dict] = []
    for criterion in criteria:
        have = by_criterion.get(criterion["id"], set())
        missing = [t for t in _needed_types(criterion) if t not in have]
        if missing:
            out.append({"id": criterion["id"], "text": criterion["text"], "missing": missing})
    return out


def _assign_ids(cases: list[dict]) -> list[dict]:
    """Deterministic stable ids (Sankar contract)."""
    return [{**c, "id": f"TC-{i:04d}"} for i, c in enumerate(cases, start=1)]


async def run_testcases(
    router: LLMRouter, *, text: str, plan: dict | None = None, max_cases: int = 120
) -> dict:
    """Generate a plan-conformant, coverage-driven case set."""
    plan = plan or {}
    criteria = _plan_criteria(plan)
    limit = max(1, max_cases)

    if router.is_mock or not text.strip():
        raw = _template_cases(text, plan, limit)
    else:
        result = await router.complete_json(
            CASES_SYSTEM, cases_prompt(text, plan, limit), TestCases
        )
        raw = [c.model_dump() for c in result.cases]

        # One deterministic follow-up for anything still uncovered. Asking
        # again with the exact gaps is far more reliable than asking the model
        # to self-audit, and it is still the model's own output.
        gaps = _missing_pairs(_normalize(raw, criteria), criteria)
        if gaps and len(raw) < limit:
            follow_up = (
                f"{cases_prompt(text, plan, limit)}\n\n"
                f"These criterion/category pairs are still missing a case. "
                f"Return ONLY cases for them:\n{gaps}"
            )
            try:
                more = await router.complete_json(CASES_SYSTEM, follow_up, TestCases)
                raw.extend(c.model_dump() for c in more.cases)
            except Exception:  # noqa: BLE001 — a failed top-up must not fail the stage
                pass

    cases = _normalize(raw, criteria)[:limit]
    cases = _assign_ids(cases)
    return {
        "cases": cases,
        "count": len(cases),
        "coverage": _coverage(cases, criteria),
        "contract": {
            "id_format": "TC-####",
            "no_invention": True,
            "traceable": True,
            "insufficient_answer": "Insufficient information to determine.",
        },
    }


def _normalize(raw: list, criteria: list[dict]) -> list[dict]:
    """Coerce model output into the shape the gates expect, dropping junk.

    A case without a criterion id is kept but flagged with an empty id, so the
    traceability metric fails honestly instead of the case vanishing.
    """
    valid_ids = {c["id"] for c in criteria}
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        criterion_id = str(item.get("criterion_id") or "")
        if valid_ids and criterion_id not in valid_ids:
            # Keep it — Traceability must be able to see and fail on it.
            criterion_id = criterion_id or ""
        out.append(
            {
                "criterion_id": criterion_id,
                "title": str(item.get("title") or ""),
                "type": str(item.get("type") or "positive").lower(),
                "priority": str(item.get("priority") or "P2"),
                "severity": str(item.get("severity") or "medium"),
                "preconditions": [str(p) for p in (item.get("preconditions") or [])],
                "steps": [str(s) for s in (item.get("steps") or [])],
                "expected": str(item.get("expected") or ""),
                "automation_rec": str(item.get("automation_rec") or "automate").lower(),
                "source_evidence": [str(e) for e in (item.get("source_evidence") or [])],
            }
        )
    return out


async def _engine_testcases(ctx: dict, **payload) -> dict:
    router: LLMRouter = ctx["router"]
    text: str = str(payload.get("text") or "")
    plan: dict = payload.get("plan") or {}
    max_cases: int = int(payload.get("max_cases") or 0)
    if max_cases <= 0:
        from ..core.settings import get_settings

        max_cases = get_settings().max_test_cases
    result = await run_testcases(router, text=text, plan=plan, max_cases=max_cases)
    return {"kind": "test_cases", "payload": result, "engine": "test-cases"}


def register_engines() -> None:
    register(
        Engine(
            id="test-cases",
            name="Test Case Generator",
            description="Generate plan-conformant, traceable test cases "
            "covering every criterion across positive, negative and edge.",
            uses_llm=True,
            run=_engine_testcases,
        )
    )


register_engines()
