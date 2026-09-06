# QA/One module contracts

Every engine exposes the same envelope so the orchestrator can treat engines
as interchangeable stages:

## EngineJob

```jsonc
{
  "engine": "E3_test_cases",
  "project_id": "uuid",
  "requirement_id": "uuid",
  "input_refs": ["artifact_id"],
  "state": "draft | awaiting_approval | approved | changes_requested | blocked",
  "output_artifact_ids": []
}
```

Approval gates are the QAGuard/Manish/Bilal pattern: AI writes a draft, a
human approves or requests changes, and nothing advances to automation while
`state != approved`.

## Evidence contract (all AI outputs)

```jsonc
{
  "summary": "...",
  "confidence": { "score": 0-100, "rationale": "..." },
  "claims": [{ "claim": "...", "evidence_id": "E1", "quote": "..." }],
  "available_evidence_ids": ["E1", "E2", "..."]
}
```

`verify_verdict_guard` (VERDICT G-rules) deterministically drops claims that
cite evidence not in the pack before a verdict is trusted.

## Canonical TestCase

```jsonc
{
  "id": "TC-0001",
  "requirement_id": "...",
  "module": "...",
  "title": "...",
  "type": "functional | negative | edge | security | accessibility | api | etl | visual",
  "priority": "P0 | P1 | P2 | P3",
  "severity": "critical | high | medium | low",
  "preconditions": [],
  "steps": [],
  "expected": "...",
  "automation_rec": "automate | manual | both",
  "source_evidence": ["E1"],
  "coverage_verdict": "FULL | PARTIAL | NONE | AMBIGUOUS"
}
```

One canonical model fans out to every exporter (TestCaseAI pattern) and the
deterministic CSV contract is stable (Sankar pattern).

## Grounding tiers (E4 codegen)

1. `unverified` — LLM-proposed selector, not checked.
2. `dom_verified` — resolved to exactly one node in the target DOM
   (QA Nexus `blast-ground`).
3. `run_verified` — assertion held against the live app in a real run.

Generated specs never claim `run_verified` until E5 proves it.
