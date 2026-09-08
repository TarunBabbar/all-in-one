"""Playwright CodeGen engine (E4).

Absorbs: QA Nexus (grounding.json single-match locators + verify-suite),
Paritosh (locator->plan->generate agent chain, registry dedupe), VisionTestAI
(shared POM dedup, self-healing), SpecCraft (verified-facts artifacts).

Deterministic first: a case's own `locators` (from a prior grounding run) are
emitted with their tier; otherwise a fast smoke step is emitted so the suite is
always syntactically valid and executes quickly — never hallucinated
text-matchers that time out. Every emitted string is a properly quoted JS
literal (the earlier bug: escapes without quotes produced unrunnable output).

The payload carries:
  - `files` — spec files the runner executes ({tests: [...]})
  - `bundle` — a publish-ready folder ({filename: content}) with package.json,
    playwright.config.js, the spec and a README, so pushing it to GitHub gives
    a self-contained repo subfolder (`npm install && npx playwright test`).
"""

from __future__ import annotations

import json

from ..pipeline.registry import Engine, register

GROUNDING_TIERS = ["unverified", "dom_verified", "run_verified"]
PLAYWRIGHT_VERSION = "1.63.0"


def _js_str(s: str) -> str:
    """Deterministic JS string literal (double-quoted, safely escaped)."""
    return '"' + (
        str(s)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    ) + '"'


def _slug(title: str) -> str:
    words = [w for w in (title or "case").split()]
    keep = [w.lower().strip(".,:;()") for w in words if w.strip()][:6]
    return "_".join(keep) or "test_case"


def _locator_js(case: dict) -> str | None:
    """Emit a locator expression from grounded data, or None for a smoke step.

    Recognized `locators` shapes (single-match grounding):
      {"selector": "..."}                       -> page.locator(...)
      {"text": "..."}                           -> page.getByText(...)
      {"role": "button", "name": "..."}         -> page.getByRole(...)
    """
    loc = case.get("locators") or {}
    if not isinstance(loc, dict):
        return None
    if loc.get("selector"):
        return f"page.locator({_js_str(loc['selector'])})"
    if loc.get("text"):
        return f"page.getByText({_js_str(loc['text'])})"
    role = loc.get("role")
    if role and loc.get("name"):
        return f"page.getByRole({_js_str(role)}, {{ name: {_js_str(loc['name'])} }})"
    return None


def _case_steps_js(case: dict) -> list[str]:
    """Deterministic per-case steps.

    Grounded case -> use its real locators (evidence we can trust): assert
    visibility, and click only when the locator is role-based (button/link),
    which implies an interactive element.
    Otherwise -> a fast smoke step on the live page. We deliberately do NOT
    synthesize getByText() calls from unverified prose: they cannot match real
    DOM, and each would burn the full wait timeout until the runner kills the
    suite.
    """
    loc = case.get("locators") or {}
    is_role = bool(isinstance(loc, dict) and loc.get("role"))
    locator = _locator_js(case)
    if locator and is_role:
        return [
            f"    await {locator}.click();",
            '    await expect(page.locator("body")).toBeVisible();',
        ]
    if locator:
        return [
            f"    await expect({locator}).toBeVisible();",
        ]
    return ['    await expect(page.locator("body")).toBeVisible();']


def _build_suite(cases: list[dict], base_url: str) -> dict:
    lines = ['import { test, expect } from "@playwright/test";', ""]
    tier_report: dict[str, int] = {}
    rows: list[tuple[str, str, str]] = []
    for i, case in enumerate(cases, start=1):
        title = case.get("title", "")
        locators = case.get("locators")
        tier = case.get("grounding", "unverified") if locators else "unverified"
        tier_report[tier] = tier_report.get(tier, 0) + 1
        rows.append((f"TC-{i:04d}", title, tier))

        test_name = _js_str(title)
        lines.append(f"test.describe({_js_str(f'TC-{i:04d} {title}')}, () => {{")
        lines.append(f"  test({test_name}, async ({{ page }}) => {{")
        lines.append(f"    await page.goto({_js_str(base_url)});")
        lines.extend(_case_steps_js(case))
        lines.append("  });")
        lines.append("});")
        lines.append("")
    spec = "\n".join(lines)

    # Publish-ready companion files (deterministic templates).
    package_json = json.dumps(
        {
            "name": "qa-one-suite",
            "private": True,
            "scripts": {"test": "playwright test"},
            "devDependencies": {"@playwright/test": PLAYWRIGHT_VERSION},
        },
        indent=2,
    )
    playwright_config = (
        "module.exports = {\n"
        "  testDir: './',\n"
        "  timeout: 60_000,\n"
        "  use: {\n"
        f"    baseURL: {_js_str(base_url)},\n"
        "    headless: true,\n"
        "    screenshot: 'only-on-failure',\n"
        "  },\n"
        "};\n"
    )
    def _row(r: tuple[str, str, str]) -> str:
        rid, title, tier = r
        return f"| {rid} | {title.replace('|', '\\|')} | {tier} |"

    table = "\n".join(_row(r) for r in rows)
    readme = (
        f"# QA/One generated suite\n\n"
        f"Target: `{base_url}`\n\n"
        f"## Run\n\n```bash\nnpm install\nnpx playwright test\n```\n\n"
        f"## Cases\n\n| ID | Title | Grounding |\n| --- | --- | --- |\n{table}\n\n"
        f"Grounding tiers: `unverified` selectors are placeholders until a real "
        f"grounding pass records single-match locators; `dom_verified` / "
        f"`run_verified` carry recorded evidence.\n"
    )

    return {
        "files": {"tests": [{"name": "qa.spec.ts", "content": spec}]},
        "bundle": {
            "qa.spec.ts": spec,
            "package.json": package_json,
            "playwright.config.js": playwright_config,
            "README.md": readme,
        },
        "grounding_report": {"tiers": GROUNDING_TIERS, "counts": tier_report},
        "base_url": base_url,
        "total_cases": len(cases),
    }


async def _codegen(ctx: dict, **payload) -> dict:
    from ..core.settings import get_settings

    cases: list[dict] = payload.get("cases", [])
    base_url: str = str(payload.get("base_url") or get_settings().app_base_url)
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
