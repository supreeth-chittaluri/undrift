"""
Undrift API -- application entrypoint.

Run locally with:
    ./.venv/bin/uvicorn app.main:app --reload --app-dir backend
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router as api_router
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

# The dashboard is served from a different origin (Vercel) than the API
# (Render), so the browser needs explicit permission to call it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health() -> dict:
    """Liveness probe. Also reports which database backend is in use."""
    backend = "postgres" if "postgresql" in settings.normalized_database_url else "sqlite"
    return {"status": "ok", "database": backend}
