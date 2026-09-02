"""
Database engine and session management.

One engine, one session factory, one `get_session` dependency that FastAPI
injects into route handlers. Works against SQLite locally and Postgres in
production purely by swapping DATABASE_URL.
"""

import logging
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

log = logging.getLogger(__name__)


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


def _add_missing_columns() -> None:
    """
    Add columns that exist on the models but not yet in the database.

    `create_all()` creates missing *tables* and silently ignores tables that
    already exist -- including ones missing a column added since they were
    created. Without this, deploying a new nullable column would leave
    production querying a column that isn't there.

    This is deliberately not a migration system. It only ever ADDs nullable
    columns; it will not drop, rename, or retype anything, and it makes no
    attempt to order changes or roll them back. That covers the only schema
    change this project actually makes -- the database is a rebuildable cache
    of GitHub, so anything more complicated is still answered by dropping it
    and re-ingesting. If that ever stops being true, the answer is Alembic,
    not more code here.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all() just made it, with every column
        present = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present or not column.nullable:
                continue
            ddl_type = column.type.compile(engine.dialect)
            with engine.begin() as conn:
                conn.execute(
                    text(f'ALTER TABLE {table.name} ADD COLUMN {column.name} {ddl_type}')
                )
            log.info("Added missing column %s.%s", table.name, column.name)


def init_db() -> None:
    """Create any tables that don't exist yet, then patch in new columns."""
    from . import models  # noqa: F401  (import registers the models on Base)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


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
