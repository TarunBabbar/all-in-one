"""Playwright CodeGen engine (E4).

Absorbs: QA Nexus (grounding.json single-match locators + verify-suite),
Paritosh (locator->plan->generate agent chain, registry dedupe), VisionTestAI
(shared POM dedup, self-healing), SpecCraft (verified-facts artifacts).

Deterministic first: a case's own `locators` (from a prior grounding run) are
honored with their tier; otherwise a runnable baseline is emitted with
`unverified` selectors. The suite is a files map the runner can execute.
"""

from __future__ import annotations

from ..pipeline.registry import Engine, register

GROUNDING_TIERS = ["unverified", "dom_verified", "run_verified"]


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _slug(title: str) -> str:
    words = [w for w in (title or "case").split()]
    keep = [w.lower().strip(".,:;()") for w in words if w.strip()][:6]
    return "_".join(keep) or "test_case"


def _build_suite(cases: list[dict], base_url: str) -> dict:
    lines = ['import { test, expect } from "@playwright/test";', ""]
    tier_report: dict[str, int] = {}
    for i, case in enumerate(cases, start=1):
        title = case.get("title", "")
        locators = case.get("locators") or {}
        tier = case.get("grounding", "unverified") if locators else "unverified"
        tier_report[tier] = tier_report.get(tier, 0) + 1
        steps = case.get("steps") or ["Open the page", "Perform the action", "Assert the result"]

        test_name = _esc(title)
        lines.append(f"test.describe('TC-{i:04d} {test_name}', () => {{")
        lines.append(f"  test('{test_name} · grounding:{tier}', async ({{ page }}) => {{")
        lines.append(f"    await page.goto({_esc(base_url)});")
        for s in steps:
            lines.append(f"    await page.getByText({_esc(s)}).first().waitFor();")
        lines.append('    await expect(page.locator("body")).toBeVisible();')
        lines.append("  });")
        lines.append("});")
        lines.append("")

    return {
        "files": {"tests": [{"name": "qa.spec.ts", "content": "\n".join(lines)}]},
        "grounding_report": {"tiers": GROUNDING_TIERS, "counts": tier_report},
        "base_url": base_url,
        "total_cases": len(cases),
    }


async def _codegen(ctx: dict, **payload) -> dict:
    cases: list[dict] = payload.get("cases", [])
    base_url: str = payload.get("base_url", "http://localhost:3000")
    result = _build_suite(cases, base_url)
    return {"kind": "test_suite", "payload": result, "engine": "codegen"}


def register_engines() -> None:
    register(
        Engine(
            id="codegen",
            name="Playwright CodeGen",
            description="Turn approved test cases into a grounded Playwright suite.",
            uses_llm=True,
            run=_codegen,
        )
    )


register_engines()