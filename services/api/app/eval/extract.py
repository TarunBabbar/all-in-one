"""Deterministic extraction helpers for the eval gates.

Everything here is pure text/number work — no model, no network. The metrics
in `metrics.py` are only as trustworthy as these helpers, so each one is
written to be explainable: if it scores something, a human can read why.
"""

from __future__ import annotations

import re
from typing import Any

# Words that carry no signal when comparing requirement text to generated text.
# Kept deliberately small — an aggressive stoplist hides real omissions.
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "then", "than", "that",
        "this", "these", "those", "is", "are", "was", "were", "be", "been",
        "to", "of", "in", "on", "at", "by", "for", "with", "from", "as", "it",
        "its", "into", "so", "such", "not", "no", "do", "does", "did", "has",
        "have", "had", "will", "would", "can", "could", "should", "must",
        "shall", "may", "might", "i", "we", "you", "they", "he", "she",
    }
)

_BULLET = re.compile(r"^\s*(?:[-*•·]|\d+[.)])\s+(.*\S)\s*$")
_MODAL = re.compile(r"\b(should|must|shall|can|will|when|if|after|before)\b", re.I)
_CRITERIA_HEAD = re.compile(r"acceptance\s+criteria|acceptance\s+tests?|criteria\s*:", re.I)
_WORD = re.compile(r"[a-z0-9]+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")

# Interaction, chrome and task-narration vocabulary. These carry no domain
# claim, so they must not count towards "invented scope": "perform the action
# with valid input" asserts nothing, while "authenticate via the corporate LDAP
# directory" asserts a great deal. Without this list every legitimately phrased
# step looks like a hallucination, and the metric would flag everything until
# it became useless.
UI_VOCAB = frozenset(
    {
        # interaction
        "open", "click", "tap", "navigate", "go", "visit", "enter", "type", "fill",
        "submit", "press", "select", "set", "wait", "verify", "check", "assert",
        "confirm", "ensure", "expect", "see", "view", "display", "shown", "show",
        # chrome
        "page", "screen", "form", "field", "button", "link", "element", "input",
        "app", "application", "site", "website", "browser", "url", "step", "steps",
        "using", "then", "given", "when", "should", "must", "and", "with",
        # task narration — describes how a step is performed, not what is tested
        "perform", "performs", "performing", "action", "actions", "behave",
        "behaves", "behaviour", "behavior", "valid", "correct", "incorrect",
        "expected", "result", "results", "outcome", "sequence", "order",
        "first", "second", "next", "again", "repeat", "attempt", "attempts",
        # standard test techniques — methodology, not domain behaviour
        "drive", "minimum", "maximum", "boundary", "boundaries", "limit",
        "limits", "extreme", "extremes", "range", "empty", "both",
    }
)

# Vocab and stopwords are compared against *stems* (see `_stem` below), so they
# are stemmed once here rather than on every comparison.


# --------------------------------------------------------------------------- #
# text primitives
# --------------------------------------------------------------------------- #

def _stem(word: str) -> str:
    """Conservative suffix stripping, so "errors" matches "error".

    Without this, a case that says "a clear error is shown" is flagged as
    invented against a requirement that says "handles invalid input without
    errors" — a plural, not a different concept. Deliberately narrow: it only
    strips regular English inflections and refuses to touch short words, so it
    cannot merge genuinely different terms.
    """
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


_STOP_STEMS = frozenset(_stem(w) for w in _STOPWORDS)
_UI_STEMS = frozenset(_stem(w) for w in UI_VOCAB)


def normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return " ".join(_WORD.findall((text or "").lower()))


def tokens(text: str) -> set[str]:
    """Content-bearing word stems only."""
    return {
        _stem(w)
        for w in _WORD.findall((text or "").lower())
        if w not in _STOPWORDS and len(w) > 1
    }


def flatten(value: Any) -> str:
    """Render any nested artifact value to a single searchable string."""
    parts: list[str] = []
    _collect(value, parts)
    return " ".join(parts)


def _collect(value: Any, out: list[str]) -> None:
    if value is None:
        return
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, bool):
        out.append(str(value))
    elif isinstance(value, (int, float)):
        out.append(str(value))
    elif isinstance(value, dict):
        for k, v in value.items():
            out.append(str(k))
            _collect(v, out)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _collect(item, out)


def coverage(
    needles: list[str], haystack_text: str, *, ratio: float = 0.6
) -> tuple[int, list[str]]:
    """Fraction of `needles` that appear in `haystack_text`.

    A needle counts as found when at least `ratio` of its content words are
    present. Requiring every word would fail on harmless rewording ("the user
    logs in" vs "a user is able to log in"); requiring none would never fail.
    Returns (found_count, missing_needles).
    """
    hay = tokens(haystack_text)
    if not hay:
        return 0, list(needles)
    found = 0
    missing: list[str] = []
    for needle in needles:
        want = tokens(needle)
        if not want:
            # Nothing comparable — treat as satisfied rather than silently fail.
            found += 1
            continue
        hit = len(want & hay) / len(want)
        if hit >= ratio:
            found += 1
        else:
            missing.append(needle)
    return found, missing


