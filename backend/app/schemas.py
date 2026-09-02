"""Response shapes for the API. Keeping them explicit means the frontend has a
contract it can rely on, and FastAPI documents them at /docs for free."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ProfileOut(BaseModel):
    username: str
    display_name: Optional[str]
    is_sample: bool
    commit_count: int
    last_synced_at: Optional[datetime]


class SkillOut(BaseModel):
    skill: str
    # The three axes. Freshness decays, depth doesn't, momentum is signed.
    # See scoring.py for why one number wasn't enough.
    freshness: float
    depth: Optional[float]
    momentum: Optional[float]
    raw_weight: float
    commit_count: int
    repo_count: Optional[int]
    first_commit_at: Optional[datetime]
    last_commit_at: Optional[datetime]
    days_since_last: float
    # Change in freshness since the previous snapshot -- the "trending toward
    # or away from staleness" signal. None when there's no earlier snapshot.
    delta: Optional[float] = None
    # Days until this skill decays past the "fading" and "stale" thresholds if
    # no new commits arrive. None means it is already past that line.
    days_until_fading: Optional[float] = None
    days_until_stale: Optional[float] = None


class HistoryPoint(BaseModel):
    date: datetime
    freshness: float


class SkillHistoryOut(BaseModel):
    skill: str
    points: List[HistoryPoint]


class CommitOut(BaseModel):
    sha: str
    repo: str
    profile: str
    message: str
    authored_at: datetime
    skill: Optional[str]
    skill_confidence: Optional[float]
    # The classifier's own one-line justification, so the dashboard can show
    # why a commit was counted toward a skill instead of asking for trust.
    skill_reason: Optional[str]
    tag_source: Optional[str]


class SyncRunOut(BaseModel):
    id: int
    trigger: str
    started_at: datetime
    finished_at: Optional[datetime]
    repos_synced: int
    commits_ingested: int
    commits_tagged: int
    skills_scored: int
    status: str
    error: Optional[str]


class StatusOut(BaseModel):
    total_profiles: int
    total_repos: int
    total_commits: int
    tagged_commits: int
    llm_tagged_commits: int
    distinct_skills: int
    half_life_days: float
    # Deployment config, echoed back so a misconfigured instance is
    # diagnosable from the API instead of only from the host's dashboard.
    scheduler_enabled: bool
    tracked_usernames: List[str]
    last_run: Optional[SyncRunOut]
