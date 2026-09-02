"""
Phase 7: run the refresh automatically, without anyone clicking anything.

Undrift uses two independent mechanisms, on purpose:

  1. APScheduler, in this process. Fires every REFRESH_INTERVAL_HOURS while
     the API is running. Simple, no external moving parts.

  2. A GitHub Actions cron (.github/workflows/refresh.yml) that POSTs to
     /api/refresh on a schedule.

Why both? Render's free tier spins a service down after ~15 minutes of
inactivity, and a sleeping process cannot run its own timer. The cron wakes
the service from outside, which is the only thing that reliably works on free
hosting. APScheduler is what keeps it current anywhere that stays awake
(local, or a paid instance). Set ENABLE_SCHEDULER=false to run cron-only.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import settings
from .db import SessionLocal
from .pipeline import run_refresh

log = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")


def scheduled_refresh() -> None:
    """The job APScheduler runs. Opens its own session -- it has no request."""
    log.info("Scheduled refresh starting")
    session = SessionLocal()
    try:
        run = run_refresh(session, trigger="scheduler")
        log.info(
            "Scheduled refresh %s: %d new commits, %d tagged",
            run.status,
            run.commits_ingested,
            run.commits_tagged,
        )
    finally:
        session.close()


def start_scheduler() -> None:
    """Start the background timer, unless it's disabled or already running."""
    if not settings.enable_scheduler:
        log.info("Scheduler disabled (ENABLE_SCHEDULER=false); relying on the cron.")
        return
    if scheduler.running:
        return

    scheduler.add_job(
        scheduled_refresh,
        trigger="interval",
        hours=settings.refresh_interval_hours,
        id="undrift-refresh",
        # If the process was asleep past a scheduled run, do one run on wake,
        # not one for every interval that was missed.
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    scheduler.start()
    log.info("Scheduler started: refreshing every %dh", settings.refresh_interval_hours)


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
