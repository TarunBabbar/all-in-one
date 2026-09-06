"""QA/One FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.pipeline import router as pipeline_router
from .api.settings import router as settings_router
from .core.llm import LLMRouter
from .core.settings import get_settings
from .db.core import dispose_db, init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup (Neon Postgres from .env DATABASE_URL)."""
    await init_db()
    yield
    await dispose_db()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipeline_router)
app.include_router(settings_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/health/llm")
def health_llm() -> dict[str, str]:
    router = LLMRouter.from_settings(settings)
    return {"provider": router._provider.name}  # noqa: SLF001 — introspection
