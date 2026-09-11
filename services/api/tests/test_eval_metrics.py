"""Eval-gate tests.

The point of these is not that good input passes — it is that bad input FAILS,
for the right metric and with a reason a human can act on. A gate that cannot
fail is worse than no gate, because it reports safety it does not provide.

Everything here runs offline: the metrics are deterministic, so no provider,
no network and no keys are involved.
"""

from __future__ import annotations

from app.eval import build_gate_input, run_gate
from app.eval.extract import split_requirement_criteria

REQUIREMENT = """Login flow for the storefront.

Acceptance Criteria:
- Login succeeds with a valid username and password
- Invalid password shows an error and stays on the login page
"""


def _metric(report: dict, name: str) -> dict:
    for m in report["metrics"]:
        if m["name"] == name:
            return m
    raise AssertionError(f"metric {name} not in report: {[m['name'] for m in report['metrics']]}")


def _plan(*, second_category: str = "edge", extra_uncited: str = "") -> dict:
    criteria = [
        {
            "id": "AC-01",
            "text": "Login succeeds with a valid username and password",
            "categories": ["positive", "negative", "edge"],
        },
        {
            "id": "AC-02",
            "text": "Invalid password shows an error and stays on the login page",
            "categories": ["positive", "negative", second_category],
        },
    ]
    if extra_uncited:
        criteria.append({"id": "AC-03", "text": extra_uncited, "categories": ["positive"]})
    return {"criteria": criteria, "assumptions": [], "ambiguous": []}


def _cases(
    plan: dict, *, omit_for: str = "", drop_expected_for: str = "", orphan: bool = False
) -> list[dict]:
    """A conformant case set. `expected` mirrors the criterion's own wording,
    which is what a grounded expectation looks like."""
    texts = {c["id"]: c["text"] for c in plan["criteria"]}
    out: list[dict] = []
    for crit_id in ("AC-01", "AC-02"):
        if crit_id == omit_for:
            continue
        for case_type in ("positive", "negative", "edge"):
            out.append(
                {
                    "id": f"TC-{len(out) + 1:04d}",
                    "criterion_id": crit_id,
                    "title": f"{crit_id} {case_type}",
                    "type": case_type,
                    "preconditions": ["The storefront is reachable"],
                    "steps": ["Open the login page", "Enter the username and password", "Submit"],
                    "expected": "" if crit_id == drop_expected_for else texts[crit_id],
                    "automation_rec": "automate",
                }
            )
    if orphan:
        out.append(
            {
                "id": "TC-9999",
                "criterion_id": "AC-99",
                "title": "orphan case",
                "type": "positive",
                "preconditions": ["x"],
                "steps": ["y", "z"],
                "expected": "w",
                "automation_rec": "automate",
            }
        )
    return out


# --------------------------------------------------------------------------- #
# requirement parsing
# --------------------------------------------------------------------------- #

def test_requirement_criteria_are_extracted_from_the_text() -> None:
    criteria = split_requirement_criteria(REQUIREMENT)
    assert len(criteria) == 2
    assert "Login succeeds" in criteria[0]


def test_requirement_without_criteria_returns_nothing() -> None:
    assert split_requirement_criteria("Make the app nicer.") == []


# --------------------------------------------------------------------------- #
# Gate 1 — plan
# --------------------------------------------------------------------------- #

def test_plan_gate_passes_a_complete_plan() -> None:
    report = run_gate("eval_plan", build_gate_input("eval_plan", requirement=REQUIREMENT,
                                                    plan=_plan()))
    assert report["passed"], report["metrics"]
    assert report["summary"]["failed"] == 0


def test_plan_gate_fails_when_the_plan_drops_a_stated_criterion() -> None:
    """A plan that silently ignores half the requirement must not pass."""
    thin = {"criteria": [_plan()["criteria"][0]], "assumptions": [], "ambiguous": []}
    report = run_gate("eval_plan", build_gate_input("eval_plan", requirement=REQUIREMENT,
                                                    plan=thin))
    assert not report["passed"]
    metric = _metric(report, "CriteriaCoverage")
    assert not metric["passed"]
    assert "Invalid password" in metric["reason"]


