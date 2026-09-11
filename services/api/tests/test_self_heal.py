"""Self-heal tests.

Two things must hold for the heal loop to be trustworthy:
  1. it re-maps a locator only on real evidence (a candidate that actually
     exists in the live DOM), and never silently marks a failure as a pass;
  2. it stops when it cannot improve anything, instead of burning the whole
     attempt budget to reach the same result.

The runner is stubbed, so these run offline with no browser.
"""

from __future__ import annotations

import pytest

from app.engines import executor
from app.engines.executor import (
    best_candidate,
    relevant_locators,
    rewrite_locator,
)

PAGE = "tests/pages/login.page.ts"
SPEC = "e2e/login.spec.ts"
OLD = 'page.getByTestId("login-btn")'
NEW = 'page.getByRole("button", { name: "Login" })'

PAGE_SOURCE = (
    'import { Page, Locator } from "@playwright/test";\n\n'
    "export class LoginPage {\n"
    "  readonly loginButton: Locator;\n\n"
    "  constructor(page: Page) {\n"
    f"    this.loginButton = {OLD};\n"
    "  }\n"
    "}\n"
)

FILES = [
    {"name": PAGE, "content": PAGE_SOURCE},
    {"name": SPEC, "content": 'import { LoginPage } from "../pages/login.page";\n'},
]

LOCATORS = [
    {
        "file": PAGE,
        "property": "loginButton",
        "element": "Login",
        "locator": OLD,
        "probe": {"testid": "login-btn"},
        "tier": "dom_verified",
    }
]

FAIL = {"id": "TC-0001", "title": "login", "file": SPEC, "status": "failed", "error": "not found"}
PASS = {"id": "TC-0001", "title": "login", "file": SPEC, "status": "passed"}


# --------------------------------------------------------------------------- #
# pure helpers
# --------------------------------------------------------------------------- #

def test_rewrite_locator_replaces_only_the_named_property() -> None:
    out = rewrite_locator(PAGE_SOURCE, "loginButton", OLD, NEW)
    assert NEW in out
    assert OLD not in out
    # Everything else is untouched.
    assert "readonly loginButton: Locator;" in out
    assert out.count("constructor") == 1


def test_rewrite_locator_is_a_no_op_for_an_unknown_property() -> None:
    assert rewrite_locator(PAGE_SOURCE, "nope", OLD, NEW) == PAGE_SOURCE


def test_relevant_locators_follows_the_failing_specs_imports() -> None:
    picked = relevant_locators(FILES, LOCATORS, [FAIL])
    assert [loc["property"] for loc in picked] == ["loginButton"]


def test_relevant_locators_falls_back_to_everything_when_nothing_matches() -> None:
    """A failure we cannot attribute must not silently heal nothing."""
    orphan = [{"id": "x", "file": "e2e/unknown.spec.ts", "status": "failed"}]
    assert len(relevant_locators(FILES, LOCATORS, orphan)) == 1


def test_best_candidate_accepts_a_matching_role_and_name() -> None:
    cand = {"role": "button", "name": "Login", "locator": NEW}
    assert best_candidate({"testid": "login-btn", "element": "Login"}, [cand]) == cand


def test_best_candidate_rejects_a_different_element() -> None:
    """The wrong element is worse than no heal, so this must return None."""
    cand = {"role": "button", "name": "Checkout", "locator": 'page.getByRole("button")'}
    assert best_candidate({"testid": "login-btn", "element": "Login"}, [cand]) is None


def test_best_candidate_prefers_an_exact_testid_match() -> None:
    exact = {"role": None, "name": "x", "testId": "login-btn", "locator": 'page.getByTestId("login-btn")'}
    other = {"role": "button", "name": "Login", "locator": NEW}
    assert best_candidate({"testid": "login-btn", "element": "Login"}, [other, exact]) == exact


# --------------------------------------------------------------------------- #
# the loop
# --------------------------------------------------------------------------- #

class FakeRunner:
    """Stub for the runner's HTTP surface."""

    def __init__(self, runs: list[list[dict]], inspect: dict | None = None) -> None:
        self._runs = list(runs)
        self._inspect = inspect or {
            "hints": [{"element": "Login", "found": False}],
            "candidates": [{"role": "button", "name": "Login", "locator": NEW}],
            "aria_snapshot": "- button Login",
        }
        self.run_calls = 0
        self.inspect_calls = 0

    async def __call__(self, runner: str, path: str, body: dict, timeout: float) -> dict:
        if path == "/run":
            self.run_calls += 1
            results = self._runs[min(self.run_calls - 1, len(self._runs) - 1)]
            return {"ok": True, "results": results}
        if path == "/inspect":
            self.inspect_calls += 1
            return self._inspect
        raise AssertionError(f"unexpected path {path}")


@pytest.fixture
def patch_post(monkeypatch):
    def _install(fake: FakeRunner) -> FakeRunner:
        monkeypatch.setattr(executor, "_post", fake)
        return fake

    return _install


