"""
Database engine and session management.

One engine, one session factory, one `get_session` dependency that FastAPI
injects into route handlers. Works against SQLite locally and Postgres in
production purely by swapping DATABASE_URL.
"""

from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Parent class every ORM model inherits from."""


def _engine_kwargs() -> dict:
    """SQLite needs one extra flag; Postgres wants connection recycling."""
    if settings.normalized_database_url.startswith("sqlite"):
        # FastAPI serves requests on a threadpool, and SQLite otherwise
        # refuses connections created on a different thread.
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True, "pool_recycle": 300}


engine = create_engine(settings.normalized_database_url, **_engine_kwargs())
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session and always closes it."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Create any tables that don't exist yet."""
    from . import models  # noqa: F401  (import registers the models on Base)

    Base.metadata.create_all(bind=engine)


def utcnow() -> datetime:
    """
    Current time as a NAIVE datetime in UTC.

    Undrift stores every timestamp as naive-UTC. SQLite cannot store timezone
    offsets at all, so mixing aware and naive values would make local dev and
    production behave differently and would raise on every comparison. One
    rule -- "everything in the database is UTC, without a tzinfo" -- keeps the
    decay math simple and identical on both backends.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
