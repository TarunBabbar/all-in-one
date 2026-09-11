"""Test Plan engine (E2b).

Sits between the requirement and case generation. The plan is what the case
gate measures against, so it must be explicit and traceable: a list of criteria
in the requirement's own terms, the categories that apply to each, and any
assumption made where the requirement is silent.

Design note: the plan states criteria, and `app/eval/extract.py` derives the
*requirement's* criteria independently from the raw text. The eval gate compares
the two, so the model cannot satisfy the gate by redefining the requirement.
"""

from __future__ import annotations

from ..core.llm import LLMRouter
from ..core.prompts import PLAN_SYSTEM, TestPlan, plan_prompt
from ..pipeline.registry import Engine, register


def _summarize(plan: dict) -> dict:
    criteria = plan.get("criteria") or []
    by_category: dict[str, int] = {}
    for item in criteria:
        for cat in item.get("categories") or []:
            by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "total_criteria": len(criteria),
        "by_category": by_category,
        "assumptions": len(plan.get("assumptions") or []),
        "ambiguous": len(plan.get("ambiguous") or []),
    }


async def _test_plan(ctx: dict, **payload) -> dict:
    router: LLMRouter = ctx["router"]
    requirement: str = str(payload.get("text") or "")

    if router.is_mock or not requirement.strip():
        # Offline/demo path: a deterministic plan so the chain stays runnable
        # without keys. The eval gate still scores it honestly.
        plan = TestPlan._mock_example().model_dump()
    else:
        result = await router.complete_json(PLAN_SYSTEM, plan_prompt(requirement), TestPlan)
        plan = result.model_dump()

    return {
        "kind": "test_plan",
        "payload": {**plan, "summary": _summarize(plan)},
        "engine": "test-plan",
    }


def register_engines() -> None:
    register(
        Engine(
            id="test-plan",
            name="Test Plan",
            description="Turn a requirement into testable criteria with a "
            "category matrix the case generator must conform to.",
            uses_llm=True,
            run=_test_plan,
        )
    )


register_engines()
