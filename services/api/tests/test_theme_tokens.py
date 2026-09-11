"""Theme token completeness.

Themes work by redefining tokens: every surface reads `var(--…)`, so a theme is
only correct if it redefines *all* of them. Miss one and that value silently
inherits from the default dark theme — a light theme with a dark shadow, or a
Nord accent on a black page. The failure is visual and easy to miss in review,
which is exactly the kind of thing a test should hold.

Parsed with a regex rather than a CSS parser: the file is hand-written and the
shape is uniform, so a parser dependency would be more machinery than the check
is worth.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GLOBALS_CSS = REPO_ROOT / "apps" / "web" / "app" / "globals.css"

# Geometry and type are deliberately constant across themes, so they are not
# expected to appear in a theme block.
CONSTANT_PREFIXES = ("--font-", "--r-", "--ease-")

REQUIRED_THEMES = {"paper", "nord", "contrast"}

pytestmark = pytest.mark.skipif(
    not GLOBALS_CSS.exists(), reason="web app not present in this checkout"
)


def _block(css: str, selector: str) -> str:
    """The body of the first `selector { ... }` rule."""
    match = re.search(
        re.escape(selector) + r"\s*\{(.*?)\n\}",
        css,
        re.DOTALL,
    )
    assert match, f"no rule found for {selector!r}"
    return match.group(1)


def _custom_props(block: str) -> set[str]:
    return set(re.findall(r"(--[a-z0-9-]+)\s*:", block))


@pytest.fixture(scope="module")
def css() -> str:
    return GLOBALS_CSS.read_text(encoding="utf-8")


def _themable(props: set[str]) -> set[str]:
    return {p for p in props if not p.startswith(CONSTANT_PREFIXES)}


def test_root_defines_the_themable_tokens(css: str) -> None:
    root = _themable(_custom_props(_block(css, ":root")))
    # Sanity: the parse actually found the token set, rather than an empty block
    # quietly satisfying every equality check below.
    assert len(root) >= 30, f"expected a full token set, found {sorted(root)}"
    assert "--accent" in root and "--bad-soft" in root and "--shadow-lg" in root


def test_every_theme_block_exists(css: str) -> None:
    for theme in REQUIRED_THEMES:
        assert f'html[data-theme="{theme}"]' in css, f"theme {theme!r} is not defined"


@pytest.mark.parametrize("theme", sorted(REQUIRED_THEMES))
def test_theme_redefines_every_themable_token(css: str, theme: str) -> None:
    root = _themable(_custom_props(_block(css, ":root")))
    block = _custom_props(_block(css, f'html[data-theme="{theme}"]'))

    missing = sorted(root - block)
    assert not missing, (
        f"theme {theme!r} does not redefine {missing}. Those tokens would "
        "silently inherit from the default dark theme."
    )


@pytest.mark.parametrize("theme", sorted(REQUIRED_THEMES))
def test_theme_does_not_redefine_geometry(css: str, theme: str) -> None:
    """Radii, fonts and motion are identity-independent by design — a theme that
    overrides them would shift layout, not just colour."""
    block = _custom_props(_block(css, f'html[data-theme="{theme}"]'))
    forbidden = sorted(p for p in block if p.startswith(CONSTANT_PREFIXES))
    assert not forbidden, f"theme {theme!r} redefines geometry: {forbidden}"


def test_default_theme_is_not_behind_an_attribute(css: str) -> None:
    """The default must live on :root so a user who never opens Settings is
    unaffected. A `data-theme="dark"` block would mean the default only applies
    once JS has run."""
    assert 'html[data-theme="dark"]' not in css
