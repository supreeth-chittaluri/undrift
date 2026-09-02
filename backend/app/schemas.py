"""Response shapes for the API. Keeping them explicit means the frontend has a
contract it can rely on, and FastAPI documents them at /docs for free."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class SkillOut(BaseModel):
    skill: str
    freshness: float
    raw_weight: float
    commit_count: int
    last_commit_at: Optional[datetime]
    days_since_last: float
    # Change in freshness since the previous snapshot -- the "trending toward
    # or away from staleness" signal. None when there's no earlier snapshot.
    delta: Optional[float] = None


class HistoryPoint(BaseModel):
    date: datetime
    freshness: float


class SkillHistoryOut(BaseModel):
    skill: str
    points: List[HistoryPoint]


class CommitOut(BaseModel):
    sha: str
    repo: str
    message: str
    authored_at: datetime
    skill: Optional[str]
    skill_confidence: Optional[float]
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
    total_repos: int
    total_commits: int
    tagged_commits: int
    llm_tagged_commits: int
    distinct_skills: int
    half_life_days: float
    last_run: Optional[SyncRunOut]
