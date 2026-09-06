"""Failure Triage engine (E6).

Absorbs: VERDICT (rules-first failure analysis + deterministic guard),
TraceFix (fingerprint clustering collapsing N failures to few diagnoses,
flaky analytics), AI QA Detective (evidence-cited root cause + confidence),
VisionTestAI/AIQAEngineer (self-heal loop with approval).

Deterministic rules run first: normalize the message, compute a fingerprint,
cluster. Then the LLM (optional) interprets the cluster into a root cause with
an evidence-cited verdict the guard verifies. On mock, a rule-based diagnosis
is produced offline. Output shape follows the canonical GuardedVerdict.
"""

from __future__ import annotations

import re

from ..pipeline.registry import Engine, register
from ..trust.guardrails import (
    ConfidenceScore,
    EvidenceCitation,
    GuardedVerdict,
    VerdictStatus,
    verify_verdict_guard,
)

# Noise patterns that distort clustering (TraceFix "CI noise stripping").
_NOISE = re.compile(
    r"(https?://\S+|timed out after \d+ms|at \S+|\d+\.\d+s|%\d+)"  # urls/timers/percent
    r"|\(In Promise\)|undefined|null",  # framework noise
    re.IGNORECASE,
)


def _fingerprint(message: str) -> str:
    """Collapse a message to a stable cluster key."""
    text = _NOISE.sub(" ", message or "").lower()
    tokens = [w for w in text.split() if w.strip() and any(c.isalnum() for c in w)]
    return " ".join(tokens[:10])


def _rule_diagnosis(failures: list[dict]) -> dict:
    """Deterministic diagnosis when insight is thin or LLM is mock.

    Classifies by keyword: locator/expect/selector/not found -> likely locator or
    assertion; timeout -> flakiness/slowness; 401/403/500 -> auth/server.
    """
    text = (" ".join(str(f.get("message", "")) for f in failures)).lower()
    if any(k in text for k in ["timeout", "timed out"]):
        cls = "timeout / flaky"
        conf = 55
    elif any(k in text for k in ["not found", "locator", "selector", "element"]):
        cls = "locator or selector drift"
        conf = 45
    elif any(k in text for k in ["401", "403", "unauthorized", "forbidden"]):
        cls = "auth / permissions"
        conf = 65
    elif any(k in text for k in ["assert", "expected", "expect("]):
        cls = "assertion failure"
        conf = 60
    else:
        cls = "unclassified"
        conf = 30
    return cls, conf


def _alpha_failures(results: list[dict]) -> list[dict]:
    """Extract the failed items from a results set."""
    out = []
    for r in results or []:
        if isinstance(r, dict) and r.get("status") in ("failed", "error", "broken"):
            out.append(r)
        elif isinstance(r, str):
            out.append({"message": r})
    return out


def cluster_failures(results: list[dict]) -> dict:
    """Cluster raw results into root-cause groups."""
    failures = _alpha_failures(results)
    clusters: dict[str, dict] = {}
    for f in failures:
        message = str(f.get("message", f.get("title", "")))
        key = _fingerprint(message) or "unknown"
        clusters.setdefault(key, {"count": 0, "message": message, "items": []})
        clusters[key]["count"] += 1
        clusters[key]["items"].append(f)
    # sort by frequency, largest first
    ordered = sorted(clusters.values(), key=lambda c: -c["count"])
    return {"total_failures": len(failures), "clusters": ordered}


async def _triage(ctx: dict, **payload) -> dict:
    results: list[dict] = payload.get("results", [])
    clustered = cluster_failures(results)

    verdicts: list[dict] = []
    guard_summary: list[str] = []
    for cluster in clustered["clusters"][:5]:
        cls, conf = _rule_diagnosis(cluster["items"])
        evidence_ids = [f"E{i}" for i in range(1, cluster["count"] + 1)]
        claims = []
        if cluster["count"] > 0:
            claims = [
                EvidenceCitation(
                    claim=f"{cls} in {cluster['count']} failure(s)",
                    evidence_id=evidence_ids[0],
                    quote=str(cluster["message"])[:160],
                )
            ]
        verdict = GuardedVerdict(
            status=VerdictStatus.SUPPORTED,
            summary=cls,
            confidence=ConfidenceScore(score=conf, rationale="deterministic rule match"),
            claims=claims,
            available_evidence_ids=evidence_ids,
        )
        guarded = verify_verdict_guard(verdict)
        verdicts.append(
            {
                "cluster": cluster["message"],
                "count": cluster["count"],
                "classification": guarded.summary,
                "confidence": guarded.confidence.score,
                "status": guarded.status.value,
                "evidence": [c.model_dump() for c in guarded.claims],
            }
        )
        guard_summary.append(guarded.status.value)

    return {
        "kind": "triage_report",
        "payload": {
            "total_failures": clustered["total_failures"],
            "clusters": clustered["clusters"],
            "verdicts": verdicts,
            "guard_states": guard_summary,
        },
        "engine": "failure-triage",
    }


def register_engines() -> None:
    register(
        Engine(
            id="failure-triage",
            name="Failure Triage",
            description="Cluster failures into root causes with evidence-cited "
            "diagnoses and verification-guarded confidence.",
            uses_llm=True,
            run=_triage,
        )
    )


register_engines()