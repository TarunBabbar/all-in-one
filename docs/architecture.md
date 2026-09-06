# QA/One Architecture

An AI QA workspace: one platform where a QA engineer runs their flow end to
end — requirement in, release verdict out — plus focused tools for each step.

## Services

| Service | Dir | Role |
|---|---|---|
| `web` | `apps/web` | Next.js 16 App Router frontend. No LLM keys in browser. |
| `api` | `services/api` | Python FastAPI orchestrator. Engines, trust layer, exports. |
| `runner` | `apps/runner` | Dockerized Playwright worker. Executes generated suites in isolation; never on the API host. |
| `db` | Neon Postgres | Workspaces, projects, artifacts, runs. |

## The QA flow (pipeline)

Each stage is an engine; artifacts flow stage to stage behind human approval
gates:

```
intake -> requirement doctor -> test cases -> grounded codegen
   -> sandboxed execution -> failure triage -> visual/a11y checks
   -> release gate -> export / defect / leakage analysis
```

with **human approval gates** between stages and an **evidence contract**
(claim -> citation -> verdict guard) on every AI output.

## Engines

| Engine | Function |
|---|---|
| E1 Intake | requirement / PRD / URL / Jira / PDF / screenshot → normalized artifact |
| E2 Requirement Doctor | quality score + findings, confirm-fix-enhance |
| E3 Strategy & Test Cases | typed cases, coverage, automation rec |
| E4 Grounded CodeGen | Playwright suite with grounded selectors |
| E5 Sandboxed Executor | dispatches suites to the runner, returns per-test evidence |
| E6 Failure Intelligence | clustering, evidence-cited diagnosis, guard-verified |
| E7 Visual Regression | screenshot diff + severity findings + ship verdict |
| E8 Accessibility | WCAG 2.0/2.1 scan of HTML |
| E9 API Testing | risk-scored endpoint tests + real execution |
| E10 ETL / Data QA | English rules → runnable pytest vs injected schema |
| E11 Release Risk / GO-NO-GO | configurable criteria + evidence |
| E12 Defect Leakage | post-release missed-defect analysis |
| RAG Explorer | visible retrieve-then-generate over documents |
| Agent Security | expected-vs-actual tool-call validation + trust score |
| Prompt Eval | golden-set + OWASP red-team prompt testing |
| Demo | seeded fixtures for offline demos |

## The trust layer (shared core)

- `llm_router` — provider abstraction (Command Code Provider API, DeepSeek)
  + offline Mock. Nothing hardcoded; provider/model come from env.
- Deterministic guardrails before/after every LLM call:
  rules-first analysis, hallucination guard, fingerprint clustering, local
  score recompute, grounding tiers, claim-check, optional-LLM fallback.
- Canonical artifact contracts (one TestCase model -> every exporter).
- Approval state machine: `draft -> awaiting_approval -> approved |
  changes_requested | blocked`.

## Data flow (execution)

1. User submits a requirement (text/PRD/URL/Jira/PDF/screenshot).
2. `api` orchestrates engines; each emits a reviewable artifact.
3. Approved artifacts become a Playwright suite in the `runner`.
4. `runner` executes in a disposable container and streams results back.
5. Failures go through E6 (clustering + evidence-cited diagnosis + heal loop).
6. E11 composes the release decision from all run evidence.
