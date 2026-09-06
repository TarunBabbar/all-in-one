"""Trust-layer guard tests.

Pattern traced to VERDICT: a deterministic guard strips hallucinated citations
before a verdict is trusted. These tests lock the guard's contract.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.trust.guardrails import (
    ConfidenceScore,
    EvidenceCitation,
    GuardedVerdict,
    VerdictStatus,
    verify_verdict_guard,
)


def test_supported_verdict_passes_guard() -> None:
    v = GuardedVerdict(
        status=VerdictStatus.SUPPORTED,
        summary="Button is misaligned",
        confidence=ConfidenceScore(score=85, rationale="E1 shows layout shift"),
        claims=[
            EvidenceCitation(claim="Button moved 4px right", evidence_id="E1"),
            EvidenceCitation(claim="Color changed", evidence_id="E2"),
        ],
        available_evidence_ids=["E1", "E2"],
    )
    result = verify_verdict_guard(v)
    assert result.status == VerdictStatus.SUPPORTED
    assert len(result.claims) == 2
    assert result.confidence.score == 85


def test_guard_strips_hallucinated_citations() -> None:
    """Claim citing E9 when only E1-E2 exist must be dropped with a penalty."""
    v = GuardedVerdict(
        status=VerdictStatus.SUPPORTED,
        summary="Some claim references missing evidence",
        confidence=ConfidenceScore(score=80),
        claims=[
            EvidenceCitation(claim="Grounded claim", evidence_id="E1"),
            EvidenceCitation(claim="Invented citation", evidence_id="E9"),  # hallucinated
        ],
        available_evidence_ids=["E1", "E2"],
    )
    result = verify_verdict_guard(v)
    assert [c.evidence_id for c in result.claims] == ["E1"]
    assert result.confidence.score < 80  # penalty applied


def test_no_grounded_claims_degrades_to_insufficient() -> None:
    v = GuardedVerdict(
        status=VerdictStatus.SUPPORTED,
        summary="Nothing is grounded",
        confidence=ConfidenceScore(score=70),
        claims=[EvidenceCitation(claim="Made up", evidence_id="E99")],
        available_evidence_ids=["E1"],
    )
    result = verify_verdict_guard(v)
    assert result.status == VerdictStatus.INSUFFICIENT_EVIDENCE
    assert result.claims == []
    assert result.confidence.score == 1


def test_no_evidence_pack_refuses_all_claims() -> None:
    v = GuardedVerdict(
        status=VerdictStatus.SUPPORTED,
        summary="Claims with no pack",
        confidence=ConfidenceScore(score=90),
        claims=[EvidenceCitation(claim="Unverifiable", evidence_id="E1")],
    )
    result = verify_verdict_guard(v)
    assert result.status == VerdictStatus.INSUFFICIENT_EVIDENCE
    assert result.claims == []
    assert result.confidence.score == 1


def test_confidence_is_rejected_outside_bounds() -> None:
    """Out-of-range confidence is rejected at validation, never silently clamped."""
    with pytest.raises(ValidationError):
        ConfidenceScore(score=150)
    with pytest.raises(ValidationError):
        ConfidenceScore(score=0)