async def _run(fake: FakeRunner) -> dict:
    result = await executor._run_suite(
        {"router": None},  # no model: deterministic healing only
        files=FILES,
        locators=LOCATORS,
        base_url="https://example.test",
        runner_url="http://runner.test",
    )
    return result["payload"]


@pytest.mark.asyncio
async def test_heal_repairs_a_locator_and_the_rerun_passes(patch_post) -> None:
    fake = patch_post(FakeRunner([[FAIL], [PASS]]))
    payload = await _run(fake)

    assert payload["ok"] is True
    assert payload["healed"] is True
    assert len(payload["attempts"]) == 2
    assert fake.run_calls == 2
    assert fake.inspect_calls == 1

    fix = payload["auto_fixed"][0]
    assert fix["old_locator"] == OLD
    assert fix["new_locator"] == NEW
    assert fix["method"] == "deterministic"
    assert payload["manual_required"] == []


@pytest.mark.asyncio
async def test_heal_stops_when_it_cannot_improve_anything(patch_post) -> None:
    """One attempt, no change, stop — do not burn the budget on a rerun that
    would produce exactly the same failure."""
    fake = patch_post(
        FakeRunner(
            [[FAIL]],
            inspect={"hints": [{"element": "Login", "found": False}], "candidates": []},
        )
    )
    payload = await _run(fake)

    assert fake.run_calls == 1
    assert payload["auto_fixed"] == []
    assert payload["ok"] is False
    assert len(payload["manual_required"]) == 1
    assert payload["manual_required"][0]["test"] == "login"


@pytest.mark.asyncio
async def test_heal_leaves_a_working_locator_alone(patch_post) -> None:
    """If the element still resolves, nothing should be rewritten."""
    fake = patch_post(
        FakeRunner(
            [[FAIL]],
            inspect={"hints": [{"element": "Login", "found": True}], "candidates": []},
        )
    )
    payload = await _run(fake)

    assert payload["auto_fixed"] == []
    assert fake.run_calls == 1


@pytest.mark.asyncio
async def test_heal_gives_up_after_the_attempt_budget(patch_post) -> None:
    """Persistent failure must end as manual_required, never as a pass."""
    from app.core.settings import get_settings

    max_attempts = get_settings().max_heal_attempts
    # Alternate the candidate so each heal produces a real change and the loop
    # keeps going until the cap.
    alt_a = {"role": "button", "name": "Login", "locator": NEW}
    alt_b = {"role": "button", "name": "Login", "locator": 'page.getByRole("button", { name: "Login now" })'}

    class Alternating(FakeRunner):
        async def __call__(self, runner, path, body, timeout):
            if path == "/inspect":
                self.inspect_calls += 1
                cand = alt_a if self.inspect_calls % 2 else alt_b
                return {"hints": [{"element": "Login", "found": False}], "candidates": [cand]}
            return await super().__call__(runner, path, body, timeout)

    fake = patch_post(Alternating([[FAIL]]))
    payload = await _run(fake)

    assert fake.run_calls <= max_attempts
    assert payload["ok"] is False
    assert payload["manual_required"], "a persistent failure must be reported"
    # The failure must never be reported as a pass.
    assert all(r["status"] != "passed" for r in payload["results"])


@pytest.mark.asyncio
async def test_runner_unreachable_is_reported_as_an_error(patch_post, monkeypatch) -> None:
    """An unreachable runner is an operational failure, not a test failure."""
    import httpx

    async def boom(*_args, **_kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(executor, "_post", boom)
    result = await executor._run_suite(
        {"router": None},
        files=FILES,
        locators=LOCATORS,
        base_url="https://example.test",
        runner_url="http://down.test",
    )
    payload = result["payload"]
    assert payload.get("runner_unreachable") is True
    assert payload["results"] == []


@pytest.mark.asyncio
async def test_no_files_is_an_error_not_a_pass() -> None:
    result = await executor._run_suite({"router": None}, files=[], locators=[])
    assert "error" in result["payload"]


# --------------------------------------------------------------------------- #
# locator registry drift
# --------------------------------------------------------------------------- #

def test_locator_registry_matches_the_generated_saucedemo_bundle() -> None:
    """The heal loop targets locators by name and expression. If codegen's
    templates and the registry drift apart, healing silently edits nothing —
    so the drift is a test failure, not a runtime surprise."""
    from app.engines.codegen import _build_framework
    from app.engines.locator_map import for_kit, verify

    cases = [{"title": "Login flow for saucedemo", "type": "positive", "criterion_id": "AC-01"}]
    _tests, root = _build_framework(cases, "http://www.saucedemo.com")
    assert verify(for_kit("saucedemo"), root) == []


def test_locator_registry_matches_the_generated_generic_bundle() -> None:
    from app.engines.codegen import _build_framework
    from app.engines.locator_map import for_kit, verify

    cases = [{"title": "Checkout works", "type": "positive", "criterion_id": "AC-01"}]
    _tests, root = _build_framework(cases, "https://shop.example.com")
    page_file = next(
        p for p in root if p.endswith(".page.ts") and "base.page" not in p
    )
    assert verify(for_kit("generic", page_file), root) == []
