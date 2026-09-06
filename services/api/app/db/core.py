"""Async SQLAlchemy engine/session + Base.

Reads DATABASE_URL from settings (Neon Postgres in .env, sqlite fallback for
tests/dev). Tables are created on startup via init_db().
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from ..core.settings import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# Engine/session are created lazily so tests can point DATABASE_URL at a temp
# sqlite before first use.
_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        url = get_settings().database_url
        kwargs: dict = {"echo": False}
        connect_args: dict = {}
        if url.startswith("postgres"):
            kwargs["pool_pre_ping"] = True
            # asyncpg rejects sslmode=/channel_binding= query params that
            # Neon connection strings carry; pass ssl via connect_args instead.
            url = _strip_pg_query(url, "sslmode")
            url = _strip_pg_query(url, "channel_binding")
            connect_args["ssl"] = "require"
            kwargs["connect_args"] = connect_args
        _engine = create_async_engine(url, **kwargs)
    return _engine


def _strip_pg_query(url: str, key: str) -> str:
    """Remove ?key=value (or &key=value) from a URL query string."""
    base, sep, query = url.partition("?")
    if not sep:
        return url
    kept = [p for p in query.split("&") if p and not p.startswith(f"{key}=")]
    if kept:
        return f"{base}?{'&'.join(kept)}"
    return base


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db() -> None:
    """Create all tables (called from app lifespan).

    Tolerates the Neon transaction-pooler race where two pooled connections
    may both attempt CREATE TABLE for the same name; a duplicate-key error
    means the table already exists, which is fine.
    """
    from sqlalchemy.exc import IntegrityError

    from . import models  # noqa: F401  (ensure models are registered)

    try:
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except IntegrityError:
        # Pooled Neon connections can race on checkfirst; tables exist already.
        pass


async def dispose_db() -> None:
    if _engine is not None:
        await _engine.dispose()