def test_plan_gate_fails_on_invented_scope() -> None:
    report = run_gate(
        "eval_plan",
        build_gate_input(
            "eval_plan",
            requirement=REQUIREMENT,
            plan=_plan(extra_uncited="Support SAML single sign-on with an identity provider"),
        ),
    )
    assert not report["passed"]
    assert not _metric(report, "PlanNoInvention")["passed"]


def test_plan_gate_fails_when_a_criterion_lacks_the_negative_category() -> None:
    report = run_gate(
        "eval_plan",
        build_gate_input("eval_plan", requirement=REQUIREMENT,
                         plan=_plan(second_category="security")),
    )
    assert not report["passed"]
    metric = _metric(report, "CategoryMatrixComplete")
    assert not metric["passed"]
    assert "AC-02" in metric["reason"]


def test_plan_gate_requires_an_assumption_for_ambiguous_statements() -> None:
    plan = _plan()
    plan["ambiguous"] = ["Session expires after a period of inactivity"]
    plan["assumptions"] = []
    report = run_gate("eval_plan", build_gate_input("eval_plan", requirement=REQUIREMENT,
                                                    plan=plan))
    assert not report["passed"]
    assert not _metric(report, "AmbiguityFlagged")["passed"]


# --------------------------------------------------------------------------- #
# Gate 2 — cases
# --------------------------------------------------------------------------- #

def test_case_gate_passes_a_conformant_set() -> None:
    report = run_gate(
        "eval_cases",
        build_gate_input("eval_cases", requirement=REQUIREMENT, plan=_plan(),
                         cases=_cases(_plan())),
    )
    assert report["passed"], report["metrics"]


def test_case_gate_fails_when_a_plan_item_has_no_case() -> None:
    report = run_gate(
        "eval_cases",
        build_gate_input("eval_cases", requirement=REQUIREMENT, plan=_plan(),
                         cases=_cases(_plan(), omit_for="AC-02")),
    )
    assert not report["passed"]
    assert not _metric(report, "PlanConformance")["passed"]
    assert not _metric(report, "CategoryBalance")["passed"]


def test_case_gate_fails_on_an_untraceable_case() -> None:
    report = run_gate(
        "eval_cases",
        build_gate_input("eval_cases", requirement=REQUIREMENT, plan=_plan(),
                         cases=_cases(_plan(), orphan=True)),
    )
    assert not report["passed"]
    assert not _metric(report, "Traceability")["passed"]


def test_case_gate_fails_when_a_case_has_no_expectation() -> None:
    report = run_gate(
        "eval_cases",
        build_gate_input("eval_cases", requirement=REQUIREMENT, plan=_plan(),
                         cases=_cases(_plan(), drop_expected_for="AC-01")),
    )
    assert not report["passed"]
    metric = _metric(report, "StepCompleteness")
    assert not metric["passed"]
    assert "expected" in metric["reason"]


def test_case_gate_fails_on_invented_steps() -> None:
    cases = _cases(_plan())
    cases[0]["steps"] = [
        "Open the login page",
        "Authenticate through the corporate LDAP directory",
        "Assert the SAML assertion is cached",
    ]
    report = run_gate(
        "eval_cases",
        build_gate_input("eval_cases", requirement=REQUIREMENT, plan=_plan(), cases=cases),
    )
    assert not report["passed"]
    assert not _metric(report, "CaseNoInvention")["passed"]


# --------------------------------------------------------------------------- #
# Gate 3 — generated code
# --------------------------------------------------------------------------- #

CODE = {
    "bundle": {
        "package.json": '{"name":"suite"}',
        "playwright.config.ts": "export default {}",
        "tests/pages/base.page.ts": "export abstract class BasePage {}",
        "tests/e2e/login.spec.ts": 'test("TC-0001 positive", async () => {});',
    },
    "grounding_report": {"counts": {"unverified": 0, "dom_verified": 6, "run_verified": 0}},
}


