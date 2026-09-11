"""Eval Gate engine — one implementation, three registrations.

Each gate scores a generated artifact with deterministic metrics and reports
per-metric results. A gate that fails is a first-class pipeline failure: the
stage blocks and the chain stops naming the metric that failed, so the user
fixes the input rather than shipping a weak artifact downstream.

    eval-plan   scores the test plan against the requirement
    eval-cases  scores the case set against the plan and the requirement
    eval-code   scores the generated suite against the cases

The metrics live in `app/eval/` and involve no model, so these stages run in
the normal chain without costing a token and without a network call.

Engine ids are hyphenated (the engine-registry convention), while the gate names
the metric layer uses are underscored (they mirror the stage ids). `GATE_FOR_ENGINE`
is the single place that mapping is written down, so a gate can never be looked
up under a name that has no metrics — a miss that used to make every gate report
"0 metrics" while still passing.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ..eval import build_gate_input, run_gate
from ..pipeline.registry import Engine, register

# engine id -> canonical gate name (see app/eval/metrics.py)
GATE_FOR_ENGINE: dict[str, str] = {
    "eval-plan": "eval_plan",
    "eval-cases": "eval_cases",
    "eval-code": "eval_code",
}

# Which upstream artifacts each gate measures.
_REQUIRES: dict[str, tuple[str, ...]] = {
    "eval_plan": ("requirement", "plan"),
    "eval_cases": ("requirement", "plan", "cases"),
    "eval_code": ("requirement", "plan", "cases", "code"),
}

_TITLES: dict[str, str] = {
    "eval-plan": "Check Plan",
    "eval-cases": "Check Cases",
    "eval-code": "Check Code",
}

# Each gate says what it checks and against what. A shared description would
# leave three stages reading identically in the pipeline.
_DESCRIPTIONS: dict[str, str] = {
    "eval-plan": "Score the test plan against the requirement: does it cover "
    "every stated criterion without inventing scope?",
    "eval-cases": "Score the cases against the plan: is every criterion covered, "
    "and does every case trace back to one?",
    "eval-code": "Score the generated suite: does every automatable case have a "
    "spec, and are the locators grounded?",
}


def _make_runner(engine_id: str) -> Callable[..., Awaitable[dict[str, Any]]]:
    gate = GATE_FOR_ENGINE[engine_id]
    needs = _REQUIRES[gate]

    async def _run(ctx: dict, **payload) -> dict:
        data = build_gate_input(
            gate,
            requirement=str(payload.get("requirement") or payload.get("text") or ""),
            plan=payload.get("plan") or {},
            cases=payload.get("cases") or [],
            code=payload.get("code") or {},
        )
        report = run_gate(gate, data)

        # A gate with nothing to measure is not a pass — say so explicitly
        # rather than reporting a green tick over an empty input.
        digest = report.get("input_digest") or {}
        missing: list[str] = []
        if "plan" in needs and not data.get("plan"):
            missing.append("test plan")
        if "cases" in needs and not data.get("cases"):
            missing.append("test cases")
        if "code" in needs and not digest.get("code_chars"):
            missing.append("generated code")
        if missing:
            report["passed"] = False
            report["summary"]["failed_metrics"] = [f"missing input: {', '.join(missing)}"]

        return {"kind": "eval_report", "payload": report, "engine": engine_id}

    return _run


def register_engines() -> None:
    for engine_id, title in _TITLES.items():
        register(
            Engine(
                id=engine_id,
                name=title,
                description=_DESCRIPTIONS[engine_id],
                uses_llm=False,
                run=_make_runner(engine_id),
            )
        )


register_engines()
