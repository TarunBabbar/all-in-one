"""Engine registry.

Every consolidated QA capability is an Engine: a named unit with typed in/out
schemas, an optional LLM dependency, and a runnable function. The registry
drives the API routes, the sidebar tools, and the pipeline stage wiring.

Each engine is a thin dataclass describing a callable `run(ctx, **input) ->
Artifact payload`. Implementations live in `engines/` and register here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

EngineFn = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Engine:
    id: str
    name: str
    description: str
    uses_llm: bool = True
    uses_runner: bool = False
    # Called as: await engine.run(ctx, **input_payload)
    run: EngineFn | None = None


# Engines register themselves here (imported in main.py).
REGISTRY: dict[str, Engine] = {}


def register(engine: Engine) -> Engine:
    REGISTRY[engine.id] = engine
    return engine


def get_engine(engine_id: str) -> Engine | None:
    return REGISTRY.get(engine_id)


def all_engines() -> list[Engine]:
    return list(REGISTRY.values())
