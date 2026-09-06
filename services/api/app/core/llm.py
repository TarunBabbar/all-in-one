"""Schema-validated structured LLM output helpers.

Pattern traced to: AI QA Detective (Zod-validated LLM responses with one
auto-retry), QAGenX (every module = Zod schema pipeline), Sankar's generator
(deterministic output contract). The trust rule from the hackathon doctrine:
the model proposes structured JSON, deterministic code validates and disposes.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Raised when every provider attempt fails or output is invalid."""


class LLMProvider(ABC):
    """One provider abstraction. Subclasses implement chat with JSON output."""

    name: str = "base"

    @abstractmethod
    async def complete_json(
        self, system: str, prompt: str, schema: type[T], max_retries: int = 1
    ) -> T: ...

    @abstractmethod
    async def complete_text(self, system: str, prompt: str, max_retries: int = 1) -> str: ...


class MockProvider(LLMProvider):
    """Deterministic offline provider. Returns canned valid JSON for tests/demo.

    Pattern traced to: AI QA Detective mock (zero keys offline), TraceFix
    offline fallback, Rohit's graceful fallback, ETL Buddy template fallback.
    """

    name = "mock"

    def __init__(self, fixtures: dict[str, Any] | None = None) -> None:
        self._fixtures = fixtures or {}

    async def complete_json(
        self, system: str, prompt: str, schema: type[T], max_retries: int = 1
    ) -> T:
        for attempt in range(max_retries + 1):
            raw = self._render_fixture(schema, prompt)
            try:
                return schema.model_validate_json(raw)
            except ValidationError:
                if attempt >= max_retries:
                    raise LLMError(f"mock fixture failed {schema.__name__} validation") from None
        raise LLMError("unreachable")

    async def complete_text(self, system: str, prompt: str, max_retries: int = 1) -> str:
        return "Mock provider response. Configure a real LLM provider to get generated content."

    def _render_fixture(self, schema: type[T], prompt: str) -> str:
        """Build a fixture that passes schema validation.

        Uses any registered example for this schema, else synthesizes from
        type defaults. Deterministic — never hallucinated.
        """
        key = schema.__name__
        if key in self._fixtures:
            return json.dumps(self._fixtures[key])
        # Fall back to a model-defined deterministic example (a classmethod
        # returning a valid instance) so tests/demo run offline.
        example_fn = getattr(schema, "_mock_example", None)
        if callable(example_fn):
            return example_fn().model_dump_json()
        # Last resort: construct from field defaults.
        try:
            return schema().model_dump_json()
        except ValidationError:
            raise LLMError(f"no mock fixture registered for {key}") from None


class LLMRouter:
    """Routes to the configured provider with failover.

    Pattern traced to: TraceFix llm-router (Gemini -> OpenAI -> Groq failover),
    AI QA Detective provider-agnostic layer. For Phase 0 only the mock is wired;
    real providers arrive in Phase 1 behind the same interface.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    @classmethod
    def from_settings(cls, settings: Any) -> LLMRouter:
        provider_name = settings.llm_provider
        if provider_name == "mock":
            return cls(MockProvider())
        # Phase 1: anthropic/openai/groq/gemini/openrouter providers registered here.
        return cls(MockProvider())

    async def complete_json(
        self, system: str, prompt: str, schema: type[T], max_retries: int = 1
    ) -> T:
        return await self._provider.complete_json(system, prompt, schema, max_retries)

    async def complete_text(self, system: str, prompt: str, max_retries: int = 1) -> str:
        return await self._provider.complete_text(system, prompt, max_retries)
