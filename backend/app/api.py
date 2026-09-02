"""
Phase 5: the read API the dashboard talks to, plus the refresh trigger.

Every route is under /api. Reads come straight out of the latest stored
snapshot -- no scoring happens on the request path, so the dashboard loads
fast and always shows the same numbers the scheduler computed.
"""

from datetime import timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_session, utcnow
from .models import Commit, Profile, Repo, SkillScore, SyncRun
from .pipeline import latest_run, run_refresh
from .scoring import FADING_THRESHOLD, FRESH_THRESHOLD, days_until_freshness
from .schemas import (
    CommitOut,
    ProfileOut,
    HistoryPoint,
    SkillHistoryOut,
    SkillOut,
    StatusOut,
    SyncRunOut,
)

router = APIRouter(prefix="/api", tags=["undrift"])


def resolve_profile(session: Session, username: Optional[str]) -> Profile:
    """
    Find the profile to report on.

    With no `profile` query param we default to the owner -- the first
    non-sample profile -- so the dashboard opens on the real one rather than
    on demo data.
    """
    if username:
        profile = session.scalar(select(Profile).where(Profile.username == username))
        if profile is None:
            raise HTTPException(404, f"No tracked profile named '{username}'.")
        return profile

    profile = session.scalar(
        select(Profile).where(Profile.is_sample.is_(False)).order_by(Profile.id)
    )
    if profile is None:
        raise HTTPException(404, "No profiles have been ingested yet.")
    return profile


def _snapshot_timestamps(session: Session, profile_id: int, limit: int = 2) -> List:
    """The most recent distinct scoring-run timestamps for one profile."""
    return list(
        session.scalars(
            select(distinct(SkillScore.computed_at))
            .where(SkillScore.profile_id == profile_id)
            .order_by(SkillScore.computed_at.desc())
            .limit(limit)
        )
    )


@router.get("/profiles", response_model=List[ProfileOut])
def get_profiles(session: Session = Depends(get_session)):
    """Everyone being tracked. The dashboard uses this to build its switcher."""
    rows = session.scalars(
        select(Profile).order_by(Profile.is_sample, Profile.id)
    ).all()
    return [
        ProfileOut(
            username=p.username,
            display_name=p.display_name,
            is_sample=p.is_sample,
            commit_count=session.scalar(
                select(func.count()).select_from(Commit).where(Commit.profile_id == p.id)
            )
            or 0,
            last_synced_at=p.last_synced_at,
        )
        for p in rows
    ]


