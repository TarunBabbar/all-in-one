"""Runs a gate's metrics and produces the stored eval report.

The report is the artifact the pipeline stores for an `eval_*` stage, and it
is deliberately shaped for a human: a pass/fail per metric, the threshold it
was measured against, and a reason sentence naming what went wrong.
"""

from __future__ import annotations

from typing import Any

from .extract import flatten, plan_criteria, split_requirement_criteria
from .metrics import DEEPEVAL_AVAILABLE, MetricResult, build_test_case, gates, metrics_for


def build_gate_input(
    gate: str,
    *,
    requirement: str = "",
    plan: dict | None = None,
    cases: list | None = None,
    code: dict | None = None,
) -> dict[str, Any]:
    """Assemble the structured payload a gate's metrics read.

    Derived fields (`stated_criteria`) are computed here rather than by the
    model, so the yardstick a gate measures against is always the requirement
    itself — not the model's summary of it.
    """
    plan = plan or {}
    data: dict[str, Any] = {
        "gate": gate,
        "requirement": requirement,
        "plan": plan,
        "cases": cases or [],
        "code": code or {},
    }
    if gate == "eval_plan":
        data["stated_criteria"] = split_requirement_criteria(requirement)
        data["vague_criteria"] = [str(v) for v in (plan.get("ambiguous") or [])]
        data["assumptions"] = [str(a) for a in (plan.get("assumptions") or [])]
    if gate == "eval_cases":
        # Ground the case gate in the plan's own criteria list.
        data["stated_criteria"] = [c["text"] for c in plan_criteria(plan)]
    if gate == "eval_code":
        data["stated_criteria"] = [c["text"] for c in plan_criteria(plan)]
    return data


def run_gate(gate: str, data: dict[str, Any]) -> dict[str, Any]:
    """Measure every metric for `gate` and return the stored report.

    Synchronous by design: every metric is pure Python, so there is nothing to
    await. `a_measure` still exists on each metric for deepeval's async runner.
    """
    test_case = build_test_case(gate, data)
    results: list[MetricResult] = []
    for metric in metrics_for(gate):
        try:
            metric.measure(test_case)
            results.append(metric.result())
        except Exception as exc:  # noqa: BLE001 — a broken metric must not pass
            results.append(
                MetricResult(
                    name=type(metric).__name__.removesuffix("Metric"),
                    score=0.0,
                    threshold=metric.threshold,
                    passed=False,
                    reason=f"metric raised: {exc}",
                )
            )

    passed_count = sum(1 for r in results if r.passed)
    failed_names = [r.name for r in results if not r.passed]
    total = len(results)

    return {
        "gate": gate,
        "passed": passed_count == total,
        "summary": {
            "passed": passed_count,
            "failed": total - passed_count,
            "total": total,
            "failed_metrics": failed_names,
        },
        "metrics": [r.model_dump() for r in results],
        "engine": "deepeval-custom" if DEEPEVAL_AVAILABLE else "deepeval-shim",
        "input_digest": {
            "requirement_words": len(str(data.get("requirement") or "").split()),
            "criteria": len(data.get("stated_criteria") or []),
            "cases": len(data.get("cases") or []),
            "code_chars": len(flatten(data.get("code") or {})),
        },
    }


def failure_message(report: dict) -> str:
    """One line naming what failed, used by the chain's stop reason."""
    summary = report.get("summary") or {}
    names = summary.get("failed_metrics") or []
    if not names:
        return f"{report.get('gate')} gate failed"
    return f"{report.get('gate')} gate failed on: {', '.join(names)}"


def all_gates() -> list[str]:
    return gates()
