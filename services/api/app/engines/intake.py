"""Normalize Requirement engine (E1) — any source into a Requirement artifact.

Absorbs: TestCaseAI (Jira picker), Sankar (multi-source input), Paritosh
(requirement/URL/PRD/Jira/Confluence), Gurpreet (design docs + screenshots),
QA Nexus (URL/PDF/Jira/screen recordings), RAG-Jira, QAE2E (connector wizard).

Deterministic first: normalizes raw text/URL/JSON/YAML, strips formatting,
computes stats, and records the source type. The result is a stable
`requirement` artifact the rest of the pipeline reads.
"""

from __future__ import annotations

import re

from ..pipeline.registry import Engine, register

# Recognized source hint prefixes (e.g. "jira: PROJ-123", "url: https://...").
_SOURCE_RE = re.compile(r"^(jira|github|confluence|url|pdf|text)\s*:[\s]*(.*)$", re.IGNORECASE)


def _normalize(text: str) -> str:
    """Strip leading whitespace, collapse blank runs, trim."""
    text = text.strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def normalize_intake(raw: str, source_hint: str | None = None) -> dict:
    """Build a requirement artifact from arbitrary raw input.

    source defaults to 'text' unless a hint or prefix is given. Structure is
    always deterministic; nothing LLM is used here.
    """
    source = (source_hint or "text").lower().strip()
    # A prefix in the raw text overrides the hint (e.g. "url: https://...").
    m = _SOURCE_RE.match(raw)
    if m:
        source = m.group(1).lower()
        raw = m.group(2).strip()

    text = _normalize(raw)
    words = [w for w in text.split() if any(c.isalnum() for c in w)]
    return {
        "text": text,
        "source": source,
        "word_count": len(words),
        "char_count": len(text),
        "title": words[:8] and " ".join(words[:8]).capitalize() or "Untitled requirement",
        "normalized": True,
    }


async def _engine_intake(ctx: dict, **payload) -> dict:
    raw: str = payload.get("text", "").strip()
    source_hint: str | None = payload.get("source")
    result = normalize_intake(raw, source_hint)
    return {"kind": "requirement", "payload": result, "engine": "intake"}


def register_engines() -> None:
    register(
        Engine(
            id="intake",
            name="Normalize Requirement",
            description="Clean and structure a raw requirement from text, URL, "
            "Jira, Confluence, PRD, or PDF into a typed artifact.",
            uses_llm=False,
            run=_engine_intake,
        )
    )


register_engines()