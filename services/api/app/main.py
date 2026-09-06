"""QA/One FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.origins import router as origins_router
from .core.llm import LLMRouter
from .core.settings import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(origins_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/health/llm")
def health_llm() -> dict[str, str]:
    router = LLMRouter.from_settings(settings)
    return {"provider": router._provider.name}  # noqa: SLF001 — Phase 0 introspection
