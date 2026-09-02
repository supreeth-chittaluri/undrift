"""
Undrift API -- application entrypoint.

Run locally with:
    ./.venv/bin/uvicorn app.main:app --reload --app-dir backend
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router as api_router
from .auth import BasicAuthMiddleware
from .config import settings
from .db import init_db
from .scheduler import start_scheduler, stop_scheduler


# Without this, our own log.info calls are swallowed and the hosting
# provider's log stream only shows uvicorn's request lines -- which makes it
# impossible to tell whether a scheduled refresh actually ran.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# httpx logs every GitHub API call at INFO, which is far too noisy.
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables and start the background refresh timer on startup."""
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Undrift",
    description="Tracks which of my skills are staying fresh and which are decaying.",
    version="0.1.0",
    lifespan=lifespan,
)

# Order matters. Starlette runs the most recently added middleware first, so
# CORS is added last and ends up outermost -- it must answer the browser's
# preflight OPTIONS request before auth gets a chance to reject it.
app.add_middleware(BasicAuthMiddleware)

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
