"""
Undrift API -- application entrypoint.

Run locally with:
    ./.venv/bin/uvicorn app.main:app --reload --app-dir backend
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup so a fresh clone just works."""
    init_db()
    yield


app = FastAPI(
    title="Undrift",
    description="Tracks which of my skills are staying fresh and which are decaying.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    """Liveness probe. Also reports which database backend is in use."""
    backend = "postgres" if "postgresql" in settings.normalized_database_url else "sqlite"
    return {"status": "ok", "database": backend}
