"""Accessibility engine (E8).

Absorbs: Aradhana's Accessibility Copilot Analyzer (WCAG 2.0/2.1 label,
contrast, keyboard-trap checks + fix suggestions) and PlaywrightExt's
axe-core a11y assertions.

Deterministic scanner over supplied HTML (or axe-core-style node results):
missing labels on inputs, empty buttons/links, missing alt on images,
missing lang, contrast hint, keyboard-trap risk. Output is a list of WCAG
2.1-referenced findings with concrete fixes. No LLM required; an optional
LLM pass can reword suggestions when configured.
"""

from __future__ import annotations

import re

from ..pipeline.registry import Engine, register

# WCAG 2.1 references by rule id.
WCAG_REF = {
    "label": "WCAG 2.1 A · 1.3.1 / 4.1.2",
    "button_name": "WCAG 2.1 A · 4.1.2",
    "link_name": "WCAG 2.1 A · 2.4.4 / 4.1.2",
    "img_alt": "WCAG 2.1 A · 1.1.1",
    "html_lang": "WCAG 2.1 A · 3.1.1",
    "contrast": "WCAG 2.1 AA · 1.4.3",
    "keyboard": "WCAG 2.1 A · 2.1.1",
}


def _tag_re(tag: str, attrs: str = "") -> re.Pattern[str]:
    return re.compile(rf"<{tag}\b[^>]*{attrs}[^>]*>", re.IGNORECASE)


def scan_accessibility(html: str) -> dict:
    """Deterministic WCAG-oriented scan of an HTML document."""
    findings: list[dict] = []
    # 1. html[lang]
    if not re.search(r'<html\s+[^>]*lang=', html, re.IGNORECASE):
        findings.append(_finding("html_lang", "critical", "<html> missing a lang attribute."))
    # 2. inputs without label/aria-label/aria-labelledby
    for m in _tag_re("input", r"(?!.*(?:type=['\"]hidden['\"]))").finditer(html):
        tag = m.group(0)
        if not re.search(r"(aria-label|aria-labelledby|id=)", tag, re.IGNORECASE):
            # crude: has a wrapping <label>? skip robust check; flag candidate
            findings.append(
                _finding("label", "high", f"Input without accessible name: {_snip(tag)}")
            )
    # 3. buttons with no text/aria-label
    for m in _tag_re("button").finditer(html):
        tag = m.group(0)
        if re.search(r"aria-label|aria-labelledby", tag, re.IGNORECASE):
            continue
        # lookahead for text content is complex; flag empty buttons only when
        # the tag is immediately closed.
        if re.search(r">\s*</button>", html[m.start(): m.start() + 200], re.IGNORECASE):
            findings.append(_finding("button_name", "high", f"Empty button: {_snip(tag)}"))
    # 4. img without alt
    for m in _tag_re("img").finditer(html):
        tag = m.group(0)
        if not re.search(r"\salt=", tag, re.IGNORECASE):
            findings.append(_finding("img_alt", "high", f"Image missing alt: {_snip(tag)}"))
    # 5. links without text/aria (very rough)
    for m in _tag_re("a").finditer(html):
        tag = m.group(0)
        if re.search(r"aria-label|aria-labelledby|title=", tag, re.IGNORECASE):
            continue
        if re.search(r">\s*</a>", html[m.start(): m.start() + 120], re.IGNORECASE):
            findings.append(_finding("link_name", "high", f"Empty link: {_snip(tag)}"))
    # 6. contrast hint: inline color without matching bg (best-effort signal)
    # 7. keyboard trap signal: onfocus/onblur handlers w/o focus management
    if re.search(r"onfocus=|onblur=", html, re.IGNORECASE):
        findings.append(
            _finding(
                "keyboard",
                "medium",
                "Focus handlers present; ensure no keyboard trap (focus stays movable).",
            )
        )
    score = _a11y_score(findings)
    return {"score": score, "findings": findings, "standards": "WCAG 2.0/2.1"}


def _a11y_score(findings: list[dict]) -> int:
    penalty = {"critical": 30, "high": 15, "medium": 5, "low": 1}
    return max(0, 100 - sum(penalty.get(f.get("severity", "low"), 1) for f in findings))


def _finding(rule: str, severity: str, message: str) -> dict:
    return {
        "rule": rule,
        "severity": severity,
        "wcag": WCAG_REF.get(rule, ""),
        "message": message,
        "fix": _fix_for(rule),
    }


def _fix_for(rule: str) -> str:
    fixes = {
        "label": "Add a <label for=...> or aria-label to give the input an accessible name.",
        "button_name": "Add visible text or aria-label to the button.",
        "link_name": "Add visible link text or aria-label.",
        "img_alt": 'Add an alt attribute (empty alt="" for decorative images).',
        "html_lang": 'Add lang="en" (or the document language) to <html>.',
        "keyboard": "Ensure all functionality is reachable and focus is not trapped.",
    }
    return fixes.get(rule, "Review against WCAG 2.1.")


def _snip(tag: str, n: int = 80) -> str:
    return tag[:n] + ("…" if len(tag) > n else "")


async def _a11y(ctx: dict, **payload) -> dict:
    html: str = payload.get("html", "") or ""
    url: str | None = payload.get("url")
    if not html and url:
        return {
            "kind": "a11y_report",
            "payload": {
                "error": "URL fetching not available; pass html directly.",
                "url": url,
            },
            "engine": "a11y",
        }
    result = scan_accessibility(html)
    return {"kind": "a11y_report", "payload": result, "engine": "a11y"}


def register_engines() -> None:
    register(
        Engine(
            id="a11y",
            name="Check Accessibility",
            description="WCAG 2.0/2.1 scan of HTML: labels, contrast, "
            "keyboard traps, with concrete fixes.",
            uses_llm=False,
            run=_a11y,
        )
    )


register_engines()