# QA/One — AI QA Workspace

One platform to run your QA flow end to end — from a raw requirement to a
release verdict — plus focused tools for every step. QA/One consolidates the
capabilities of an AI QA engineer into a single hub: requirement intake,
quality diagnosis, test-case generation, Playwright codegen, sandboxed
execution, failure triage, visual + accessibility + API + ETL checks, and a
GO/NO-GO release gate.

Everything persists to Postgres (works out of the box with Neon's serverless
Postgres) and the LLM layer is provider-agnostic (Command Code / DeepSeek,
with an offline mock for development).

---

## Table of contents

- [Services](#services)
- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
  - [1. Environment (.env)](#1-environment-env)
  - [2. Database](#2-database)
  - [3. LLM provider](#3-llm-provider)
  - [4. Connectors (Jira / GitHub)](#4-connectors-jira--github)
- [Running the project](#running-the-project)
  - [Option A — Docker Compose](#option-a--docker-compose)
  - [Option B — Local dev (recommended for development)](#option-b--local-dev-recommended-for-development)
- [How to use each section](#how-to-use-each-section)
  - [Home / dashboard (`/`)](#home--dashboard-)
  - [Pipeline (`/pipeline`) — the flagship flow](#pipeline-pipeline--the-flagship-flow)
  - [Standalone tools (`/tools/*`)](#standalone-tools-tools)
  - [Settings (`/settings`) — Jira + GitHub connections](#settings-settings--jira--github-connections)
- [API reference](#api-reference)
- [Running tests](#running-tests)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)

---

## Services

| Dir | Stack | Purpose | URL |
|---|---|---|---|
| `apps/web` | Next.js 16, React 19, Tailwind v4 | Hub shell + tool pages (the UI) | http://localhost:3000 |
| `services/api` | Python FastAPI + SQLAlchemy (async) | Engines, pipeline orchestrator, connectors, REST API | http://localhost:8000 |
| `apps/runner` | Node 22 + Playwright | Sandboxed executor that runs generated Playwright suites | http://localhost:8787 |

The API needs a Postgres database (Neon recommended). The runner is only
needed when you execute generated Playwright suites in the sandbox; the rest
of the platform works without it.

---

## Features

QA/One merges **15 engines**, each covering one capability. Every engine is a
registered plugin with typed inputs/outputs, so it can run standalone (tool
page) or as a stage in the Pipeline.

| # | Engine | What it does |
|---|---|---|
| — | **Pipeline** | Chains stages end-to-end with a human **approval gate** between each (requirement → verdict) |
| E1 | **Intake** | Normalizes a raw requirement (text / URL / Jira / PRD / PDF) into a structured artifact |
| E2 | **Requirement Doctor** | Scores requirement quality (0–100), lists ambiguity/incompleteness findings, rewrites on request |
| E3 | **Test Case Generator** | Requirement → typed, prioritized test cases (functional/negative/edge/security) with a stable contract |
| E4 | **Playwright CodeGen** | Approved cases → a runnable, selector-grounding-tagged Playwright TS suite |
| E5 | **Test Runner** | Dispatches the generated suite to the sandboxed Playwright worker and returns per-test evidence |
| E6 | **Failure Triage** | Clusters failures into root causes; evidence-cited diagnoses pass a deterministic hallucination guard |
| E7 | **Visual Regression** | Compares legacy-vs-new screenshots: severity findings, match score, ship/don't-ship verdict |
| E8 | **Accessibility** | WCAG 2.0/2.1 scan of HTML: labels, contrast, keyboard traps, with concrete fixes |
| E9 | **API Tester** | Risk-scored endpoint analysis + test-gap ideas + optional live request execution |
| E10 | **ETL / Data QA** | Plain-English data rules → runnable pytest against an injected schema |
| E11 | **Release Gate** | GO/NO-GO release decision from run results + configurable criteria |
| E12 | **Defect Leakage** | Classifies post-release defects as missed/not-missed and proposes preventive tests |
| — | **RAG Explorer** | Visible retrieve-then-generate over a document (browse/edit chunks, top-K) |
| — | **Agent Security** | Validates an AI agent's tool calls against the expected path → trust score + findings |
| — | **Prompt Eval** | Golden-set prompt tests + OWASP LLM red-team attacks with pass/safe reporting |
| — | **Demo** | Seeds a sample requirement + run results so everything is exercisable offline |

### Cross-cutting trust layer

- **Approval gates** — every stage emits a reviewable artifact; nothing
  advances to the next stage until a human approves it
  (`draft → awaiting_approval → approved | changes_requested | blocked`).
- **Deterministic guardrails** — scores are recomputed locally, AI verdicts
  are validated against an evidence pack, and hallucinated citations are
  stripped before a verdict is trusted.
- **Provider-agnostic LLM** — the same engine code runs against the offline
  mock, the `cmdc` CLI, or the Command Code REST API (DeepSeek).

---

## Architecture

```
apps/web (Next.js UI)
   │  REST / JSON
services/api (FastAPI orchestrator)
   ├─ engines/       15 capability engines (registry pattern)
   ├─ pipeline/      approval state machine + Postgres store
   ├─ connectors/    Jira + GitHub REST clients
   ├─ trust/         evidence citation + verdict guard
   ├─ export/        TestCase → CSV / Jira-markdown / JSON adapters
   └─ db/            SQLAlchemy async models (Neon Postgres)
   │
   ├─ apps/runner (Playwright worker — sandboxed execution)
   └─ Postgres (projects, pipelines, stage_runs, artifacts, app_settings)
```

See `docs/architecture.md` and `docs/module-contracts.md` for detail.

---

## Prerequisites

- **Python 3.12+**
- **Node.js 22+** (the web app and runner)
- **Docker** (only for Option A — Docker Compose)
- A **Postgres** database. QA/One works out of the box with
  [Neon](https://neon.tech) serverless Postgres (free tier is fine), or any
  local Postgres. If you leave `DATABASE_URL` unset, the API falls back to a
  local SQLite file (no install needed).
- Optional: a **Command Code API key** (for the DeepSeek LLM path) — or run
  with `LLM_PROVIDER=mock` for fully offline deterministic behavior.
- Optional: **Jira** email + API token and a **GitHub** personal access token
  (for the connectors).

---

## Setup

### 1. Environment (.env)

```bash
cd services/api
cp .env.example .env
```

Then edit `.env` and fill in what you have. The keys are grouped:

| Group | Keys | Purpose |
|---|---|---|
| LLM | `LLM_PROVIDER`, `CMD_API_KEY`, `CMD_MODEL`, `CMD_API_BASE`, `CMDC_BIN` | Which LLM backend to use and the model id |
| DB | `DATABASE_URL` | Postgres connection string |
| Jira | `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_AUTH_MODE`, `JIRA_API_VERSION`, `JIRA_INCLUDE_COMMENTS`, `JIRA_MAX_COMMENTS`, `JIRA_TIMEOUT_SECONDS` | Jira REST connector defaults |
| GitHub | `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_BRANCH` | GitHub connector defaults |
| App | `RUNNER_URL`, `CORS_ORIGINS` | Runner address + allowed web origins |

> `.env` is gitignored — it never gets committed. Only `.env.example` (with
> blank secrets) is in the repo.

### 2. Database

Set `DATABASE_URL` in `.env` to your Postgres (Neon) string:

```
DATABASE_URL=postgresql+asyncpg://user:pass@host/db?sslmode=require
```

Tables are created automatically on API startup (see
[Troubleshooting](#troubleshooting) if you don't see them). Leave the var
unset to use a local SQLite file for quick experiments.

### 3. LLM provider

| `LLM_PROVIDER` | Behavior |
|---|---|
| `mock` (default) | Deterministic offline responses — no keys, works everywhere, used by tests |
| `cmdc` | Shells out to the authenticated `cmdc` CLI (headless `-p` mode) |
| `commandcode` | Calls the Command Code Provider REST API with `CMD_API_KEY` (DeepSeek Flash Fast by default) |

Example for the hosted REST path:

```
LLM_PROVIDER=commandcode
CMD_API_KEY=user_...
CMD_MODEL=deepseek/deepseek-v4-flash-fast
CMD_API_BASE=https://api.commandcode.ai/provider/v1
```

### 4. Connectors (Jira / GitHub)

You can set them in `.env` (boot defaults) **or** — the recommended way — in
the **Settings** page in the UI (`/settings`), which persists them to the
database so you never edit `.env` for credentials. Secrets are masked on read.

Jira needs: `JIRA_URL` (e.g. `https://your-domain.atlassian.net`), `JIRA_EMAIL`,
and a Jira API token (`JIRA_API_TOKEN`) using basic auth — the same pattern as
Atlassian's REST API.

GitHub needs: a personal access token (`GITHUB_TOKEN`) with `repo` scope and
the repo you want to push/pull (`GITHUB_REPO=owner/repo`, `GITHUB_BRANCH`).

Use the **Test connection** button on the Settings page to verify both before
using them.

---

## Running the project

### Option A — Docker Compose

```bash
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000/docs
- Runner: http://localhost:8787

The api service reads `services/api/.env` via `env_file`, so your connectors
and DB config apply inside the container too. Note: the bundled `db` service
is a local Postgres fallback; if your `.env` points at Neon, the api uses Neon
and the local `db` container is simply unused.

### Option B — Local dev (recommended for development)

Start each service in its own terminal.

**1. API** (from `services/api`):

```bash
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

(First time: `python -m venv .venv` then `.venv\Scripts\pip install -e . --group dev`.)

**2. Web** (from `apps/web`):

```bash
npm install
npm run dev
```

**3. Runner** (from `apps/runner`) — only needed for sandboxed Playwright runs:

```bash
npm install
npm run dev
```

Open http://localhost:3000. The dashboard lists recent projects; the sidebar
holds every tool.

---

## How to use each section

### Home / dashboard (`/`)

Landing hub. Shows a **Start a pipeline** call to action and a **Recent
projects** list (from the database) — click a project to reopen its pipeline.
The left sidebar lists every tool.

### Pipeline (`/pipeline`) — the flagship flow

The end-to-end QA loop with a human approval gate between every stage:

```
intake → doctor → test cases → codegen → run → triage → visual → release
```

1. Enter a **project name** and a **requirement** (leave the box empty to load
   the demo requirement), then click **Start pipeline**.
2. Walk the stages in order. For each stage click **Run stage**, review the
   generated artifact (shown as JSON), then click **Approve** to unlock the
   next stage. You can also re-run a stage after requesting changes.
3. The final **Release** stage computes GO/NO-GO from the run results and
   shows the verdict with the reason.

Stage inputs are chained automatically: the approved test cases feed the
codegen stage, the generated Playwright files feed the run stage (dispatched
to the sandboxed runner), run results feed failure triage, and run evidence
feeds the release gate.

### Standalone tools (`/tools/*`)

Each sidebar tool opens a workspace page that calls the matching engine
directly (no project needed). Give it the inputs and click **Run**:

| Tool (route) | Inputs you provide | Output |
|---|---|---|
| `/tools/intake` | Raw requirement + source hint | Normalized requirement artifact |
| `/tools/requirement-doctor` | Requirement text | Quality score + findings |
| `/tools/test-cases` | Requirement text | Typed test cases with stable IDs |
| `/tools/codegen` | Test cases (JSON) + base URL | Playwright TS suite files |
| `/tools/runner` | Suite files (JSON) + base URL | Per-test results from the sandbox |
| `/tools/failure-triage` | Run results (JSON) | Clustered, evidence-guarded root causes |
| `/tools/visual` | Diff % + findings (JSON) | Match score + ship/don't-ship verdict |
| `/tools/a11y` | HTML snippet | WCAG findings + fixes + score |
| `/tools/api-testing` | Method + URL (+ execute) | Risk score + test ideas + live result |
| `/tools/etl` | Rules + schema (JSON) | Runnable pytest tests |
| `/tools/release-gate` | Run results (JSON) | GO/NO-GO verdict + criteria evidence |
| `/tools/leakage` | Defects (JSON) | Missed/not-missed classification + preventive tests |
| `/tools/rag` | Document text + question | Chunks, retrieval, grounded answer |
| `/tools/agent-security` | Expected path + actual trace (JSON) | Trust score + severity findings |
| `/tools/prompt-eval` | Test rows (JSON) | Pass/safe report + attack results |

JSON fields accept a JSON array/object — the placeholder shows the shape.
`********`-style values are never required here; these are raw engine inputs.

### Settings (`/settings`) — Jira + GitHub connections

Store and verify your external connections. This is the mechanism for
connecting to your own Jira and GitHub from the UI:

1. **Jira** — enter URL, email, API token → **Test connection** shows the
   authenticated display name when it works.
2. **GitHub** — enter a personal access token, repo (`owner/repo`), branch →
   **Test connection** verifies auth and repo reachability.
3. Click **Save settings**. Values persist to the database; secret fields
   show `********` and are kept unchanged if you save with the mask intact.

Once configured, the Jira connector can fetch and normalize a real issue
(e.g. feed it into intake), and the GitHub connector can push generated files
to your repo via the Contents API.

---

## API reference

The API serves interactive docs at **http://localhost:8000/docs** (Swagger).
Main groups:

| Group | Routes |
|---|---|
| Projects | `POST /projects` · `GET /projects` · `GET /projects/{id}` |
| Pipeline | `POST /pipeline/{id}/run-stage/{stage}` · `GET /pipeline/{id}` · approve / request-changes / block per stage |
| Engines | `GET /engines` · `POST /engines/{id}/run` (standalone) |
| Artifacts | `GET /artifacts/{id}` · `GET /projects/{id}/artifacts` |
| Export | `POST /export/cases` (csv / jira / json) |
| Settings | `GET /settings` · `PUT /settings` · `GET /settings/test/jira` · `GET /settings/test/github` |
| Connectors | `POST /connectors/jira/fetch` · `POST /connectors/github/push` |
| Health | `GET /health` · `GET /health/llm` |

---

## Running tests

API (from `services/api`):

```bash
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check app tests
```

Tests run against an isolated SQLite database and the mock LLM — no external
services needed.

---

## Project structure

```
all-in-one/
├─ apps/
│  ├─ web/                  # Next.js UI (hub shell, pipeline, tools, settings)
│  └─ runner/               # Playwright sandbox worker
├─ services/
│  └─ api/                  # FastAPI orchestrator
│     ├─ app/
│     │  ├─ api/            # routes: pipeline, settings, (origins removed)
│     │  ├─ connectors/     # Jira + GitHub REST clients
│     │  ├─ core/           # settings, llm router, settings_store
│     │  ├─ db/             # async engine + ORM models
│     │  ├─ engines/        # 15 engines (registry pattern)
│     │  ├─ export/         # CSV / Jira / JSON adapters
│     │  ├─ pipeline/       # models, registry, Postgres store
│     │  └─ trust/          # guardrails, evidence schemas
│     └─ tests/
├─ docs/                    # architecture.md, module-contracts.md
├─ data/                    # gitignored local data
├─ docker-compose.yml
└─ README.md
```

---

## Troubleshooting

- **No tables in Postgres after startup** — tables are created on API
  startup (lifespan). If you started the API before the DB layer existed, run
  it once now. On Neon's pooled endpoint, `init_db` tolerates the
  create-table race (a duplicate-key error means the table already exists —
  confirm with: `SELECT tablename FROM pg_tables WHERE schemaname='public'`).
- **`connect() got an unexpected keyword argument 'sslmode'`** — the Neon
  connection string carries `sslmode=require&channel_binding=require`, which
  asyncpg rejects. QA/One strips those and passes `ssl="require"` via
  connect_args automatically — make sure you're on the latest code.
- **Engines return mock/deterministic output** — that is correct when
  `LLM_PROVIDER=mock`. Set it to `commandcode` (or `cmdc`) with a key in
  `.env` to get real LLM-generated content.
- **Test connection fails on GitHub** — the token needs `repo` scope and the
  repo must be `owner/repo`. Jira needs an API token (not your password) from
  https://id.atlassian.com/manage-profile/security/api-tokens.
- **Ports** — web uses 3000, api 8000, runner 8787. Change `CORS_ORIGINS` in
  `.env` if you run the web app elsewhere.
