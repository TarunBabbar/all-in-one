"""Requirement Doctor engine (E2).

Pattern source: Khan Bilal's AI Requirement Doctor — diagnose requirement
quality with a 0-100 score and severity-tagged findings, let the user confirm
fixes, then produce an enhanced, testable rewrite. The Gap Analyzer pattern
is applied: the score is RECOMPUTED in local deterministic code, never trusted
to the model's arithmetic.
"""

from __future__ import annotations

from ..core.llm import LLMRouter
from ..pipeline.registry import Engine, register
from ..trust.schemas import ConfidenceScore

# --- local deterministic quality rules (always run, no LLM) ---

AMBIGUITY_MARKERS = [
    "etc",
    "etc.",
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

CRITICAL_MISSING_MARKERS = [
    "should",
    "must",
    "shall",
    "when",
    "if",
    "error",
    "invalid",
    "login",
    "user",
    "data",
    "save",
    "submit",
    "display",
    "delete",
    "update",
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
    lower = text.lower()
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

    # Acceptance-criteria signal: 'should/must/shall' or 'when/if' present.
    has_criteria_signal = any(m in lower for m in ["should", "must", "shall", "when", "if"])
    if not has_criteria_signal:
        findings.append(
            QualityRule(
                "REQ_NO_CRITERIA",
                "high",
                25,
                "No acceptance-criteria signal found (should/must/when/if). "
                "Acceptance is unverifiable.",
            ).as_finding()
        )

    for marker in AMBIGUITY_MARKERS:
        if marker in lower:
            findings.append(
                QualityRule(
                    "REQ_AMBIGUOUS",
                    "medium",
                    5,
                    f"Ambiguous term present: '{marker}'. Define it precisely.",
                ).as_finding()
            )

    # Dedupe identical ambiguous markers (cap at 3 findings for one marker).
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
            name="Requirement Doctor",
            description="Diagnose requirement quality with a score + findings, "
            "then produce a confirmed, enhanced rewrite.",
            uses_llm=True,
            run=_engine_doctor,
        )
    )


register_engines()
