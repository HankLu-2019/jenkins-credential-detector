"""FastAPI dependency injection helpers."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy.orm import Session

from db.session import make_session_factory
from scanner.config import Settings, load_settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def _get_session_factory():
    """Cached session factory — engine is created once per process."""
    return make_session_factory(get_settings().database_url)


def get_session() -> Generator[Session, None, None]:
    factory = _get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
