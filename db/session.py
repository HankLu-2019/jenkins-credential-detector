"""Database session factory."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import Session, sessionmaker


@lru_cache(maxsize=1)
def _get_engine(database_url: str) -> Engine:
    """Return a cached engine — one engine per process, shared across requests."""
    return create_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=10)


def make_session_factory(database_url: str) -> sessionmaker[Session]:
    engine = _get_engine(database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)
