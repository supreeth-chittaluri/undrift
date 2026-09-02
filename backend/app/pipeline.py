"""
The full refresh pipeline: ingest -> tag -> score.

Everything that runs on a schedule runs through here, so there is exactly one
code path whether the trigger was the in-process scheduler, the GitHub Actions
cron, or someone hitting the endpoint by hand. Each run is recorded in the
sync_runs table so you can prove the automation is actually firing.
"""

import logging
import traceback

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import utcnow
from .ingest import ingest_commits
from .models import SyncRun
from .scoring import backfill_history, score_and_store
from .skill_tagger import tag_untagged_commits

log = logging.getLogger(__name__)


def run_refresh(session: Session, trigger: str = "manual") -> SyncRun:
    """
    Run one end-to-end refresh and return the SyncRun record describing it.

    Runs synchronously. Each stage only processes what's new -- ingestion skips
    known SHAs, tagging skips already-tagged commits -- so a routine run makes
    very few API calls even though a first run does real work.
    """
    run = SyncRun(trigger=trigger, started_at=utcnow(), status="running")
    session.add(run)
    session.commit()

    try:
        # 1. Pull any new commits from GitHub.
        counts = ingest_commits(session)
        run.repos_synced = counts["repos_synced"]
        run.commits_ingested = counts["commits_ingested"]

        # 2. Ask Claude to classify whatever is still untagged.
        run.commits_tagged = tag_untagged_commits(session)

        # 3. Recompute freshness and store a new snapshot.
        run.skills_scored = score_and_store(session)

        # 4. On a fresh database, reconstruct the trend history so the chart
        #    has something to draw. Skips dates already present, so this is a
        #    no-op on every run after the first.
        backfill_history(session)

        run.status = "ok"
    except Exception as exc:  # noqa: BLE001 - a failed run must be recorded, not crash the scheduler
        run.status = "error"
        run.error = f"{type(exc).__name__}: {exc}"
        log.error("Refresh failed: %s", traceback.format_exc())
    finally:
        run.finished_at = utcnow()
        session.commit()

    return run


def latest_run(session: Session) -> SyncRun | None:
    """The most recent refresh, for the dashboard's status line."""
    return session.scalar(select(SyncRun).order_by(SyncRun.started_at.desc()).limit(1))