@router.get("/skills", response_model=List[SkillOut])
def get_skills(
    profile: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """
    Current freshness for every skill, highest first.

    `delta` compares each skill against the previous snapshot, which is what
    tells you whether a skill is trending toward or away from staleness.
    """
    target = resolve_profile(session, profile)
    stamps = _snapshot_timestamps(session, target.id, limit=2)
    if not stamps:
        return []

    current = session.scalars(
        select(SkillScore).where(
            SkillScore.profile_id == target.id,
            SkillScore.computed_at == stamps[0],
        )
    ).all()

    previous: Dict[str, float] = {}
    if len(stamps) > 1:
        previous = {
            row.skill: row.freshness
            for row in session.scalars(
                select(SkillScore).where(
                    SkillScore.profile_id == target.id,
                    SkillScore.computed_at == stamps[1],
                )
            )
        }

    def forecast(raw_weight: float, target: float) -> Optional[float]:
        """Days until this skill decays past `target`, rounded for display."""
        days = days_until_freshness(raw_weight, target)
        return round(days, 1) if days is not None else None

    out = [
        SkillOut(
            skill=row.skill,
            freshness=round(row.freshness, 2),
            depth=round(row.depth, 2) if row.depth is not None else None,
            momentum=round(row.momentum, 2) if row.momentum is not None else None,
            raw_weight=round(row.raw_weight, 4),
            commit_count=row.commit_count,
            repo_count=row.repo_count,
            first_commit_at=row.first_commit_at,
            last_commit_at=row.last_commit_at,
            days_since_last=round(row.days_since_last, 1),
            delta=(
                round(row.freshness - previous[row.skill], 2)
                if row.skill in previous
                else None
            ),
            days_until_fading=forecast(row.raw_weight, FRESH_THRESHOLD),
            days_until_stale=forecast(row.raw_weight, FADING_THRESHOLD),
        )
        for row in current
    ]
    out.sort(key=lambda s: s.freshness, reverse=True)
    return out


@router.get("/skills/history", response_model=List[SkillHistoryOut])
def get_history(
    weeks: int = Query(26, ge=1, le=104),
    profile: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """Freshness over time per skill -- the data behind the trend chart."""
    target = resolve_profile(session, profile)
    cutoff = utcnow() - timedelta(weeks=weeks)
    rows = session.scalars(
        select(SkillScore)
        .where(
            SkillScore.profile_id == target.id,
            SkillScore.computed_at >= cutoff,
        )
        .order_by(SkillScore.computed_at.asc())
    ).all()

    series: Dict[str, List[HistoryPoint]] = {}
    for row in rows:
        series.setdefault(row.skill, []).append(
            HistoryPoint(date=row.computed_at, freshness=round(row.freshness, 2))
        )

    # Most-recently-fresh skills first, so the chart legend matches the bars.
    return sorted(
        [SkillHistoryOut(skill=k, points=v) for k, v in series.items()],
        key=lambda s: s.points[-1].freshness,
        reverse=True,
    )


@router.get("/commits", response_model=List[CommitOut])
def get_commits(
    limit: int = Query(50, ge=1, le=200),
    skill: Optional[str] = None,
    profile: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """Recent commits and how they were tagged -- the evidence behind a score."""
    target = resolve_profile(session, profile)
    query = (
        select(Commit, Repo.full_name)
        .join(Repo, Commit.repo_id == Repo.id)
        .where(Commit.profile_id == target.id)
        .order_by(Commit.authored_at.desc())
        .limit(limit)
    )
    if skill:
        query = query.where(Commit.skill == skill)

    return [
        CommitOut(
            sha=commit.sha,
            repo=repo_name,
            profile=target.username,
            message=commit.message.splitlines()[0] if commit.message else "",
            authored_at=commit.authored_at,
            skill=commit.skill,
            skill_confidence=commit.skill_confidence,
            skill_reason=commit.skill_reason,
            tag_source=commit.tag_source,
        )
        for commit, repo_name in session.execute(query)
    ]


@router.get("/status", response_model=StatusOut)
def get_status(session: Session = Depends(get_session)):
    """Counts and last-run info, so the dashboard can show the data is live."""

    def count(model, *where):
        return session.scalar(select(func.count()).select_from(model).where(*where)) or 0

    run = latest_run(session)
    return StatusOut(
        total_profiles=count(Profile),
        total_repos=count(Repo),
        total_commits=count(Commit),
        tagged_commits=count(Commit, Commit.skill.is_not(None)),
        llm_tagged_commits=count(Commit, Commit.tag_source == "llm"),
        distinct_skills=session.scalar(
            select(func.count(distinct(Commit.skill))).where(Commit.skill.is_not(None))
        )
        or 0,
        half_life_days=settings.decay_half_life_days,
        scheduler_enabled=settings.enable_scheduler,
        # Which profiles this instance will actually refresh. If a profile
        # exists in the database but is missing here, its data is frozen --
        # exactly the silent failure that SAMPLE_PROFILES being unset causes.
        tracked_usernames=sorted(settings.sample_usernames),
        last_run=SyncRunOut.model_validate(run, from_attributes=True) if run else None,
    )


@router.post("/refresh", response_model=SyncRunOut)
def refresh(
    trigger: str = Query("manual", pattern="^(manual|cron|scheduler)$"),
    session: Session = Depends(get_session),
):
    """
    Run the full pipeline now: ingest, tag, score.

    This exists so the GitHub Actions cron has something to hit. It is not the
    primary way data gets refreshed -- the scheduler and the cron are -- but a
    manual trigger is useful when demoing.
    """
    run = run_refresh(session, trigger=trigger)
    return SyncRunOut.model_validate(run, from_attributes=True)
