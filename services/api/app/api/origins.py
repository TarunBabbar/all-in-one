"""Origins registry API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..origins.models import Origin, Tag
from ..origins.repository import OriginRepository

router = APIRouter(prefix="/origins", tags=["origins"])


def get_repo() -> OriginRepository:
    return OriginRepository()


@router.get("", response_model=list[Origin])
def list_origins(
    tag: Tag | None = Query(default=None),
    repo: OriginRepository = Depends(get_repo),
) -> list[Origin]:
    if tag:
        return repo.by_tag(tag)
    return repo.list_all()


@router.get("/count", response_model=dict[str, int])
def origin_count(repo: OriginRepository = Depends(get_repo)) -> dict[str, int]:
    return {"count": repo.count()}


@router.get("/{rank}", response_model=Origin)
def get_origin(rank: int, repo: OriginRepository = Depends(get_repo)) -> Origin:
    origin = repo.get(rank)
    if origin is None:
        raise HTTPException(status_code=404, detail=f"No origin with rank {rank}")
    return origin
