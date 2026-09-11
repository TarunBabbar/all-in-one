"""Requirement Check engine (E2).

Pattern source: Khan Bilal's AI Requirement Doctor — score requirement quality
0-100 with severity-tagged findings, let the user confirm fixes, then produce an
enhanced, testable rewrite. The Gap Analyzer pattern applies: the score is
RECOMPUTED in local deterministic code, never trusted to the model's arithmetic.

This is a lint pass over the requirement, not a diagnosis — the display name
says so. Two matching rules matter and both were once wrong:

  - markers match on WORD BOUNDARIES. A substring test made "support" fire on
    "supports", "some" on "something", "fast" on "breakfast" — vague-word
    detection that reported words the requirement never used.
  - an explicit "Acceptance Criteria" section IS an acceptance signal. The rule
    only looked for should/must/shall/when/if, so a requirement listing seven
    numbered criteria was scored "unverifiable" for lacking a modal verb.
"""

from __future__ import annotations

import re

from ..core.llm import LLMRouter
from ..pipeline.registry import Engine, register
from ..trust.schemas import ConfidenceScore

# --- local deterministic quality rules (always run, no LLM) ---

# Vague terms that make a requirement unverifiable. Matched case-insensitively
# on word boundaries, so a marker only fires on the word itself.
AMBIGUITY_MARKERS = [
    "etc",
    "and so on",
    "as soon as possible",
    "asap",
    "quickly",
    "fast",
    "user-friendly",
    "easy",
    "some",
    "many",
    "few",
    "various",
    "appropriate",
    "better",
    "improved",
    "handle",
    "support",
]

# An explicit criteria section is the strongest acceptance signal there is.
_CRITERIA_HEADING = re.compile(
    r"acceptance\s+(?:criteria|tests?|conditions?)|given\s*[:\-]|expected\s+behaviou?r",
    re.IGNORECASE,
)

# Modal / conditional verbs that imply a testable condition.
_CRITERIA_MODAL = re.compile(r"\b(should|must|shall|when|if)\b", re.IGNORECASE)


def _ambiguity_hits(text: str) -> list[str]:
    """Markers present as whole words, in list order.

    A per-marker regex rather than one alternation so we can report which
    marker matched, and so a longer phrase ("as soon as possible") is never
    shadowed by a shorter one inside it.
    """
    return [
        marker
        for marker in AMBIGUITY_MARKERS
        if re.search(rf"\b{re.escape(marker)}\b", text, re.IGNORECASE)
    ]


class QualityRule:
    """One deterministic finding rule: id, severity, score penalty."""

    def __init__(self, rule_id: str, severity: str, penalty: int, message: str) -> None:
        self.id = rule_id
        self.severity = severity  # critical | high | medium | low
        self.penalty = penalty
        self.message = message

    def as_finding(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity,
            "penalty": self.penalty,
            "message": self.message,
        }


def _word_count(text: str) -> int:
    return len([w for w in text.split() if any(c.isalnum() for c in w)])


def run_deterministic_analysis(text: str) -> dict:
    """Local rules: length, acceptance criteria presence, ambiguity markers.

    Score starts at 100; each finding subtracts its penalty. Floor 0.
    Mirrors Gap Analyzer's 'score recomputed locally, never trusted to model'.
    """
    findings: list[dict] = []
    words = _word_count(text)

    if words < 20:
        findings.append(
            QualityRule(
                "REQ_TOO_SHORT",
                "critical",
                40,
                "Requirement is very short (<20 words). Likely incomplete.",
            ).as_finding()
        )
    if words < 50:
        findings.append(
            QualityRule(
                "REQ_BRIEF",
                "high",
                15,
                "Requirement is brief (<50 words). Consider more detail.",
            ).as_finding()
        )

    # Acceptance signal: an explicit criteria section, or a modal/conditional
    # verb. The heading check matters — a requirement can state its criteria
    # plainly without ever using "should" or "must".
    if not (_CRITERIA_HEADING.search(text) or _CRITERIA_MODAL.search(text)):
        findings.append(
            QualityRule(
                "REQ_NO_CRITERIA",
                "high",
                25,
                "No acceptance criteria found. Add a criteria section, or state "
                "the conditions with should/must/when/if. Acceptance is unverifiable.",
            ).as_finding()
        )

    for marker in _ambiguity_hits(text):
        findings.append(
            QualityRule(
                "REQ_AMBIGUOUS",
                "medium",
                5,
                f"Ambiguous term present: '{marker}'. Define it precisely.",
            ).as_finding()
        )

    # A marker fires at most once per requirement, so a repeated vague word
    # cannot stack penalties.
    seen = set()
    deduped: list[dict] = []
    for f in findings:
        key = f["id"] + f["message"]
        if key not in seen:
            seen.add(key)
            deduped.append(f)

    score = max(0, 100 - sum(f["penalty"] for f in deduped))
    return {
        "text": text,
        "word_count": words,
        "quality_score": score,
        "findings": deduped,
    }


async def run_doctor(
    router: LLMRouter,
    *,
    text: str,
    user_fixes: list[str] | None = None,
) -> dict:
    """Diagnose, then (optionally) enhance. Deterministic first; LLM optional.

    Deterministic rules always run locally (score never trusted to the model
    — Gap Analyzer pattern). When a real provider is configured and fixes are
    requested, the LLM writes the enhanced requirement grounded in the
    accepted fixes. On mock (offline) a template rewrite is used so the
    pipeline is fully exercisable without keys.
    """
    analysis = run_deterministic_analysis(text)
    if not user_fixes:
        return {"diagnosis": analysis, "enhanced_text": None}

    fixes = "\n".join(f"- {f}" for f in user_fixes)
    if router.is_mock:
        enhanced = (
            f"ENHANCED REQUIREMENT (deterministic draft)\n\n{text}\n\n"
            f"Accepted refinements:\n{fixes}\n"
            f"Confidence: {ConfidenceScore(score=analysis['quality_score'])}"
        )
    else:
        # Real LLM path: DeepSeek (commandcode) rewrites, grounded in the
        # accepted fixes, never inventing requirements beyond them.
        system = (
            "You are a QA requirements analyst. Rewrite the requirement to "
            "resolve the user's accepted refinements. Only use facts present "
            "in the original text and the listed fixes. Never invent new "
            "behavior. Return plain text, no markdown headers."
        )
        prompt = f"REQUIREMENT:\n{text}\n\nACCEPTED REFINEMENTS:\n{fixes}"
        enhanced = await router.complete_text(system, prompt)

    return {"diagnosis": analysis, "enhanced_text": enhanced}


async def _engine_doctor(ctx: dict, **payload) -> dict:
    """Engine entrypoint. ctx carries router/store/project_id."""
    router: LLMRouter = ctx["router"]
    text: str = payload.get("text", "")
    fixes: list[str] | None = payload.get("user_fixes")
    result = await run_doctor(router, text=text, user_fixes=fixes)
    # Store the deterministic analysis as the artifact payload.
    return {
        "kind": "doctor_report",
        "payload": {
            "diagnosis": result["diagnosis"],
            "enhanced_text": result["enhanced_text"],
            "engine": "requirement-doctor",
        },
    }


def register_engines() -> None:
    register(
        Engine(
            id="requirement-doctor",
            name="Check Requirement",
            description="Score requirement quality against deterministic rules "
            "and list the findings, then produce an enhanced rewrite on request.",
            uses_llm=True,
            run=_engine_doctor,
        )
    )


register_engines()