def _code_input(code: dict, cases: list[dict]):
    return build_gate_input("eval_code", requirement=REQUIREMENT, plan=_plan(),
                            cases=cases, code=code)


def test_code_gate_passes_a_complete_grounded_suite() -> None:
    cases = [
        {"id": "TC-0001", "criterion_id": "AC-01", "automation_rec": "automate"},
    ]
    report = run_gate("eval_code", _code_input(CODE, cases))
    assert report["passed"], report["metrics"]


def test_code_gate_fails_when_an_automatable_case_has_no_spec() -> None:
    cases = [
        {"id": "TC-0001", "criterion_id": "AC-01", "automation_rec": "automate"},
        {"id": "TC-0002", "criterion_id": "AC-02", "automation_rec": "automate"},
    ]
    report = run_gate("eval_code", _code_input(CODE, cases))
    assert not report["passed"]
    metric = _metric(report, "CaseCoverage")
    assert not metric["passed"]
    assert "TC-0002" in metric["reason"]


def test_code_gate_fails_on_ungrounded_locators() -> None:
    code = {**CODE, "grounding_report": {"counts": {"unverified": 9, "dom_verified": 1}}}
    cases = [{"id": "TC-0001", "criterion_id": "AC-01", "automation_rec": "automate"}]
    report = run_gate("eval_code", _code_input(code, cases))
    assert not report["passed"]
    assert not _metric(report, "GroundingTier")["passed"]


def test_code_gate_fails_on_todo_stubs() -> None:
    code = {
        **CODE,
        "bundle": {**CODE["bundle"], "tests/e2e/login.spec.ts": "// TODO implement\n"},
    }
    cases = [{"id": "TC-0001", "criterion_id": "AC-01", "automation_rec": "automate"}]
    report = run_gate("eval_code", _code_input(code, cases))
    assert not report["passed"]
    assert not _metric(report, "RunnableStructure")["passed"]


def test_code_gate_reports_unknown_grounding_rather_than_passing() -> None:
    """A missing grounding report must not read as 'all locators verified'."""
    code = {"bundle": CODE["bundle"]}
    cases = [{"id": "TC-0001", "criterion_id": "AC-01", "automation_rec": "automate"}]
    report = run_gate("eval_code", _code_input(code, cases))
    metric = _metric(report, "GroundingTier")
    assert not metric["passed"]
    assert metric["score"] == 0.0
    assert "unknown" in metric["reason"]


# --------------------------------------------------------------------------- #
# empty input must not silently pass
# --------------------------------------------------------------------------- #

def test_gate_with_no_cases_reports_the_missing_input() -> None:
    report = run_gate(
        "eval_cases", build_gate_input("eval_cases", requirement=REQUIREMENT, plan=_plan())
    )
    # Nothing to check is not a pass: the gate must say so.
    assert report["summary"]["total"] > 0
    assert not all(m["passed"] for m in report["metrics"])


# --------------------------------------------------------------------------- #
# a failing gate must stop the chain
# --------------------------------------------------------------------------- #

def test_failed_gate_stops_the_chain_and_names_the_metric() -> None:
    """A gate that reports `passed: False` must be treated as a hard failure,
    otherwise a weak artifact flows straight into automation."""
    from app.pipeline.models import StageId
    from app.pipeline.runner import _failure_message, _is_hard_failure

    failed = {
        "kind": "eval_report",
        "payload": {
            "gate": "eval_cases",
            "passed": False,
            "summary": {"failed_metrics": ["Traceability", "PlanConformance"]},
        },
    }
    assert _is_hard_failure(failed)
    message = _failure_message(StageId.EVAL_CASES, failed)
    assert "Traceability" in message


def test_passing_gate_does_not_stop_the_chain() -> None:
    from app.pipeline.runner import _is_hard_failure

    ok = {"kind": "eval_report", "payload": {"gate": "eval_cases", "passed": True}}
    assert not _is_hard_failure(ok)
