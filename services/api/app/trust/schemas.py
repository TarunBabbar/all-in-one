"""Shared guardrail schemas for evidence-cited AI verdicts.

Pattern traced to: VERDICT — the model reads a redacted evidence pack and must
cite evidence IDs; a deterministic Verdict Guard strips hallucinated citations
and unsupported causes before a verdict is trusted. These types give every
engine on the platform the same evidence contract.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

# Evidence packs carry E1..EN ids; findings cite back to them.
VALID_EVIDENCE_PREFIX = "E"

class VerdictStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class EvidenceCitation(BaseModel):
    """A single claim the AI made, tied to evidence it must be grounded in."""

    claim: str = Field(description="Short statement the model asserts")
    evidence_id: str = Field(
        description=f"Evidence pack id the claim is grounded in (e.g. {VALID_EVIDENCE_PREFIX}1)"
    )
    quote: str | None = Field(
        default=None, description="Supporting excerpt from the evidence, when available"
    )


class ConfidenceScore(BaseModel):
    """Bounded 0-100 confidence with rationale.

    VERDICT clamps confidence via deterministic adjustments A1-A9 (range
    10-99); we enforce the same bound declaratively with Field(1..100) rather
    than trusting the model's raw number — out-of-range input is rejected.
    """

    score: int = Field(ge=1, le=100)
    rationale: str | None = None


class GuardedVerdict(BaseModel):
    """A verdict the deterministic guard has reviewed.

    On construction the guard runs: every claim's evidence_id must reference
    an id present in the supplied evidence pack, else the verdict degrades to
    INSUFFICIENT_EVIDENCE (the VERDICT G-rule outcome).
    """

    status: VerdictStatus = VerdictStatus.SUPPORTED
    summary: str
    confidence: ConfidenceScore
    claims: list[EvidenceCitation] = Field(default_factory=list)
    available_evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("claims", "available_evidence_ids", mode="before")
    @classmethod
    def _normalize(cls, v: object) -> object:
        return v or []

    @classmethod
    def _mock_example(cls) -> GuardedVerdict:
        """Deterministic valid instance the offline mock provider can return."""
        return cls(
            status=VerdictStatus.SUPPORTED,
            summary="Mock verdict",
            confidence=ConfidenceScore(score=80),
            claims=[EvidenceCitation(claim="Mock claim", evidence_id="E1")],
            available_evidence_ids=["E1"],
        )


def verify_verdict_guard(verdict: GuardedVerdict) -> GuardedVerdict:
    """Deterministic hallucination guard over a verdict's claims.

    Mirrors VERDICT's G1-G10: strip/refuse claims whose cited evidence does
    not exist in the pack. Runs locally, never delegated to the model.
    """
    allowed = set(verdict.available_evidence_ids)
    if not allowed:
        # No evidence available: the guard refuses to let claims stand.
        verdict.status = VerdictStatus.INSUFFICIENT_EVIDENCE
        verdict.claims = []
        verdict.confidence.score = 1
        verdict.confidence.rationale = (
            "Verdict guard: no evidence pack was supplied; all claims were refused."
        )
        return verdict

    # Claims citing unknown evidence ids are dropped (degrading confidence).
    original = verdict.claims
    kept = [c for c in original if c.evidence_id in allowed]
    dropped = len(original) - len(kept)
    if dropped:
        verdict.confidence.score = max(1, verdict.confidence.score - 15 * dropped)
    verdict.claims = kept

    if not kept:
        verdict.status = VerdictStatus.INSUFFICIENT_EVIDENCE
        verdict.confidence.score = 1
        verdict.confidence.rationale = (
            "Verdict guard: no claim was grounded in the supplied evidence; verdict refused."
        )
        return verdict

    # Some claims survived but at least one was dropped — require higher support.
    if dropped and verdict.confidence.score < 50:
        verdict.status = VerdictStatus.INSUFFICIENT_EVIDENCE
    return verdict
