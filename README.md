# QA/One — AI QA Workspace

One platform to run your QA flow end to end — requirement diagnosis, test
generation, Playwright execution, failure triage, and release decisions.

## Services

| Dir | Stack | Purpose |
|---|---|---|
| `apps/web` | Next.js 16, React 19, Tailwind v4 | Hub shell + tool pages |
| `apps/runner` | Node 22, Playwright | Sandboxed test executor worker |
| `services/api` | Python FastAPI | Orchestrator, engines, trust layer |

## Quick start

```bash
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000/docs
- Runner: http://localhost:8787

## Local development

```bash
# API (from services/api)
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# Web (from apps/web)
npm run dev
```

Copy `services/api/.env.example` to `services/api/.env` and fill in your
Command Code API key + Neon Postgres URL (or run on the mock LLM + SQLite).

## Docs

See `docs/architecture.md` for the service design and engine model.
