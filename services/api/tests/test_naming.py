"""Naming contract between the web nav and the engine registry.

Engine names live in the API and are read by the UI, so the two cannot disagree
about what a tool is *called*. What can still drift is the join itself: a tool
declared in the sidebar whose id is not a registered engine would render as a
humanized id — "Requirement Doctor" style guesswork — with no error anywhere.

That is the same class of bug as an eval gate looking its metrics up under a
name that does not exist: silently wrong, and invisible until someone reads the
screen. These tests make it loud.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.engines import modules as _engine_modules  # noqa: F401
from app.pipeline import registry

# services/api/tests/ -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS_TS = REPO_ROOT / "apps" / "web" / "lib" / "tools.ts"
STAGES_TS = REPO_ROOT / "apps" / "web" / "lib" / "stages.ts"

pytestmark = pytest.mark.skipif(
    not TOOLS_TS.exists(), reason="web app not present in this checkout"
)


def _tools_source() -> str:
    return TOOLS_TS.read_text(encoding="utf-8")


def _tool_ids(source: str) -> list[str]:
    """Tool ids — objects that carry BOTH an id and an href, in one literal.

    Group entries also have an `id` (author, automate, …). Matching a bare
    `id:` reports five phantom missing engines, and allowing `}` but not `{`
    still lets a group match across into its first nested tool. Excluding both
    braces keeps every match inside a single object literal, and href is what
    distinguishes a routable tool from a group.
    """
    return re.findall(r'\{\s*id:\s*"([^"]+)"[^{}]*?href:', source)


def _stage_engines(source: str) -> set[str]:
    """Every `engine: "..."` literal in the stage table."""
    return set(re.findall(r'\bengine:\s*"([^"]+)"', source))


def test_every_sidebar_tool_maps_to_a_registered_engine() -> None:
    nav_ids = set(_tool_ids(_tools_source()))
    registered = {e.id for e in registry.all_engines()}

    # "pipeline" is the shell around the engines, not an engine itself.
    nav_ids.discard("pipeline")

    unknown = sorted(nav_ids - registered)
    assert not unknown, (
        f"sidebar tools with no engine behind them: {unknown}. "
        "The nav would fall back to a guess derived from the id."
    )


def test_every_pipeline_stage_maps_to_a_registered_engine() -> None:
    stage_engines = _stage_engines(STAGES_TS.read_text(encoding="utf-8"))
    registered = {e.id for e in registry.all_engines()}

    unknown = sorted(stage_engines - registered)
    assert not unknown, f"pipeline stages with no engine behind them: {unknown}"


def test_tool_ids_are_unique() -> None:
    """A duplicate id would silently shadow a tool in the flat TOOLS list."""
    ids = _tool_ids(_tools_source())
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    assert not duplicates, f"duplicate tool ids: {duplicates}"


def test_engine_names_are_verb_phrases_or_artifact_nouns() -> None:
    """Guard the naming rule so a new engine cannot quietly reintroduce a
    metaphor or an unexplained acronym.

    A name is acceptable when it starts with an imperative verb, or is a short
    artifact noun. What is rejected is a name carrying neither — the "Doctor" /
    "Explorer" shape, which described an attitude rather than an operation.
    """
    verbs = {
        "normalize", "check", "plan", "generate", "run", "test", "cluster",
        "compare", "assess", "analyze", "query", "validate", "evaluate",
    }
    # Artifact nouns we accept as-is, with the reason they are allowed.
    nouns = {
        "demo data",  # a fixture, not an operation
    }
    banned = {"doctor", "explorer", "triage", "intake", "tester", "codegen"}

    for engine in registry.all_engines():
        name = engine.name.lower()
        first = name.split()[0]
        assert first in verbs or name in nouns, (
            f"engine {engine.id!r} is named {engine.name!r}, which starts with "
            f"neither an imperative verb nor an accepted artifact noun"
        )
        for word in banned:
            assert word not in name, (
                f"engine {engine.id!r} is named {engine.name!r}, which uses the "
                f"metaphor or jargon {word!r}"
            )
