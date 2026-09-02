"""
Central configuration for Undrift.

Every value comes from environment variables (loaded from the project-root
.env file in local development). Nothing sensitive is ever hardcoded here —
the .env file is gitignored and only .env.example, with empty values, is
committed.
"""

from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/app -> backend -> <project root>
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database -------------------------------------------------------
    # SQLite for local dev, a real Postgres URL in production.
    database_url: str = "sqlite:///./undrift.db"

    # --- GitHub ingestion ----------------------------------------------
    github_token: str = ""
    # Optional pinned list, e.g. "owner/repo-a,owner/repo-b".
    # When left empty we auto-discover the token owner's repositories.
    github_repos: str = ""
    # How many of the most recently pushed repos to ingest per profile.
    max_repos: int = 10
    # Ceiling on commits stored per repo. Every new commit costs one Claude
    # call, so this is the main lever on how much a sync run costs.
    max_commits_per_repo: int = 40

    # --- Profiles ---------------------------------------------------------
    # Public GitHub accounts seeded as demo data, comma-separated. They are
    # flagged is_sample in the database so the dashboard can label them as
    # samples rather than implying their work is the owner's.
    sample_profiles: str = ""
    # Only ingest commits newer than this. Two years gives the decay curve
    # enough history to actually show something fading.
    commit_lookback_days: int = 730

    # --- LLM skill tagging ----------------------------------------------
    anthropic_api_key: str = ""
    # Classification is the easy end of what an LLM does: pick one label from
    # a fixed list given a filename list. Haiku answers it as well as Opus for
    # a fraction of the price, and price is the whole ballgame once strangers
    # can trigger a sync from the public site.
    anthropic_model: str = "claude-haiku-4-5"
    # How many commits go into a single classification call. One call per
    # commit spends most of its tokens re-sending the same system prompt; at
    # 25 per call that overhead is amortised ~25x. Raising this further starts
    # to hurt accuracy, because the model has to hold more context per answer.
    tagger_batch_size: int = 25
    # Hard ceiling on commits classified in one refresh. This is the spend
    # stop: whatever else goes wrong -- a runaway backfill, someone pointing
    # us at a 10,000-commit account -- a single run cannot cost more than this
    # many commits' worth of tokens. Leftovers get tagged on the next run.
    max_commits_per_tag_run: int = 600

    # --- Auth ------------------------------------------------------------
    app_username: str = ""
    app_password: str = ""
    # Serve sample profiles over GET without credentials, so the deployed link
    # opens on a working dashboard instead of a login wall. Only profiles
    # flagged is_sample are ever exposed this way; the owner's own history
    # still needs the password above. Set false to make the whole API private.
    public_demo: bool = True


    # --- Frontend / CORS --------------------------------------------------
    # Comma-separated list of origins allowed to call the API. In production
    # this is the Vercel URL; locally it's the Vite dev server.
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Decay algorithm --------------------------------------------------
    # Days for a single commit's weight to fall to half its original value.
    # 60 days is a deliberate choice: short enough that a skill you dropped
    # last quarter visibly fades, long enough that a two-week holiday doesn't
    # tank your scores. See scoring.py for the full explanation.
    decay_half_life_days: float = 60.0

    # --- Scheduling -------------------------------------------------------
    # Hours between automatic refresh runs by the in-process scheduler.
    refresh_interval_hours: int = 12
    # Set false on hosts that sleep (Render free tier) and drive refreshes
    # from the GitHub Actions cron instead.
    enable_scheduler: bool = True

    @property
    def tracked_repos(self) -> List[str]:
        """Parse GITHUB_REPOS into a clean list. Empty list = auto-discover."""
        return [r.strip() for r in self.github_repos.split(",") if r.strip()]

    @property
    def sample_usernames(self) -> List[str]:
        """Parse SAMPLE_PROFILES into a clean list."""
        return [u.strip() for u in self.sample_profiles.split(",") if u.strip()]

    @property
    def normalized_database_url(self) -> str:
        """
        Neon/Render/Supabase hand out URLs starting with `postgres://`, but
        SQLAlchemy 2.x wants an explicit driver. Rewrite it so the same env
        var works locally and in production without anyone editing it.

        This is not cosmetic: SQLAlchemy resolves a bare `postgresql://` to
        psycopg2, which this project does not install, so the app would die
        at startup with ModuleNotFoundError instead of connecting.

        >>> Settings(database_url="postgres://u:p@h/db").normalized_database_url
        'postgresql+psycopg://u:p@h/db'
        >>> Settings(database_url="postgresql://u:p@h/db").normalized_database_url
        'postgresql+psycopg://u:p@h/db'
        >>> Settings(database_url="sqlite:///./undrift.db").normalized_database_url
        'sqlite:///./undrift.db'

        Query parameters survive, which matters because Neon appends them:

        >>> Settings(database_url="postgres://u:p@h/db?sslmode=require"
        ...          ).normalized_database_url
        'postgresql+psycopg://u:p@h/db?sslmode=require'
        """
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @property
    def cors_origins(self) -> List[str]:
        """Parse ALLOWED_ORIGINS into the list CORSMiddleware expects."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
