"""Sandboxed Executor engine (E5) with a self-healing run loop.

Absorbs: QA_AI_Solution (execute generated Playwright, collect evidence),
OmnyGO (planner/driver/verifier), ETL Buddy (sandboxed execution), QAE2E
(Docker-isolated run), VisionTestAI (self-heal loop with approval).

Behaviour
---------
Run the suite. If tests fail, re-inspect the live DOM through the runner's
`/inspect`, re-map the locators that no longer resolve, rewrite the page
objects, and run again — up to `MAX_HEAL_ATTEMPTS` times. Deterministic
matching is tried first; the model is consulted only when no candidate in the
snapshot matches, so the common case costs nothing and stays reproducible.

Tests still failing after the last attempt are reported in `manual_required`.
They are never silently dropped and never marked as passing — a suite that
could not be healed is evidence, and the release gate needs to see it.

If healing produces no change, the loop stops early: rerunning an identical
suite would just burn the budget to reach the same answer.
"""

from __future__ import annotations

import re
import time

import httpx

from ..core.settings import get_settings
from ..pipeline.registry import Engine, register

DEFAULT_TIMEOUT = 420.0
_WORD = re.compile(r"[a-z0-9]+")


# --------------------------------------------------------------------------- #
# runner calls
# --------------------------------------------------------------------------- #

async def _post(runner: str, path: str, body: dict, timeout: float) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{runner.rstrip('/')}{path}", json=body)
        resp.raise_for_status()
        return resp.json()


async def _one_run(
    runner: str, files: list, base_url: str, suite_id: str, timeout: float
) -> tuple[list[dict], str | None]:
    """One Playwright run. Returns (results, error) — error is operational only."""
    data = await _post(
        runner,
        "/run",
        {"suiteId": suite_id, "files": files, "baseUrl": base_url},
        timeout,
    )
    results = data.get("results") or []
    if not data.get("ok") or not results:
        excerpt = (data.get("raw_stdout_excerpt") or "").strip().replace("\n", " ")[-300:]
        detail = (
            "playwright produced no parseable report"
            if not data.get("ok")
            else "the report contained 0 specs (check the suite layout)"
        )
        return [], f"runner returned no results — {detail}. {excerpt}".strip()
    return results, None


# --------------------------------------------------------------------------- #
# deterministic candidate matching
# --------------------------------------------------------------------------- #

def _norm(value: str) -> str:
    return " ".join(_WORD.findall((value or "").lower()))


def _overlap(a: str, b: str) -> float:
    wa, wb = set(_WORD.findall(_norm(a))), set(_WORD.findall(_norm(b)))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa)


def _score_candidate(probe: dict, candidate: dict) -> float:
    """How well a live candidate matches the element we originally targeted."""
    c_role = (candidate.get("role") or "").lower()
    c_name = candidate.get("name") or ""
    p_role = (probe.get("role") or "").lower()
    p_name = probe.get("name") or probe.get("element") or ""

    # Highest confidence: the structured probe matches exactly.
    if probe.get("testid") and probe["testid"] == candidate.get("testId"):
        return 1.0
    if probe.get("placeholder") and probe["placeholder"] == candidate.get("placeholder"):
        return 1.0
    if probe.get("css"):
        return 0.0  # a CSS probe cannot be matched to a role/name candidate

    if p_role and c_role and p_role == c_role:
        if _norm(p_name) and _norm(p_name) == _norm(c_name):
            return 1.0
        overlap = _overlap(p_name, c_name)
        if overlap >= 0.6:
            return 0.8
    if _norm(p_name) and _norm(p_name) == _norm(c_name):
        return 0.7
    if c_name and _overlap(p_name, c_name) >= 0.6:
        return 0.5
    return 0.0


MATCH_THRESHOLD = 0.7


def best_candidate(probe: dict, candidates: list[dict]) -> dict | None:
    best: dict | None = None
    best_score = 0.0
    for cand in candidates:
        score = _score_candidate(probe, cand)
        if score > best_score:
            best, best_score = cand, score
    return best if best_score >= MATCH_THRESHOLD else None


# --------------------------------------------------------------------------- #
# spec rewriting
# --------------------------------------------------------------------------- #

