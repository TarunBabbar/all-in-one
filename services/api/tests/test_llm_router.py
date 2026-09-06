"""llm_router tests: mock provider round-trips and schema validation."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from app.core.llm import LLMError, LLMRouter, MockProvider
from app.trust.schemas import GuardedVerdict


class DemoResult(BaseModel):
    verdict: str
    score: int = Field(ge=0, le=100)


async def test_mock_provider_returns_registered_fixture() -> None:
    provider = MockProvider(fixtures={"DemoResult": {"verdict": "PASS", "score": 88}})
    router = LLMRouter(provider)
    out = await router.complete_json("sys", "prompt", DemoResult)
    assert out.verdict == "PASS"
    assert out.score == 88


async def test_mock_provider_missing_fixture_raises() -> None:
    """No fixture and no default-constructible schema => clear LLMError."""
    provider = MockProvider()
    with pytest.raises(LLMError, match="no mock fixture registered"):
        await provider.complete_json("sys", "p", DemoResult)


async def test_mock_provider_rejects_bad_fixture() -> None:
    provider = MockProvider(fixtures={"DemoResult": {"verdict": 123}})  # wrong type
    router = LLMRouter(provider)
    with pytest.raises(LLMError):
        await router.complete_json("sys", "prompt", DemoResult)


async def test_router_from_settings_defaults_to_mock() -> None:
    from app.core.settings import Settings

    router = LLMRouter.from_settings(Settings())
    assert router._provider.name == "mock"  # noqa: SLF001


async def test_guarded_verdict_mock_roundtrip() -> None:
    provider = MockProvider()
    # GuardedVerdict() default-constructs, so the mock can synthesize it.
    out = await provider.complete_json("sys", "p", GuardedVerdict)
    assert isinstance(out, GuardedVerdict)
