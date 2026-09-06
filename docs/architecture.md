# QA/One Architecture

The consolidated platform merges the 41 AI Tester Blueprint 3x hackathon
projects. Working title **QA/One**, code name `qahub`.

## Services

| Service | Dir | Role |
|---|---|---|
| `web` | `apps/web` | Next.js 16 App Router frontend + thin BFF. No LLM keys in browser. |
| `api` | `services/api` | Python FastAPI orchestrator. Intake, engines (E1-E12), trust layer, exports. |
| `runner` | `apps/runner` | Dockerized Playwright worker. Executes generated suites in isolation; never on the API host. |
| `db` | docker-compose | Postgres 16 (workspaces, artifacts, origins registry). |

## The merged spine

Every hackathon project converged on one loop; QA/One implements it once and
exposes each stage as an engine:

```
intake -> requirement doctor -> test cases -> grounded codegen
   -> sandboxed execution -> failure triage -> visual/a11y checks
   -> release gate -> export / defect / leakage analysis
```

with **human approval gates** between stages and an **evidence contract**
(claim -> citation -> verdict guard) on every AI output.

## Engines and their origin projects

| Engine | Merges |
|---|---|
| E1 Intake & connectors | TestCaseAI, Sankar, Paritosh, Gurpreet, RAG-Jira, QAE2E |
| E2 Requirement Doctor | Bilal, Gap Analyzer, Rekha |
| E3 Strategy & Test Cases | TestSense, Sankar, Shashank, Paritosh, Gurpreet, TestPlanBuddy, QA Nexus, SpecCraft, QAGenX, Dhanashree |
| E4 Grounded CodeGen | QA Nexus, Paritosh, VisionTestAI, SpecCraft, PlaywrightExt, AIQAEngineer |
| E5 Sandboxed Executor | QA_AI_Solution, OmnyGO, ETL Buddy, QAE2E, AIQAEngineer |
| E6 Failure Intelligence & Self-Healing | VERDICT, TraceFix, AI QA Detective, VisionTestAI, AIQAEngineer, PlaywrightExt |
| E7 Visual Regression | Parity Scope, Rohit, SpecCraft |
| E8 Accessibility | Aradhana, PlaywrightExt (axe-core) |
| E9 API Testing | Vishesh, QAGenX |
| E10 ETL / Data & Format QA | ETL Buddy, EDI |
| E11 Release Risk / GO-NO-GO | Mrutyunjay, QAE2E, AI QA Detective, Rekha |
| E12 Defect Leakage | Rohan |

See `docs/origins/` and the `/origins` UI for full per-project attribution.

## The trust layer (shared core)

- `llm_router` — provider abstraction + offline Mock (AI QA Detective pattern).
- Deterministic guardrails before/after every LLM call:
  rules-first analysis, hallucination guard, fingerprint clustering, local
  score recompute, grounding tiers, claim-check, optional-LLM fallback.
- Canonical artifact contracts (one TestCase model -> every exporter).
- Approval state machine: `draft -> awaiting_approval -> approved |
  changes_requested | blocked`.

## Data flow (execution)

1. User submits a requirement (text/PRD/URL/Jira/GitHub/PDF/screenshot).
2. `api` orchestrates engines; each emits a reviewable artifact.
3. Approved artifacts become a Playwright suite in the `runner`.
4. `runner` executes in a disposable container and streams results back.
5. Failures go through E6 (clustering + evidence-cited diagnosis + heal loop).
6. E11 composes the release decision from all run evidence.

## Phase status

- **Phase 0 (current):** monorepo, API skeleton + trust schemas + origins
  registry (41 rows), runner worker, web origins page.
- **Phase 1:** the golden path E1-E11 with real Playwright execution.
- **Phase 2:** specialist engines E8/E9/E10/E12.
- **Phase 3:** RAG Explorer, Agent/MCP Security, NL browser agent, MCP surface.
