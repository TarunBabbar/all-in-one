"""Deterministic eval metrics on DeepEval's BaseMetric contract.

Why these are not LLM-judged
----------------------------
An eval gate has to be able to *fail*, reproducibly, for a reason a human can
read. A judge model gives neither. Every metric below is pure Python over the
stored artifacts: same inputs, same score, every time, no network. That is also
what lets the whole pipeline (gates included) run under LLM_PROVIDER=mock.

When `deepeval` is importable we inherit its real BaseMetric, so these metrics
work inside deepeval's own ecosystem (assert_test, caching, CI). When it is not
installed yet, a local shim with the identical contract takes over so the API
still boots — the scoring is ours either way, so behaviour does not change.

The contract, per deepeval's docs:
    __init__(threshold)            -> no evaluation_model, no reason model
    measure(test_case) -> float    -> sets self.score and self.success
    is_successful() -> bool
    __name__                       -> metric name

Scores are 0..1 and higher-is-better (deepeval >= 4.2.2).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

try:  # pragma: no cover - exercised by whichever branch the env has
    from deepeval.metrics import BaseMetric
    from deepeval.test_case import LLMTestCase

    DEEPEVAL_AVAILABLE = True
except ImportError:  # pragma: no cover
    DEEPEVAL_AVAILABLE = False

    class LLMTestCase:  # type: ignore[no-redef]
        """Minimal stand-in carrying the same fields our metrics read."""

        def __init__(
            self,
            *,
            input: str = "",
            actual_output: str = "",
            expected_output: str = "",
            context: list[str] | None = None,
        ) -> None:
            self.input = input
            self.actual_output = actual_output
            self.expected_output = expected_output
            self.context = context or []

    class BaseMetric:  # type: ignore[no-redef]
        """Minimal stand-in for deepeval's BaseMetric."""

        threshold: float = 0.5
        score: float = 0.0
        success: bool = False
        reason: str = ""
        error: str | None = None
        async_mode: bool = False
        include_reason: bool = False
        evaluation_model: str | None = None


from .extract import (  # noqa: E402  (import after the shim is defined)
    case_ids_in_source,
    case_records,
    coverage,
    flatten,
    is_multi_step,
    plan_criteria,
    s,
    spec_files,
    ungrounded_claims,
)

REQUIRED_CATEGORIES = ("positive", "negative", "edge")


class MetricResult(BaseModel):
    """One metric's outcome, as stored in the eval-gate artifact."""

    name: str
    score: float = Field(ge=0.0, le=1.0)
    threshold: float
    passed: bool
    reason: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class QAMetric(BaseMetric):
    """Shared scaffolding: score/evidence plumbing and the sync/async bridge."""

    gate: str = ""

    def __init__(self, threshold: float = 1.0) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.success = False
        self.reason = ""
        self.error = None
        # Non-LLM metrics need neither a reason model nor async scheduling.
        self.include_reason = False
        self.evaluation_model = None
        self.async_mode = False
        self.evidence: list[dict[str, Any]] = []

    # -- deepeval contract ------------------------------------------------- #

    def measure(self, test_case: LLMTestCase) -> float:  # pragma: no cover - overridden
        raise NotImplementedError

    async def a_measure(self, test_case: LLMTestCase) -> float:
        # Scoring is synchronous and cheap; reuse it rather than duplicating.
        return self.measure(test_case)

    def is_successful(self) -> bool:
        if self.error is not None:
            self.success = False
        else:
            try:
                self.success = self.score >= self.threshold
            except TypeError:
                self.success = False
        return self.success

    @property
    def __name__(self) -> str:
        return type(self).__name__.removesuffix("Metric")

    # -- helpers ----------------------------------------------------------- #

    def _finish(self, score: float, reason: str, evidence: list[dict] | None = None) -> float:
        self.score = max(0.0, min(1.0, round(score, 4)))
        self.reason = reason
        self.evidence = evidence or []
        self.is_successful()
        return self.score

    def _ratio(self, good: int, total: int, zero_case: str, ok_case: str) -> tuple[float, str]:
        """Score a count-of-things metric, with an explicit empty-state.

        An empty input is NOT automatically a pass — the caller must say what
        it means, because "nothing to check" silently scoring 1.0 is exactly
        how a broken gate hides.
        """
        if total <= 0:
            return 1.0, zero_case
        return good / total, f"{good}/{total} {ok_case}"

    def result(self) -> MetricResult:
        return MetricResult(
            name=self.__name__,
            score=self.score,
            threshold=self.threshold,
            passed=bool(self.success),
            reason=self.reason,
            evidence=self.evidence[:20],
        )


