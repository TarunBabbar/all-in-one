"""Schema-validated structured LLM output helpers.

Patterns traced to the 41-project doctrine "AI proposes, deterministic rules
dispose":
- AI QA Detective: provider-agnostic LLM layer, Zod-validated responses.
- QAGenX / Sankar: every module = typed schema pipeline, deterministic contract.
- VERDICT / TraceFix: the model may only reason over supplied evidence.

Providers:
- MockProvider        — deterministic offline (tests/demo, zero keys).
- CommandCodeProvider — DeepSeek (or any Command Code model) over the Command
                        Code Provider API (https://api.commandcode.ai/provider/v1,
                        OpenAI Chat Completions wire). The same key that
                        authenticates the CLI authenticates this REST API.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, TypeVar

import httpx
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


class CommandCodeProvider(LLMProvider):
    """DeepSeek (or any Command Code model) over the Command Code Provider API.

    Wire: OpenAI Chat Completions at {CMD_API_BASE}/chat/completions, authed
    with `Authorization: Bearer {CMD_API_KEY}`. Structured JSON is requested
    via response_format json_schema; output is validated with Pydantic and
    never trusted unparsed.

    Per the provider docs: DeepSeek models route to /chat/completions (the
    OpenAI-compatible route), so the model id stays deepseek/... here.
    """

    name = "commandcode"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "deepseek/deepseek-v4-flash-fast",
        api_base: str = "https://api.commandcode.ai/provider/v1",
        timeout_s: float = 120.0,
    ) -> None:
        if not api_key:
            raise LLMError("CMD_API_KEY is empty; set it in .env to use commandcode provider")
        self._api_key = api_key
        self._model = model
        self._url = f"{api_base.rstrip('/')}/chat/completions"
        self._timeout = timeout_s

    async def complete_json(
        self, system: str, prompt: str, schema: type[T], max_retries: int = 1
    ) -> T:
        last: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                text = await self._chat(system, prompt, schema=schema)
                return schema.model_validate_json(text)
            except (ValidationError, httpx.HTTPError, KeyError, ValueError) as exc:
                last = exc
                if attempt >= max_retries:
                    break
        raise LLMError(f"commandcode provider failed after retries: {last}") from last

    async def complete_text(self, system: str, prompt: str, max_retries: int = 1) -> str:
        last: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return await self._chat(system, prompt)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                last = exc
                if attempt >= max_retries:
                    break
        raise LLMError(f"commandcode provider failed after retries: {last}") from last

    async def _chat(self, system: str, prompt: str, schema: type[T] | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        if schema is not None:
            # Ask for strict JSON matching the schema.
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                    "strict": True,
                },
            }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        # OpenAI-compatible envelope.
        return data["choices"][0]["message"]["content"]


class CmdcProvider(LLMProvider):
    """DeepSeek (or any Command Code model) via the local cmdc CLI.

    Shells out to `cmdc -p "<query>" --model <model> --output-format json
    --yolo` (headless mode) and parses the trailing NDJSON result frame's
    `finalText`. Uses the authenticated cmdc session — no API key in .env
    required for this path.

    System prompt + user prompt are joined into the headless query. For
    structured output the query instructs the model to return ONLY JSON
    matching the schema; the result is then validated with Pydantic.
    """

    name = "cmdc"

    def __init__(
        self,
        *,
        bin: str = "cmdc",
        model: str = "deepseek/deepseek-v4-flash-fast",
        timeout_s: float = 180.0,
    ) -> None:
        self._bin = bin
        self._model = model
        self._timeout = timeout_s

    async def complete_json(
        self, system: str, prompt: str, schema: type[T], max_retries: int = 1
    ) -> T:
        last: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                text = await self._run(
                    system,
                    prompt,
                    json_instruction=(
                        "Return ONLY a single JSON object conforming to this "
                        f"JSON schema. No prose, no markdown fences.\n{schema.model_json_schema()}"
                    ),
                )
                return schema.model_validate_json(text)
            except (ValidationError, LLMError, ValueError) as exc:
                last = exc
                if attempt >= max_retries:
                    break
        raise LLMError(f"cmdc provider failed after retries: {last}") from last

    async def complete_text(self, system: str, prompt: str, max_retries: int = 1) -> str:
        last: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return await self._run(system, prompt)
            except (LLMError, ValueError) as exc:
                last = exc
                if attempt >= max_retries:
                    break
        raise LLMError(f"cmdc provider failed after retries: {last}") from last

    async def _run(self, system: str, prompt: str, json_instruction: str | None = None) -> str:
        import asyncio
        import os
        import shutil
        import sys

        query = f"{system}\n\n{prompt}"
        if json_instruction:
            query = f"{query}\n\n{json_instruction}"

        args = [self._bin, "-p", query, "--model", self._model,
                "--output-format", "json", "--yolo", "--skip-onboarding"]
        if sys.platform == "win32":
            # cmdc is a .cmd shim -> it just runs
            # node <dir>\node_modules\command-code\dist\index.mjs. Bypass cmd
            # entirely and exec node against that entry directly (no shell,
            # no quoting issues with paths containing spaces).
            shim = shutil.which(self._bin)
            launch: list[str] | None = None
            if shim:
                base = os.path.dirname(os.path.abspath(shim))
                entry = os.path.join(base, "node_modules", "command-code", "dist", "index.mjs")
                node = os.path.join(base, "node.exe")
                if os.path.exists(entry):
                    launch = [
                        node if os.path.exists(node) else "node",
                        entry,
                        *args[1:],
                    ]
            if launch is None:
                # Fall back to the plain exec path; if the bin is an .exe this
                # works, if it is a bare name on PATH the FileNotFoundError
                # below surfaces a clear error.
                launch = args
            proc = await asyncio.create_subprocess_exec(
                *launch,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except TimeoutError:
            proc.kill()
            raise LLMError(f"cmdc timed out after {self._timeout}s") from None

        if proc.returncode != 0:
            raise LLMError(
                f"cmdc exited {proc.returncode}: {stderr.decode(errors='replace')[:500]}"
            )

        # Parse the NDJSON stream for the final result frame.
        final_text = ""
        for line in stdout.decode(errors="replace").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                frame = json.loads(line)
            except ValueError:
                continue
            if frame.get("type") == "result":
                final_text = frame.get("finalText", "")
        if not final_text:
            raise LLMError("cmdc returned no final result frame")
        return final_text


class LLMRouter:
    """Routes to the configured provider.

    Pattern traced to: TraceFix llm-router (Gemini -> OpenAI -> Groq failover),
    AI QA Detective provider-agnostic layer. Constructed from Settings so no
    provider choice or secret is hardcoded in callers.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    @property
    def is_mock(self) -> bool:
        """True when running offline (mock provider). Engines use this to
        keep deterministic fallbacks and never hit the network in tests."""
        return self._provider.name == "mock"

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @classmethod
    def from_settings(cls, settings: Any) -> LLMRouter:
        provider_name = (settings.llm_provider or "mock").lower()
        if provider_name == "commandcode":
            return cls(
                CommandCodeProvider(
                    api_key=settings.cmd_api_key,
                    model=settings.cmd_model,
                    api_base=settings.cmd_api_base,
                )
            )
        if provider_name == "cmdc":
            return cls(
                CmdcProvider(
                    bin=settings.cmdc_bin,
                    model=settings.cmd_model,
                )
            )
        # mock (default) + unknown providers degrade safely to offline.
        return cls(MockProvider())

    async def complete_json(
        self, system: str, prompt: str, schema: type[T], max_retries: int = 1
    ) -> T:
        return await self._provider.complete_json(system, prompt, schema, max_retries)

    async def complete_text(self, system: str, prompt: str, max_retries: int = 1) -> str:
        return await self._provider.complete_text(system, prompt, max_retries)
