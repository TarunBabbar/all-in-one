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
  "criterion_id": "AC-01",          // the plan criterion this case verifies
  "module": "...",
  "title": "...",
  "type": "positive | negative | edge | e2e | security | accessibility | api | etl | visual",
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

`criterion_id` is required by the eval gates: without it a case cannot be
traced to the plan, and `Traceability` correctly fails the gate. One canonical
model fans out to every exporter (TestCaseAI pattern) and the deterministic CSV
contract is stable (Sankar pattern).

## Pipeline stages and eval gates

Every generator is followed by a deterministic eval gate. A failing gate stops
the chain naming the metric that failed, so a weak artifact cannot reach
automation:

```
intake → doctor → test_plan → eval_plan → test_cases → eval_cases
       → codegen → eval_code → run → triage → (visual) → release
```

| Gate | Scores | Metrics |
|---|---|---|
| `eval_plan` | the test plan against the requirement | CriteriaCoverage, PlanNoInvention, CategoryMatrixComplete, AmbiguityFlagged |
| `eval_cases` | the case set against the plan | PlanConformance, CategoryBalance, Traceability, StepCompleteness, CaseNoInvention |
| `eval_code` | the generated suite against the cases | CaseCoverage, GroundingTier, RunnableStructure, SpecMapping |

Metrics are deterministic (no LLM judge), so the gates run offline under
`LLM_PROVIDER=mock`. Scores are 0..1, higher is better; a gate passes only when
every metric clears its threshold.

## Self-healing runs

The executor runs the suite, and on failure re-inspects the live DOM through the
runner's `/inspect` endpoint, re-maps locators that no longer resolve, rewrites
the page objects and runs again — up to `MAX_HEAL_ATTEMPTS` (default 5).

Deterministic matching runs first (role + accessible name, test id, placeholder);
the model is consulted only when no candidate in the snapshot matches. If
healing changes nothing, the loop stops rather than repeating an identical run.

Tests still failing after the final attempt are reported in `manual_required` and
surface in the Release Report. They are never marked as passing.

## Grounding tiers (E4 codegen)

1. `unverified` — LLM-proposed selector, not checked.
2. `dom_verified` — resolved to exactly one node in the target DOM
   (QA Nexus `blast-ground`).
3. `run_verified` — assertion held against the live app in a real run.

Generated specs never claim `run_verified` until E5 proves it.
