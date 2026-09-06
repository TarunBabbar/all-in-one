"""Origins registry — credits every project absorbed into the platform.

Each row is one of the 41 participants from the AI Tester Blueprint 3x
results page. Every merged engine keeps a paper trail to the submissions that
inspired it; the /origins page renders this for attribution.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Capability tags map a project to the platform engines it informed (E1..E12
# from docs/architecture.md) or mark it OUT_OF_SCOPE (credited, not merged).
Tag = Literal[
    "intake",
    "requirement-doctor",
    "test-cases",
    "codegen",
    "execution",
    "failure-triage",
    "visual",
    "a11y",
    "api-testing",
    "etl",
    "release-gate",
    "leakage",
    "rag",
    "agent-security",
    "prompt-eval",
    "career",
    "talent",
    "unrelated",
    "unverifiable",
]


class Origin(BaseModel):
    """One hackathon submission, credited on the platform."""

    rank: int = Field(ge=1, le=41)
    name: str
    project: str
    one_liner: str
    repo: str
    live: str | None = None
    tags: list[Tag] = Field(default_factory=list)
    note: str | None = Field(
        default=None,
        description="What the platform absorbed from this project, or why it is out of scope.",
    )
