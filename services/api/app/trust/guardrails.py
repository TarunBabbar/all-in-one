"""Guardrails package — deterministic rules that constrain AI output.

Patterns traced to the 41-project doctrine "AI proposes, deterministic rules
dispose": VERDICT's G-rules hallucination guard, TraceFix fingerprint
clustering, Gap Analyzer's local score recompute. Phase 0 ships the schema
foundation; rule engines arrive with their modules in Phase 1.
"""

from .schemas import (
    ConfidenceScore,
    EvidenceCitation,
    GuardedVerdict,
    VerdictStatus,
    verify_verdict_guard,
)

__all__ = [
    "ConfidenceScore",
    "EvidenceCitation",
    "GuardedVerdict",
    "VerdictStatus",
    "verify_verdict_guard",
]
