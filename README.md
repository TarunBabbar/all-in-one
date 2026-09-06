# QA/One — Consolidated AI QA Platform

Merges the 41 AI Tester Blueprint 3x hackathon projects into one best-of-breed AI QA workspace.

## Services

| Dir | Stack | Purpose |
|---|---|---|
| `apps/web` | Next.js 16, React 19, Tailwind v4 | Frontend + BFF |
| `apps/runner` | Node 22, Playwright | Sandboxed test executor worker |
| `services/api` | Python 3.13 FastAPI | Orchestrator, engines, trust layer |

## Quick start

```bash
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000/docs
- Runner: http://localhost:8787

## Docs

See `docs/architecture.md` and `docs/plan.md` for the full consolidation plan.
