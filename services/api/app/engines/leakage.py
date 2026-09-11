"""Defect Leakage engine (E12).

Absorbs Rohan's Defect Leakage Analyzer: classify escaped (post-release)
defects as missed-vs-not-missed with a reason taxonomy, then propose
preventive test cases so the same class of defect is caught earlier.
Deterministic taxonomy first; LLM optional to enrich the "why" per defect.
"""

from __future__ import annotations

from ..pipeline.registry import Engine, register

# Taxonomy of why a defect leaked past QA (Rohan's reason taxonomy).
LEAK_REASONS = [
    "no_test_covered_scenario",
    "test_data_gap",
    "environment_only",
    "integration_not_tested",
    "requirement_ambiguity",
    "rare_edge_case",
    "performance_under_load",
]


def classify_leak(defect: dict) -> dict:
    """Deterministic reason classification from keywords in the defect."""
    text = " ".join(
        str(defect.get(k, "")) for k in ("title", "description", "root_cause")
    ).lower()
    if any(k in text for k in ["only in prod", "environment", "deployment", "config"]):
        reason = "environment_only"
    elif any(k in text for k in ["edge", "rare", "corner", "boundary"]):
        reason = "rare_edge_case"
    elif any(k in text for k in ["integration", "between services", "api contract"]):
        reason = "integration_not_tested"
    elif any(k in text for k in ["not in requirements", "ambiguous", "unclear"]):
        reason = "requirement_ambiguity"
    elif any(k in text for k in ["slow", "load", "concurrent", "race"]):
        reason = "performance_under_load"
    elif any(k in text for k in ["data", "fixture", "test data"]):
        reason = "test_data_gap"
    else:
        reason = "no_test_covered_scenario"

    # Was it a miss? Everything reaching production without coverage is a miss;
    # environment-only is arguably not (but we mark it for review).
    missed = reason != "environment_only"
    return {"reason": reason, "missed": missed, "review": not missed}


def preventive_tests(reason: str, defect: dict) -> list[dict]:
    """Map a leak reason to preventive test suggestions."""
    title = defect.get("title", "this defect")
    base = {
        "no_test_covered_scenario": [
            f"Add a regression test reproducing '{title}' at the API layer",
            "Add an E2E UI test walking the exact reported steps",
        ],
        "test_data_gap": [
            "Add a fixture covering the exact data shape that leaked",
            "Extend the data matrix with the production-like values",
        ],
        "environment_only": [
            "Add a smoke test on the deployment environment in CI",
            "Assert config/env parity between staging and prod",
        ],
        "integration_not_tested": [
            "Add a contract test between the two services",
            "Add an integration test exercising the full call chain",
        ],
        "requirement_ambiguity": [
            "Tighten the requirement with the clarified behavior",
            "Add acceptance criteria for the ambiguous case",
        ],
        "rare_edge_case": [
            f"Add a boundary test for the edge case in '{title}'",
            "Add the edge case to the exploratory test charter",
        ],
        "performance_under_load": [
            "Add a load test at the observed concurrency",
            "Add a race/soak test for the reported path",
        ],
    }
    return base.get(reason, ["Add a regression test for the leaked defect"])


async def _leakage(ctx: dict, **payload) -> dict:
    defects: list[dict] = payload.get("defects", [])
    analyzed = []
    for d in defects:
        info = classify_leak(d)
        analyzed.append(
            {
                "defect_id": d.get("id", d.get("key", "?")),
                "title": d.get("title", ""),
                **info,
                "preventive_tests": preventive_tests(info["reason"], d),
            }
        )
    missed = sum(1 for a in analyzed if a["missed"])
    return {
        "kind": "leakage_report",
        "payload": {
            "total_defects": len(defects),
            "missed": missed,
            "not_missed": len(defects) - missed,
            "defects": analyzed,
            "taxonomy": LEAK_REASONS,
        },
        "engine": "leakage",
    }


def register_engines() -> None:
    register(
        Engine(
            id="leakage",
            name="Analyze Defect Leakage",
            description="Classify post-release defects as missed/not-missed "
            "and propose preventive tests.",
            uses_llm=True,
            run=_leakage,
        )
    )


register_engines()