def rewrite_locator(source: str, prop: str, old_expr: str, new_expr: str) -> str:
    """Replace one page-object locator assignment.

    Anchored to `this.<prop> = ...;` so a substring that happens to appear
    elsewhere in the file is never touched.
    """
    pattern = re.compile(
        r"(this\." + re.escape(prop) + r"\s*=\s*)" + re.escape(old_expr) + r"(\s*;)"
    )
    return pattern.sub(lambda m: m.group(1) + new_expr + m.group(2), source, count=1)


def relevant_locators(files: list[dict], locators: list[dict], failures: list[dict]) -> list[dict]:
    """Locators belonging to the pages the failing specs actually import."""
    failing_files = {str(f.get("file") or "") for f in failures}
    sources = {
        str(f.get("name") or ""): str(f.get("content") or "")
        for f in files
        if isinstance(f, dict)
    }
    imported: set[str] = set()
    for name, src in sources.items():
        if not any(ff and ff in name for ff in failing_files):
            continue
        for loc in locators:
            page = str(loc.get("file") or "")
            stem = page.rsplit("/", 1)[-1].replace(".ts", "")
            if stem and stem in src:
                imported.add(page)
    # If nothing matched (flat layouts, unusual imports), heal everything —
    # a failed run is not the moment to be conservative about scope.
    if not imported:
        return list(locators)
    return [loc for loc in locators if str(loc.get("file")) in imported]


# --------------------------------------------------------------------------- #
# the heal step
# --------------------------------------------------------------------------- #

async def _llm_locator(
    ctx: dict, element: str, snapshot: str, old_expr: str
) -> str | None:
    """Last resort: ask the model for a locator, constrained to the snapshot."""
    router = ctx.get("router")
    if router is None or getattr(router, "is_mock", True) or not snapshot:
        return None
    from ..core.prompts import LOCATOR_SYSTEM, LocatorFixes, locator_prompt

    try:
        result = await router.complete_json(
            LOCATOR_SYSTEM, locator_prompt(element, snapshot, old_expr), LocatorFixes
        )
    except Exception:  # noqa: BLE001 — a failed suggestion is not a failure
        return None
    for fix in result.fixes:
        if fix.new_locator.strip():
            return fix.new_locator.strip()
    return None


async def _heal(
    ctx: dict,
    *,
    files: list[dict],
    locators: list[dict],
    failures: list[dict],
    base_url: str,
    runner: str,
    inspect_timeout: float,
) -> tuple[list[dict], list[dict], list[dict], str | None]:
    """Re-map broken locators against the live DOM.

    Returns (files, locators, fixed_records, error).
    """
    targets = relevant_locators(files, locators, failures)
    if not targets:
        return files, locators, [], None

    hints = [{"element": loc["element"], **(loc.get("probe") or {})} for loc in targets]
    try:
        snap = await _post(runner, "/inspect", {"url": base_url, "hints": hints}, inspect_timeout)
    except httpx.HTTPError as exc:
        return files, locators, [], f"inspect failed: {exc}"

    found_by_element = {
        str(h.get("element")): bool(h.get("found"))
        for h in (snap.get("hints") or [])
        if isinstance(h, dict)
    }
    candidates = [c for c in (snap.get("candidates") or []) if isinstance(c, dict)]
    snapshot = str(snap.get("aria_snapshot") or "")

    updated_files = {str(f.get("name")): str(f.get("content") or "") for f in files}
    updated_locators = [dict(loc) for loc in locators]
    fixed: list[dict] = []

    for loc in updated_locators:
        element = str(loc.get("element") or "")
        if found_by_element.get(element, True):
            continue  # still resolves — leave it alone

        probe = dict(loc.get("probe") or {})
        probe.setdefault("element", element)
        candidate = best_candidate(probe, candidates)
        method = "deterministic"
        new_expr = str(candidate.get("locator") or "") if candidate else ""

        if not new_expr or new_expr == loc.get("locator"):
            suggested = await _llm_locator(ctx, element, snapshot, str(loc.get("locator") or ""))
            if suggested and suggested != loc.get("locator"):
                new_expr, method = suggested, "model"

        if not new_expr or new_expr == loc.get("locator"):
            continue

        page = str(loc.get("file") or "")
        source = updated_files.get(page)
        if source is None:
            continue
        rewritten = rewrite_locator(
            source, str(loc.get("property")), str(loc.get("locator")), new_expr
        )
        if rewritten == source:
            continue

        updated_files[page] = rewritten
        fixed.append(
            {
                "file": page,
                "element": element,
                "old_locator": loc.get("locator"),
                "new_locator": new_expr,
                "method": method,
            }
        )
        loc["locator"] = new_expr
        loc["tier"] = "dom_verified"

    new_files = [
        {"name": name, "content": content} for name, content in updated_files.items()
    ]
    return new_files, updated_locators, fixed, None


