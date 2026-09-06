"""Release Gate engine (E11).

Pattern source: Mrutyunjay's Release Risk Analysis — configurable decision
criteria (max fail %, min pass %, max high-priority failures) -> GO/NO-GO
with stated evidence. QAE2E's IQ judge and AI QA Detective's risk rollup feed
the same shape. Fully deterministic: the verdict is computed from run
evidence in local code, never by an LLM.
"""

from __future__ import annotations

from ..pipeline.registry import Engine, register


def default_criteria() -> dict:
    return {
        "max_fail_percent": 5.0,
        "min_pass_percent": 90.0,
        "max_high_priority_failures": 0,
    }


def compute_release(results: list[dict], criteria: dict | None = None) -> dict:
    """Given per-test results [{status: passed|failed|skipped, priority}],
    apply the criteria and produce a GO/NO-GO with evidence."""
    criteria = criteria or default_criteria()
    total = len(results)
    if total == 0:
        return {
            "verdict": "NO_GO",
            "reason": "No test results to judge release on.",
            "criteria": criteria,
            "evidence": {"total": 0},
        }

    passed = sum(1 for r in results if r.get("status") == "passed")
    failed = sum(1 for r in results if r.get("status") == "failed")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    pass_pct = (passed / total) * 100
    fail_pct = (failed / total) * 100

    # High-priority failures (P0/P1) are weighted heavier (Mrutyunjay pattern).
    high_prio_failures = sum(
        1
        for r in results
        if r.get("status") == "failed" and r.get("priority") in ("P0", "P1")
    )

    checks = {
        "max_fail_percent": fail_pct <= criteria["max_fail_percent"],
        "min_pass_percent": pass_pct >= criteria["min_pass_percent"],
        "max_high_priority_failures": high_prio_failures
        <= criteria["max_high_priority_failures"],
    }

    passed_all = all(checks.values())
    verdict = "GO" if passed_all else "NO_GO"
    failed_checks = [k for k, ok in checks.items() if not ok]

    return {
        "verdict": verdict,
        "reason": (
            "All release criteria met."
            if passed_all
            else f"Release criteria not met: {', '.join(failed_checks)}."
        ),
        "criteria": criteria,
        "evidence": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "pass_percent": round(pass_pct, 1),
            "fail_percent": round(fail_pct, 1),
            "high_priority_failures": high_prio_failures,
        },
        "checks": checks,
    }


async def _engine_release(ctx: dict, **payload) -> dict:
    results: list[dict] = payload.get("results", [])
    criteria = payload.get("criteria")
    decision = compute_release(results, criteria)
    return {
        "kind": "release_decision",
        "payload": decision,
        "engine": "release-gate",
    }


def register_engines() -> None:
    register(
        Engine(
            id="release-gate",
            name="Release Gate",
            description="GO/NO-GO release decision from run evidence, "
            "with configurable criteria.",
            uses_llm=False,
            run=_engine_release,
        )
    )


register_engines()
