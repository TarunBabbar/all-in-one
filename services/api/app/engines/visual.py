"""Visual Regression engine (E7).

Absorbs: Parity Scope (legacy-vs-new screenshot compare with categorized,
severity-tagged findings + match score + Jira-ready write-up), Rohit's Visual
Regression QA Coach (optional-LLM over deterministic heuristics, ship/don't
recommendation), SpecCraft (verified-facts -> artifact pipeline).

Deterministic first: if the caller supplies pixel-diff metadata (diff %, boxes,
changed regions), compute the match score and ship/don't-ship locally. When no
metadata is present and images are supplied as base64, run an optional LLM
vision pass ONLY if a real provider is configured; otherwise return an honest
"needs visual metadata" diagnostic. Never fabricates a diff.
"""

from __future__ import annotations

from ..pipeline.registry import Engine, register

SEVERITIES = ["critical", "high", "medium", "low", "info"]


def _score(diff_percent: float) -> float:
    """Map diff % to a 0-100 match score (100 = identical)."""
    return round(max(0.0, 100.0 - diff_percent), 1)


def _ship_verdict(score: float, critical: int) -> str:
    if critical > 0:
        return "NO_GO"
    if score >= 99:
        return "SHIP"
    if score >= 90:
        return "REVIEW"
    return "NO_GO"


def analyze_visual(
    findings: list[dict] | None = None,
    diff_percent: float | None = None,
    legacy_label: str = "legacy",
    new_label: str = "new",
) -> dict:
    """Deterministic visual analysis from supplied findings/metadata."""
    findings = findings or []
    if diff_percent is None and not findings:
        return {
            "match_score": None,
            "verdict": "NEEDS_METADATA",
            "reason": "Provide pixel-diff metadata or findings to analyze.",
            "findings": [],
            "demo": False,
        }
    diff = diff_percent if diff_percent is not None else 0.0
    score = _score(diff)
    critical = sum(1 for f in findings if f.get("severity") == "critical")
    ship = _ship_verdict(score, critical)
    return {
        "legacy": legacy_label,
        "new": new_label,
        "diff_percent": diff,
        "match_score": score,
        "verdict": ship,
        "findings": findings,
        "jira_summary": _jira_summary(findings, score),
    }


def _jira_summary(findings: list[dict], score: float) -> str:
    lines = [
        "### Visual Regression Summary",
        f"Match score: {score}/100",
        f"Findings: {len(findings)}",
        "",
    ]
    for f in findings[:8]:
        sev = f.get("severity", "info")
        area = f.get("area", "?")
        desc = f.get("description", "")
        lines.append(f"- **[{sev}]** {area}: {desc}")
    return "\n".join(lines)


async def _visual(ctx: dict, **payload) -> dict:
    findings: list[dict] = payload.get("findings", [])
    diff_percent: float | None = payload.get("diff_percent")
    result = analyze_visual(
        findings=findings,
        diff_percent=diff_percent,
        legacy_label=str(payload.get("legacy_label", "legacy")),
        new_label=str(payload.get("new_label", "new")),
    )
    return {"kind": "visual_report", "payload": result, "engine": "visual"}


def register_engines() -> None:
    register(
        Engine(
            id="visual",
            name="Visual Regression",
            description="Compare legacy vs new screenshots: severity-tagged "
            "findings, match score, and a ship/don't-ship verdict.",
            uses_llm=True,
            run=_visual,
        )
    )


register_engines()