# --------------------------------------------------------------------------- #
# engine entrypoint
# --------------------------------------------------------------------------- #

async def _run_suite(ctx: dict, **payload) -> dict:
    settings = get_settings()
    files: list[dict] = payload.get("files") or []
    locators: list[dict] = payload.get("locators") or []
    suite_id: str = str(payload.get("suite_id", "suite"))
    base_url: str = str(payload.get("base_url") or settings.app_base_url)
    runner = str(payload.get("runner_url") or settings.runner_url)
    max_attempts = max(1, int(settings.max_heal_attempts))
    budget = float(settings.stage_budget_s)
    call_timeout = float(settings.runner_call_timeout_s)
    inspect_timeout = float(settings.inspect_timeout_s)

    if not files:
        return {
            "kind": "run_results",
            "payload": {"error": "no suite files to run."},
            "engine": "executor",
        }

    deadline = time.monotonic() + budget
    attempts: list[dict] = []
    auto_fixed: list[dict] = []
    results: list[dict] = []
    last_error: str | None = None
    current_files = files
    current_locators = locators

    for attempt in range(1, max_attempts + 1):
        try:
            results, last_error = await _one_run(
                runner, current_files, base_url, suite_id, call_timeout
            )
        except httpx.HTTPError as exc:
            return {
                "kind": "run_results",
                "payload": {
                    "runner_unreachable": True,
                    "runner": runner,
                    "error": str(exc),
                    "results": [],
                },
                "engine": "executor",
            }

        if last_error:
            # The runner answered but produced nothing usable. Retrying cannot
            # help, so stop with the runner's own words.
            break

        failures = [r for r in results if r.get("status") != "passed"]
        attempts.append(
            {
                "attempt": attempt,
                "total": len(results),
                "passed": len(results) - len(failures),
                "failed": len(failures),
            }
        )
        if not failures:
            break
        if attempt >= max_attempts or time.monotonic() > deadline:
            break

        current_files, current_locators, fixed, heal_error = await _heal(
            ctx,
            files=current_files,
            locators=current_locators,
            failures=failures,
            base_url=base_url,
            runner=runner,
            inspect_timeout=inspect_timeout,
        )
        if heal_error:
            last_error = heal_error
            break
        if not fixed:
            # Nothing changed, so another identical run reaches the same place.
            break
        auto_fixed.extend(fixed)

    if last_error and not results:
        return {
            "kind": "run_results",
            "payload": {
                "runner": runner,
                "suite_id": suite_id,
                "error": last_error,
                "results": [],
                "attempts": attempts,
            },
            "engine": "executor",
        }

    failures = [r for r in results if r.get("status") != "passed"]
    return {
        "kind": "run_results",
        "payload": {
            "runner": runner,
            "suite_id": suite_id,
            "results": results,
            "ok": not failures,
            "attempts": attempts,
            "auto_fixed": auto_fixed,
            "manual_required": [
                {
                    "test": r.get("title") or r.get("id"),
                    "file": r.get("file"),
                    "reason": "still failing after the final attempt",
                    "error": (r.get("error") or "")[:300],
                }
                for r in failures
            ],
            "locators": current_locators,
            "healed": bool(auto_fixed),
        },
        "engine": "executor",
    }


def register_engines() -> None:
    register(
        Engine(
            id="executor",
            name="Test Runner",
            description="Dispatch the generated suite to the sandboxed Playwright "
            "runner, re-inspect the DOM on failure and heal locators, then report "
            "per-test evidence plus anything that needs a manual run.",
            uses_llm=True,
            uses_runner=True,
            run=_run_suite,
        )
    )


register_engines()