def payload_of(test_case: LLMTestCase) -> dict:
    """Parse the structured context the harness attached."""
    for chunk in test_case.context or []:
        try:
            data = json.loads(chunk)
        except (TypeError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return {}


# --------------------------------------------------------------------------- #
# Gate 1 — Test Plan
# --------------------------------------------------------------------------- #

class CriteriaCoverageMetric(QAMetric):
    """Every criterion the requirement states must appear in the plan."""

    gate = "eval_plan"

    def __init__(self, threshold: float = 1.0) -> None:
        super().__init__(threshold)

    def measure(self, test_case: LLMTestCase) -> float:
        data = payload_of(test_case)
        stated = data.get("stated_criteria") or []
        plan = data.get("plan") or {}
        plan_text = flatten(plan)
        found, missing = coverage(list(stated), plan_text)
        score, _ = self._ratio(
            found,
            len(stated),
            "the requirement states no acceptance criteria to cover",
            "requirement criteria present in the plan",
        )
        evidence = [{"criterion": m} for m in missing[:10]]
        reason = (
            f"{len(missing)} stated criteria have no plan item: "
            + "; ".join(m[:70] for m in missing[:4])
            if missing
            else f"all {len(stated)} stated criteria are covered"
        )
        return self._finish(score, reason, evidence)


class PlanNoInventionMetric(QAMetric):
    """Plan items must trace back to the requirement, not be invented."""

    gate = "eval_plan"

    def __init__(self, threshold: float = 0.9) -> None:
        super().__init__(threshold)

    def measure(self, test_case: LLMTestCase) -> float:
        data = payload_of(test_case)
        criteria = plan_criteria(data.get("plan") or {})
        source = s(data.get("requirement"))
        ungrounded: list[str] = []
        for crit in criteria:
            if ungrounded_claims([crit["text"]], source):
                ungrounded.append(crit["id"])
        score, _ = self._ratio(
            len(criteria) - len(ungrounded),
            len(criteria),
            "the plan declares no criteria",
            "plan items are grounded in the requirement",
        )
        reason = (
            f"{len(ungrounded)} plan items cite nothing in the requirement: "
            + ", ".join(ungrounded[:6])
            if ungrounded
            else "every plan item traces to the requirement"
        )
        return self._finish(score, reason, [{"criterion_id": c} for c in ungrounded[:10]])


class CategoryMatrixCompleteMetric(QAMetric):
    """Each criterion must declare positive, negative and edge coverage."""

    gate = "eval_plan"

    def __init__(self, threshold: float = 1.0) -> None:
        super().__init__(threshold)

    def measure(self, test_case: LLMTestCase) -> float:
        data = payload_of(test_case)
        criteria = plan_criteria(data.get("plan") or {})
        thin: list[dict] = []
        for crit in criteria:
            need = set(REQUIRED_CATEGORIES)
            if is_multi_step(crit["text"]):
                need.add("e2e")
            have = set(crit["categories"])
            missing = sorted(need - have)
            if missing:
                thin.append({"criterion_id": crit["id"], "missing": missing})
        score, _ = self._ratio(
            len(criteria) - len(thin),
            len(criteria),
            "the plan declares no criteria",
            "criteria declare a complete category matrix",
        )
        reason = (
            f"{len(thin)} criteria are missing categories: "
            + ", ".join(f"{t['criterion_id']}({','.join(t['missing'])})" for t in thin[:4])
            if thin
            else "every criterion declares positive, negative, edge (and e2e where multi-step)"
        )
        return self._finish(score, reason, thin[:10])


class AmbiguityFlaggedMetric(QAMetric):
    """Vague criteria must carry an explicit, testable assumption."""

    gate = "eval_plan"

    def __init__(self, threshold: float = 0.8) -> None:
        super().__init__(threshold)

    def measure(self, test_case: LLMTestCase) -> float:
        data = payload_of(test_case)
        vague = [s(v) for v in (data.get("vague_criteria") or [])]
        assumptions = [s(a) for a in (data.get("assumptions") or [])]
        if not vague:
            return self._finish(1.0, "the requirement states nothing ambiguous")
        assumed_text = flatten(assumptions)
        flagged = 0
        unflagged: list[str] = []
        for item in vague:
            found, missing = coverage([item], assumed_text, ratio=0.4)
            if found and not missing:
                flagged += 1
            else:
                unflagged.append(item)
        score = flagged / len(vague)
        reason = (
            f"{len(unflagged)} ambiguous statements carry no assumption: "
            + "; ".join(u[:60] for u in unflagged[:3])
            if unflagged
            else f"all {len(vague)} ambiguous statements carry a stated assumption"
        )
        return self._finish(score, reason, [{"ambiguous": u} for u in unflagged[:10]])


# --------------------------------------------------------------------------- #
# Gate 2 — Test Cases vs the plan
# --------------------------------------------------------------------------- #

class PlanConformanceMetric(QAMetric):
    """Both directions: every plan item covered, every case traceable."""

    gate = "eval_cases"

    def __init__(self, threshold: float = 1.0) -> None:
        super().__init__(threshold)

    def measure(self, test_case: LLMTestCase) -> float:
        data = payload_of(test_case)
        criteria = plan_criteria(data.get("plan") or {})
        cases = case_records(data.get("cases") or [])
        plan_ids = {c["id"] for c in criteria}
        covered = {c["criterion_id"] for c in cases if c["criterion_id"]}

        uncovered = sorted(plan_ids - covered)
        orphaned = sorted({c["id"] for c in cases if c["criterion_id"] not in plan_ids})

        total = len(plan_ids) + len(cases)
        bad = len(uncovered) + len(orphaned)
        score = 1.0 if total == 0 else (total - bad) / total
        score = max(0.0, min(1.0, score))

        parts: list[str] = []
        if uncovered:
            parts.append(f"{len(uncovered)} plan items have no case ({', '.join(uncovered[:4])})")
        if orphaned:
            parts.append(f"{len(orphaned)} cases map to no plan item ({', '.join(orphaned[:4])})")
        reason = (
            "; ".join(parts)
            if parts
            else "every plan item has cases and every case is traceable"
        )
        evidence = [{"criterion_id": c} for c in uncovered[:10]] + [
            {"case_id": c} for c in orphaned[:10]
        ]
        return self._finish(score, reason, evidence)


class CategoryBalanceMetric(QAMetric):
    """Per criterion, the required case categories must actually exist."""

    gate = "eval_cases"

    def __init__(self, threshold: float = 1.0) -> None:
        super().__init__(threshold)

    def measure(self, test_case: LLMTestCase) -> float:
        data = payload_of(test_case)
        criteria = plan_criteria(data.get("plan") or {})
        cases = case_records(data.get("cases") or [])
        by_criterion: dict[str, set[str]] = {}
        for case in cases:
            by_criterion.setdefault(case["criterion_id"], set()).add(case["type"])

        gaps: list[dict] = []
        for crit in criteria:
            need = set(REQUIRED_CATEGORIES)
            if is_multi_step(crit["text"]):
                need.add("e2e")
            have = by_criterion.get(crit["id"], set())
            missing = sorted(need - have)
            if missing:
                gaps.append({"criterion_id": crit["id"], "missing": missing})

        score, _ = self._ratio(
            len(criteria) - len(gaps),
            len(criteria),
            "the plan declares no criteria",
            "criteria have balanced case categories",
        )
        reason = (
            f"{len(gaps)} criteria lack coverage types: "
            + ", ".join(f"{g['criterion_id']}({','.join(g['missing'])})" for g in gaps[:4])
            if gaps
            else "every criterion has positive, negative and edge cases (e2e where multi-step)"
        )
        return self._finish(score, reason, gaps[:10])


class CaseNoInventionMetric(QAMetric):
    """Case content must come from the requirement or the plan."""

    gate = "eval_cases"

    def __init__(self, threshold: float = 0.9) -> None:
        super().__init__(threshold)

    def measure(self, test_case: LLMTestCase) -> float:
        data = payload_of(test_case)
        cases = case_records(data.get("cases") or [])
        source = f"{s(data.get('requirement'))} {flatten(data.get('plan') or {})}"
        invented: list[dict] = []
        for case in cases:
            claims = list(case["steps"]) + [case["expected"]] + list(case["preconditions"])
            bad = ungrounded_claims([c for c in claims if c.strip()], source)
            if bad:
                invented.append({"case_id": case["id"], "unverified": bad[:2]})
        score, _ = self._ratio(
            len(cases) - len(invented),
            len(cases),
            "no cases to check",
            "cases are grounded in the requirement or plan",
        )
        reason = (
            f"{len(invented)} cases contain steps with no basis in the source: "
            + ", ".join(i["case_id"] for i in invented[:5])
            if invented
            else "every case step traces to the requirement or plan"
        )
        return self._finish(score, reason, invented[:10])


class TraceabilityMetric(QAMetric):
    """Every case must carry a criterion id that exists in the plan."""

    gate = "eval_cases"

    def __init__(self, threshold: float = 1.0) -> None:
        super().__init__(threshold)

    def measure(self, test_case: LLMTestCase) -> float:
        data = payload_of(test_case)
        criteria = {c["id"] for c in plan_criteria(data.get("plan") or {})}
        cases = case_records(data.get("cases") or [])
        bad = [
            {"case_id": c["id"], "criterion_id": c["criterion_id"] or None}
            for c in cases
            if c["criterion_id"] not in criteria
        ]
        score, _ = self._ratio(
            len(cases) - len(bad),
            len(cases),
            "no cases to check",
            "cases carry a valid criterion id",
        )
        reason = (
            f"{len(bad)} cases reference a criterion that is not in the plan"
            if bad
            else f"all {len(cases)} cases are traceable to a plan criterion"
        )
        return self._finish(score, reason, bad[:10])


class StepCompletenessMetric(QAMetric):
    """A case without preconditions, steps and an expectation is not runnable."""

    gate = "eval_cases"

    def __init__(self, threshold: float = 1.0) -> None:
        super().__init__(threshold)

    def measure(self, test_case: LLMTestCase) -> float:
        data = payload_of(test_case)
        cases = case_records(data.get("cases") or [])
        incomplete: list[dict] = []
        for case in cases:
            missing: list[str] = []
            if not case["preconditions"]:
                missing.append("preconditions")
            if len(case["steps"]) < 2:
                missing.append("steps")
            if not case["expected"].strip():
                missing.append("expected")
            if missing:
                incomplete.append({"case_id": case["id"], "missing": missing})
        score, _ = self._ratio(
            len(cases) - len(incomplete),
            len(cases),
            "no cases to check",
            "cases are complete",
        )
        reason = (
            f"{len(incomplete)} cases are missing required fields: "
            + ", ".join(f"{i['case_id']}({','.join(i['missing'])})" for i in incomplete[:4])
            if incomplete
            else f"all {len(cases)} cases have preconditions, steps and an expectation"
        )
        return self._finish(score, reason, incomplete[:10])


# --------------------------------------------------------------------------- #
# Gate 3 — Generated code
# --------------------------------------------------------------------------- #

class CaseCoverageMetric(QAMetric):
    """Every automatable case must have a spec that references it."""

    gate = "eval_code"

    def __init__(self, threshold: float = 1.0) -> None:
        super().__init__(threshold)

    def measure(self, test_case: LLMTestCase) -> float:
        data = payload_of(test_case)
        cases = case_records(data.get("cases") or [])
        automatable = [c for c in cases if c["automation_rec"] in ("automate", "both", "")]
        sources = spec_files(data.get("code") or {})
        referenced: set[str] = set()
        for src in sources.values():
            referenced |= case_ids_in_source(src)
        missing = [c["id"] for c in automatable if c["id"] not in referenced]
        score, _ = self._ratio(
            len(automatable) - len(missing),
            len(automatable),
            "no automatable cases requested",
            "automatable cases have generated specs",
        )
        reason = (
            f"{len(missing)} automatable cases have no spec: {', '.join(missing[:6])}"
            if missing
            else f"all {len(automatable)} automatable cases are covered by a spec"
        )
        return self._finish(score, reason, [{"case_id": m} for m in missing[:10]])


class GroundingTierMetric(QAMetric):
    """Locators should be verified against a DOM, not guessed."""

    gate = "eval_code"

    def __init__(self, threshold: float = 0.8) -> None:
        super().__init__(threshold)

    def measure(self, test_case: LLMTestCase) -> float:
        data = payload_of(test_case)
        code = data.get("code") or {}
        report = code.get("grounding_report") or {}
        counts = report.get("counts") or {}
        total = sum(v for v in counts.values() if isinstance(v, int))
        if total <= 0:
            return self._finish(
                0.0,
                "no grounding report was produced, so locator quality is unknown",
                [{"reason": "missing grounding_report"}],
            )
        verified = sum(
            v for k, v in counts.items()
            if k in ("dom_verified", "run_verified") and isinstance(v, int)
        )
        score = verified / total
        unverified = total - verified
        reason = (
            f"{unverified}/{total} locators are unverified guesses"
            if unverified
            else f"all {total} locators are DOM- or run-verified"
        )
        return self._finish(score, reason, [{"unverified_locators": unverified, "total": total}])


class RunnableStructureMetric(QAMetric):
    """The suite must be a complete scaffold, not fragments or stubs."""

    gate = "eval_code"

    REQUIRED = ("package.json", "playwright.config", "base.page")

    def __init__(self, threshold: float = 1.0) -> None:
        super().__init__(threshold)

    def measure(self, test_case: LLMTestCase) -> float:
        data = payload_of(test_case)
        sources = spec_files(data.get("code") or {})
        if not sources:
            return self._finish(0.0, "no files were generated", [{"reason": "empty bundle"}])

        missing = [r for r in self.REQUIRED if not any(r in p for p in sources)]
        stubs = [p for p, src in sources.items() if "TODO" in src or "FIXME" in src]
        specs = [p for p in sources if p.endswith(".spec.ts")]
        spec_ok = [p for p in specs if "test(" in sources[p]]

        checks: list[tuple[str, bool]] = [
            ("scaffold files", not missing),
            ("no TODO stubs", not stubs),
            ("specs declare tests", len(spec_ok) == len(specs) if specs else False),
        ]
        passed = sum(1 for _, ok in checks if ok)
        score = passed / len(checks) if checks else 0.0

        parts: list[str] = []
        if missing:
            parts.append(f"missing scaffold: {', '.join(missing)}")
        if stubs:
            parts.append(f"{len(stubs)} files contain TODO/FIXME stubs")
        if specs and len(spec_ok) != len(specs):
            parts.append(f"{len(specs) - len(spec_ok)} spec files declare no test()")
        reason = "; ".join(parts) if parts else "the suite is a complete, runnable scaffold"
        evidence = [{"missing": missing}, {"stubs": stubs[:5]}]
        return self._finish(score, reason, evidence)


class SpecMappingMetric(QAMetric):
    """One automatable case should map to exactly one generated spec."""

    gate = "eval_code"

    def __init__(self, threshold: float = 0.9) -> None:
        super().__init__(threshold)

    def measure(self, test_case: LLMTestCase) -> float:
        data = payload_of(test_case)
        cases = case_records(data.get("cases") or [])
        automatable = {c["id"] for c in cases if c["automation_rec"] in ("automate", "both", "")}
        if not automatable:
            return self._finish(1.0, "no automatable cases to map")

        appearances: dict[str, int] = {cid: 0 for cid in automatable}
        for src in spec_files(data.get("code") or {}).values():
            for cid in case_ids_in_source(src):
                if cid in appearances:
                    appearances[cid] += 1

        good = sum(1 for v in appearances.values() if v == 1)
        dupes = [cid for cid, v in appearances.items() if v > 1]
        score = good / len(automatable)
        reason = (
            f"{len(dupes)} cases appear in more than one spec: {', '.join(dupes[:5])}"
            if dupes
            else f"{good}/{len(automatable)} cases map to exactly one spec"
        )
        return self._finish(score, reason, [{"duplicated_case": d} for d in dupes[:10]])


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #

_GATES: dict[str, list[type[QAMetric]]] = {
    "eval_plan": [
        CriteriaCoverageMetric,
        PlanNoInventionMetric,
        CategoryMatrixCompleteMetric,
        AmbiguityFlaggedMetric,
    ],
    "eval_cases": [
        PlanConformanceMetric,
        CategoryBalanceMetric,
        TraceabilityMetric,
        StepCompletenessMetric,
        CaseNoInventionMetric,
    ],
    "eval_code": [
        CaseCoverageMetric,
        GroundingTierMetric,
        RunnableStructureMetric,
        SpecMappingMetric,
    ],
}


def gates() -> list[str]:
    return list(_GATES)


def metrics_for(gate: str) -> list[QAMetric]:
    """Fresh metric instances for a gate (metrics hold state when measured)."""
    return [cls() for cls in _GATES.get(gate, [])]


def build_test_case(gate: str, data: dict) -> LLMTestCase:
    """Wrap gate input in deepeval's LLMTestCase.

    The structured payload rides in `context` as JSON so the metrics stay
    within deepeval's contract rather than depending on custom fields.
    """
    question = {
        "eval_plan": "Does this test plan cover the requirement without inventing scope?",
        "eval_cases": "Do these test cases conform to the plan and the requirement?",
        "eval_code": "Does the generated suite cover the cases and run as a real framework?",
    }.get(gate, gate)
    return LLMTestCase(
        input=s(data.get("requirement")) or question,
        actual_output=flatten(
            data.get("plan") or data.get("cases") or data.get("code") or {}
        ),
        expected_output=question,
        context=[json.dumps(data, default=str)],
    )