def as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def distinctive(text: str) -> set[str]:
    """Domain words in `text` — stop words and UI chrome removed.

    This is what "invented scope" is measured on: the boilerplate around a step
    should not decide whether the step is grounded, and a step that reduces to
    pure boilerplate makes no claim that could be invented.
    """
    return {
        _stem(w)
        for w in _WORD.findall((text or "").lower())
        if _stem(w) not in _STOP_STEMS
        and _stem(w) not in _UI_STEMS
        and len(w) > 2
    }


def ungrounded_claims(claims: list[str], source_text: str, *, ratio: float = 0.34) -> list[str]:
    """Claims whose distinctive vocabulary is absent from the source.

    Returns [] when every claim is either grounded or reduces to boilerplate.
    """
    source = distinctive(source_text)
    out: list[str] = []
    for claim in claims:
        want = distinctive(claim)
        if not want:
            continue  # pure navigation — nothing to invent
        if len(want & source) / len(want) < ratio:
            out.append(claim)
    return out


def s(value: Any) -> str:
    """Safe string from an arbitrary field."""
    return value if isinstance(value, str) else ("" if value is None else str(value))


# --------------------------------------------------------------------------- #
# requirement parsing
# --------------------------------------------------------------------------- #

def split_requirement_criteria(text: str) -> list[str]:
    """Deterministically derive the criteria a requirement states.

    Three passes, most explicit first:
      1. an "Acceptance Criteria" heading followed by bullets
      2. any bulleted lines anywhere in the text
      3. sentences carrying a modal verb (should/must/when/if/…)

    Returns [] when the requirement genuinely states none, which the plan gate
    treats as "nothing to cover" rather than a pass.
    """
    raw = text or ""
    lines = [ln.rstrip() for ln in raw.splitlines()]

    start: int | None = None
    for i, line in enumerate(lines):
        if _CRITERIA_HEAD.search(line):
            start = i + 1
            break

    if start is not None:
        out: list[str] = []
        for line in lines[start:]:
            m = _BULLET.match(line)
            if m:
                out.append(m.group(1))
            elif line.strip() and out:
                break  # the criteria section ended
        if out:
            return _dedupe(out)

    bullets = [m.group(1) for line in lines if (m := _BULLET.match(line))]
    if bullets:
        return _dedupe(bullets)

    sentences = [p.strip() for p in _SENTENCE.split(raw) if p.strip()]
    modal = [p for p in sentences if _MODAL.search(p)]
    return _dedupe(modal)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        key = normalize(it)
        if key and key not in seen:
            seen.add(key)
            out.append(it.strip())
    return out


def is_multi_step(text: str) -> bool:
    """Does this criterion imply a flow rather than a single interaction?"""
    t = (text or "").lower()
    markers = ("then", "after", "before", "step", "flow", "navigate", "redirect",
               "followed by", "next", "and then")
    return any(m in t for m in markers)


# --------------------------------------------------------------------------- #
# artifact field access (defensive — payload shapes vary by engine)
# --------------------------------------------------------------------------- #

def plan_criteria(plan: dict) -> list[dict]:
    """Criteria declared by a test-plan artifact."""
    items = plan.get("criteria") or plan.get("test_criteria") or []
    out: list[dict] = []
    for i, item in enumerate(as_list(items), start=1):
        if isinstance(item, dict):
            out.append(
                {
                    "id": s(item.get("id")) or f"AC-{i:02d}",
                    "text": s(item.get("text") or item.get("criterion") or item.get("title")),
                    "categories": [s(c).lower() for c in as_list(item.get("categories"))],
                }
            )
        elif isinstance(item, str):
            out.append({"id": f"AC-{i:02d}", "text": item, "categories": []})
    return out


def case_records(cases: list) -> list[dict]:
    """Normalized view over a test-case artifact."""
    out: list[dict] = []
    for i, item in enumerate(as_list(cases), start=1):
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "id": s(item.get("id")) or f"TC-{i:04d}",
                "title": s(item.get("title")),
                "type": s(item.get("type")).lower(),
                "priority": s(item.get("priority")),
                "severity": s(item.get("severity")),
                "criterion_id": s(item.get("criterion_id") or item.get("criterion")),
                "preconditions": [s(p) for p in as_list(item.get("preconditions"))],
                "steps": [s(p) for p in as_list(item.get("steps"))],
                "expected": s(item.get("expected")),
                "automation_rec": s(item.get("automation_rec")).lower(),
                "_raw": item,
            }
        )
    return out


def spec_files(code: dict) -> dict[str, str]:
    """path -> source for every generated file in a codegen artifact."""
    out: dict[str, str] = {}
    bundle = code.get("bundle")
    if isinstance(bundle, dict):
        for path, source in bundle.items():
            if isinstance(source, str):
                out[str(path)] = source
    files = code.get("files")
    if isinstance(files, dict):
        for entries in files.values():
            for entry in as_list(entries):
                if isinstance(entry, dict):
                    name = s(entry.get("name"))
                    content = s(entry.get("content"))
                    if name and content:
                        out.setdefault(name, content)
    elif isinstance(files, list):
        for entry in files:
            if isinstance(entry, dict):
                name = s(entry.get("name"))
                content = s(entry.get("content"))
                if name and content:
                    out.setdefault(name, content)
    return out


def case_ids_in_source(source: str) -> set[str]:
    """TC ids referenced by a generated spec."""
    return {m.group(0).upper() for m in re.finditer(r"TC-\d{3,4}", source or "", re.I)}
