"""In-memory registry seeded from the 41-project list.

Phase 0 keeps the registry as an immutable in-memory seed (single workspace,
no DB needed yet). Phase 1 moves it to Postgres behind the same repository
interface when workspaces/DB land.
"""

from __future__ import annotations

from .models import Origin, Tag
from .seed import ORIGINS


class OriginRepository:
    """Read-only access to the credited 41-project registry."""

    def __init__(self, origins: list[Origin] | None = None) -> None:
        self._origins = origins if origins is not None else list(ORIGINS)

    def list_all(self) -> list[Origin]:
        return self._origins

    def get(self, rank: int) -> Origin | None:
        return next((o for o in self._origins if o.rank == rank), None)

    def by_tag(self, tag: Tag) -> list[Origin]:
        return [o for o in self._origins if tag in o.tags]

    def count(self) -> int:
        return len(self._origins)
