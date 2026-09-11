"""Prompt text and response schemas for the model-backed stages.

Every schema here is the *contract* the deterministic layer measures against.
The model fills the shape; local code decides whether the result is acceptable
(the eval gates). That is why the schemas are strict and the allowed values are
enumerated rather than free text.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

CATEGORIES = ["positive", "negative", "edge", "e2e", "security", "accessibility", "api"]


# --------------------------------------------------------------------------- #
# Test plan
# --------------------------------------------------------------------------- #

class PlanCriterion(BaseModel):
    """One testable criterion, tied to the wording of the requirement."""

    id: str = Field(description="Stable id, e.g. AC-01")
    text: str = Field(description="The criterion, in the requirement's own terms")
    categories: list[str] = Field(
        description="Which of positive/negative/edge/e2e apply. Include e2e for multi-step flows."
    )


class TestPlan(BaseModel):
    """The plan the case generator must conform to."""

    criteria: list[PlanCriterion] = Field(
        description="Every acceptance criterion in the requirement. Do not invent scope."
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Assumptions made where the requirement is silent.",
    )
    ambiguous: list[str] = Field(
        default_factory=list,
        description="Statements that are ambiguous and were resolved by an assumption.",
    )
    approach: str = Field(default="", description="One paragraph on the testing approach.")

    @classmethod
    def _mock_example(cls) -> TestPlan:
        """Offline fixture so the pipeline runs under LLM_PROVIDER=mock."""
        return cls(
            criteria=[
                PlanCriterion(
                    id="AC-01",
                    text="Login succeeds with a valid username and password",
                    categories=["positive", "negative", "edge"],
                ),
                PlanCriterion(
                    id="AC-02",
                    text="An invalid password shows an error and stays on the login page",
                    categories=["positive", "negative", "edge"],
                ),
            ],
            assumptions=["A standard user account exists"],
            ambiguous=["Session expires after a period of inactivity"],
            approach="Cover each acceptance criterion with positive, negative and edge cases.",
        )


PLAN_SYSTEM = (
    "You are a QA lead writing a test plan. Work only from the requirement given. "
    "List every acceptance criterion it states, using the requirement's own wording. "
    "Never invent scope that is not in the requirement. Where the requirement is "
    "silent or vague, record it under `ambiguous` and state the assumption you made "
    "under `assumptions`. For each criterion, say which categories apply: positive, "
    "negative, edge, and e2e when the criterion describes a multi-step flow."
)


def plan_prompt(requirement: str) -> str:
    return (
        "REQUIREMENT:\n"
        f"{requirement}\n\n"
        "Produce the test plan as JSON. One entry in `criteria` per acceptance "
        "criterion the requirement states — not one per feature. If the requirement "
        "states no acceptance criteria, return an empty criteria list rather than "
        "inventing them."
    )


# --------------------------------------------------------------------------- #
# Test cases
# --------------------------------------------------------------------------- #

class TestCaseOut(BaseModel):
    """One test case, traceable to the criterion it verifies."""

    criterion_id: str = Field(description="The AC id from the plan this case verifies")
    title: str = Field(description="What the case verifies, in one line")
    type: str = Field(
        description="One of: positive, negative, edge, e2e, security, accessibility, api"
    )
    priority: str = Field(default="P2", description="P0 | P1 | P2 | P3")
    severity: str = Field(default="medium", description="critical | high | medium | low")
    preconditions: list[str] = Field(description="State required before the steps run")
    steps: list[str] = Field(description="Ordered actions a human could follow")
    expected: str = Field(description="The observable result that makes this pass or fail")
    automation_rec: str = Field(default="automate", description="automate | manual | both")
    source_evidence: list[str] = Field(default_factory=list)


class TestCases(BaseModel):
    cases: list[TestCaseOut] = Field(description="The full case set for the plan")

    @classmethod
    def _mock_example(cls) -> TestCases:
        return cls(
            cases=[
                TestCaseOut(
                    criterion_id="AC-01",
                    title="Valid credentials log the user in",
                    type="positive",
                    priority="P1",
                    severity="high",
                    preconditions=["A standard user account exists"],
                    steps=["Open the login page", "Enter valid credentials", "Submit"],
                    expected="The user reaches the inventory page",
                    automation_rec="automate",
                ),
                TestCaseOut(
                    criterion_id="AC-01",
                    title="Invalid password is rejected",
                    type="negative",
                    priority="P1",
                    severity="high",
                    preconditions=["A standard user account exists"],
                    steps=["Open the login page", "Enter a wrong password", "Submit"],
                    expected="An error message is shown and the user stays on the login page",
                    automation_rec="automate",
                ),
                TestCaseOut(
                    criterion_id="AC-02",
                    title="Empty credentials show a required error",
                    type="edge",
                    priority="P2",
                    severity="medium",
                    preconditions=["The login page is reachable"],
                    steps=["Open the login page", "Submit with both fields empty"],
                    expected="A required-field error is shown",
                    automation_rec="automate",
                ),
            ]
        )


CASES_SYSTEM = (
    "You are a QA engineer writing test cases from an approved test plan. "
    "Every case must name the criterion id it verifies. Cover every criterion in "
    "the plan with at least one positive, one negative and one edge case, and add "
    "an end-to-end case for criteria that describe a multi-step flow. Ground every "
    "step and expectation in the requirement or the plan — never invent behaviour "
    "that is not stated. Write steps a human could follow without seeing the app."
)


def cases_prompt(requirement: str, plan: dict, max_cases: int) -> str:
    return (
        f"REQUIREMENT:\n{requirement}\n\n"
        f"TEST PLAN:\n{plan}\n\n"
        f"Write one case per criterion per applicable category, up to {max_cases} cases "
        "in total. Do not stop early if the plan has more criteria. Do not add cases "
        "that no criterion covers."
    )


# --------------------------------------------------------------------------- #
# Locator healing
# --------------------------------------------------------------------------- #

class LocatorFix(BaseModel):
    """A replacement locator proposed for one failing test."""

    test_id: str = Field(description="The test the fix applies to")
    new_locator: str = Field(
        description=(
            "A Playwright locator that exists in the snapshot, "
            "e.g. page.getByRole('button', { name: 'Login' })"
        )
    )
    rationale: str = Field(default="", description="Why this element is the intended target")


class LocatorFixes(BaseModel):
    fixes: list[LocatorFix] = Field(default_factory=list)

    @classmethod
    def _mock_example(cls) -> LocatorFixes:
        return cls(fixes=[])


LOCATOR_SYSTEM = (
    "You are repairing a failing Playwright test. You are given the element the test "
    "intended to interact with and an accessibility snapshot of the live page. Choose "
    "a locator for the element that best matches the intent, using ONLY roles and "
    "names that appear in the snapshot. Prefer getByRole, then getByLabel, then "
    "getByTestId. Return an empty fix list for a test if no element in the snapshot "
    "matches its intent — a wrong locator is worse than none."
)


def locator_prompt(intent: str, snapshot: str, old_locator: str) -> str:
    return (
        f"INTENDED ELEMENT:\n{intent}\n\n"
        f"CURRENT (FAILING) LOCATOR:\n{old_locator}\n\n"
        f"ACCESSIBILITY SNAPSHOT OF THE LIVE PAGE:\n{snapshot}\n\n"
        "Return the corrected locator."
    )
