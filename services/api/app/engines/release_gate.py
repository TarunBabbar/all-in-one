"""Release Gate engine (E11) — the Release Report.

Pattern source: Mrutyunjay's Release Risk Analysis (configurable criteria ->
GO/NO-GO with stated evidence), QAE2E's IQ judge, AI QA Detective's risk rollup.

Fully deterministic: the verdict, the confidence score and the manual-run queue
are computed from run evidence in local code, never described by a model. The
report is the last thing a release decision should rest on, so it states what
it knows and what it could not resolve.

Confidence is bounded by the eval gates on purpose. A run whose generated code
failed its own coverage gate cannot report high confidence no matter how many
tests happened to pass.
"""

from __future__ import annotations

from ..pipeline.registry import Engine, register


def default_criteria() -> dict:
    return {
        "max_fail_percent": 5.0,
        "min_pass_percent": 90.0,
        "max_high_priority_failures": 0,
        "max_manual_required": 0,
    }


def _confidence(
    *, pass_percent: float, total: int, manual: int, gates_ok: bool, healed: int
) -> dict:
    """Deterministic confidence, with every deduction explained.

    Starts from the pass rate, then subtracts for unresolved tests and for a
    failed gate, and adds a little back when self-healing demonstrably worked
    (a suite that repaired itself is better evidence than one that needed no
    repair only by luck).
    """
    if total == 0:
        return {"score": 0, "rationale": "No tests ran, so there is no evidence to trust."}

    score = pass_percent
    reasons = [f"{pass_percent:.1f}% of tests passed"]

    if manual:
        penalty = min(30.0, manual * 10.0)
        score -= penalty
        reasons.append(f"-{penalty:.0f} for {manual} test(s) unresolved after self-healing")

    if not gates_ok:
        score -= 15.0
        reasons.append("-15 because an eval gate did not pass")

    if healed:
        score += min(5.0, healed * 1.0)
        reasons.append(f"+{min(5.0, float(healed)):.0f} for {healed} auto-repaired locator(s)")

    score = max(0, min(100, round(score)))
    return {"score": score, "rationale": "; ".join(reasons)}


def build_report(
    results: list[dict],
    criteria: dict | None = None,
    *,
    self_heal: dict | None = None,
    gates: list[dict] | None = None,
) -> dict:
    criteria = criteria or default_criteria()
    self_heal = self_heal or {}
    gates = gates or []
    manual = self_heal.get("manual_required") or []

    total = len(results)
    if total == 0:
        return {
            "verdict": "NO_GO",
            "reason": "No test results to judge release on.",
            "criteria": criteria,
            "evidence": {"total": 0},
            "confidence": {"score": 0, "rationale": "No tests ran."},
            "manual_queue": manual,
            "gates": gates,
        }

    passed = sum(1 for r in results if r.get("status") == "passed")
    failed = sum(1 for r in results if r.get("status") == "failed")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    pass_pct = (passed / total) * 100
    fail_pct = (failed / total) * 100

    # High-priority failures weigh heavier (Mrutyunjay pattern).
    high_prio_failures = sum(
        1
        for r in results
        if r.get("status") == "failed" and r.get("priority") in ("P0", "P1")
    )

    gates_ok = all(bool(g.get("passed")) for g in gates) if gates else True
    failed_gates = [g.get("gate") for g in gates if not g.get("passed")]

    checks = {
        "max_fail_percent": fail_pct <= criteria["max_fail_percent"],
        "min_pass_percent": pass_pct >= criteria["min_pass_percent"],
        "max_high_priority_failures": high_prio_failures
        <= criteria["max_high_priority_failures"],
        "max_manual_required": len(manual) <= criteria["max_manual_required"],
        "eval_gates": gates_ok,
    }

    passed_all = all(checks.values())
    failed_checks = [k for k, ok in checks.items() if not ok]
    confidence = _confidence(
        pass_percent=pass_pct,
        total=total,
        manual=len(manual),
        gates_ok=gates_ok,
        healed=len(self_heal.get("auto_fixed") or []),
    )

    if passed_all:
        reason = "All release criteria met."
    elif failed_gates:
        reason = f"Eval gates did not pass: {', '.join(str(g) for g in failed_gates)}."
    elif manual and not checks["max_manual_required"]:
        reason = (
            f"{len(manual)} test(s) could not be automated after self-healing and "
            "need a manual run."
        )
    else:
        reason = f"Release criteria not met: {', '.join(failed_checks)}."

    return {
        "verdict": "GO" if passed_all else "NO_GO",
        "reason": reason,
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
        "self_heal": {
            "attempts": len(self_heal.get("attempts") or []),
            "auto_fixed": len(self_heal.get("auto_fixed") or []),
            "manual_required": len(manual),
        },
        "manual_queue": manual,
        "gates": gates,
        "confidence": confidence,
        "checks": checks,
    }


async def _engine_release(ctx: dict, **payload) -> dict:
    report = build_report(
        payload.get("results", []),
        payload.get("criteria"),
        self_heal=payload.get("self_heal"),
        gates=payload.get("gates"),
    )
    return {"kind": "release_decision", "payload": report, "engine": "release-gate"}


def register_engines() -> None:
    register(
        Engine(
            id="release-gate",
            name="Assess Release",
            description="GO/NO-GO from run evidence, self-heal outcomes and "
            "check results, with a stated confidence and the manual-run queue.",
            uses_llm=False,
            run=_engine_release,
        )
    )


register_engines()
