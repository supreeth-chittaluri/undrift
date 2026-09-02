"""
Database models.

Five tables, and the whole app is explainable from them:

  profiles     -- the GitHub users we track; every score belongs to one
  repos        -- the GitHub repositories we pull from
  commits      -- one row per commit, plus the skill tag the LLM assigned it
  skill_scores -- a snapshot of one profile's skill freshness at a point in time
  sync_runs    -- a log of each automated refresh, so we can prove it's running

Undrift tracks several people at once rather than being hardwired to one
account. A "profile" is just a GitHub username; commits and scores hang off
it, so two people's decay curves never mix.

skill_scores is deliberately append-only rather than a single updated row:
keeping every snapshot is what lets the dashboard draw a trend line showing a
skill fading over time, instead of only its value right now.

All timestamps are naive UTC (see db.utcnow for why).
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow


class Profile(Base):
    """
    One person whose skills we track, identified by their GitHub username.

    `is_sample` marks the public accounts seeded purely as demo data, so the
    dashboard can label them honestly rather than implying their work is mine.
    """

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(120))
    is_sample: Mapped[bool] = mapped_column(default=False)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    commits: Mapped[List["Commit"]] = relationship(back_populates="profile")

    def __repr__(self) -> str:
        return f"<Profile {self.username}>"


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    primary_language: Mapped[Optional[str]] = mapped_column(String(64))
    is_private: Mapped[bool] = mapped_column(default=False)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    commits: Mapped[List["Commit"]] = relationship(back_populates="repo")

    def __repr__(self) -> str:
        return f"<Repo {self.full_name}>"


class Commit(Base):
    __tablename__ = "commits"

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), index=True)
    # Who wrote it. Two people committing to the same repo produce two rows
    # against two profiles, so their skill curves stay separate.
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    sha: Mapped[str] = mapped_column(String(40), unique=True, index=True)

    message: Mapped[str] = mapped_column(Text, default="")
    authored_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    # Newline-separated list of changed file paths. Stored as text because we
    # only ever feed it to the classifier -- we never query inside it.
    files_changed: Mapped[str] = mapped_column(Text, default="")
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)

    # --- filled in by the skill tagger (phase 3), null until then ---
    skill: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    skill_confidence: Mapped[Optional[float]] = mapped_column(Float)
    # The classifier's one-line justification. Storing it is what lets the
    # dashboard answer "why do you think I know FastAPI?" with the model's
    # own reasoning per commit, instead of asking the reader to trust a bar.
    skill_reason: Mapped[Optional[str]] = mapped_column(String(300))
    # "llm" when Claude classified it, "fallback" when the deterministic
    # extension-based tagger did. Worth recording so we can tell how much of
    # the dashboard is actually LLM-driven.
    tag_source: Mapped[Optional[str]] = mapped_column(String(16))
    tagged_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    repo: Mapped["Repo"] = relationship(back_populates="commits")
    profile: Mapped["Profile"] = relationship(back_populates="commits")

    def __repr__(self) -> str:
        return f"<Commit {self.sha[:7]} skill={self.skill}>"


class SkillScore(Base):
    __tablename__ = "skill_scores"
    # One row per profile per skill per scoring run.
    __table_args__ = (
        UniqueConstraint("profile_id", "skill", "computed_at", name="uq_profile_skill_run"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    skill: Mapped[str] = mapped_column(String(64), index=True)

    # 0-100, the number the dashboard bars actually render.
    freshness: Mapped[float] = mapped_column(Float)
    # The raw decayed weight before it was normalised to 0-100. Kept so the
    # math is inspectable and the normalisation isn't a black box.
    raw_weight: Mapped[float] = mapped_column(Float)

    # The other two axes. Nullable because snapshots written before these
    # existed genuinely don't have them -- an old row saying depth=0 would be
    # a claim about the person, not a gap in the record.
    depth: Mapped[Optional[float]] = mapped_column(Float)
    momentum: Mapped[Optional[float]] = mapped_column(Float)

    commit_count: Mapped[int] = mapped_column(Integer, default=0)
    # How many distinct repos the skill shows up in -- evidence spread, which
    # separates "used it across my whole portfolio" from "one weekend project".
    repo_count: Mapped[Optional[int]] = mapped_column(Integer)
    first_commit_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_commit_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    days_since_last: Mapped[float] = mapped_column(Float, default=0.0)
    computed_at: Mapped[datetime] = mapped_column(DateTime, index=True, default=utcnow)

    def __repr__(self) -> str:
        return f"<SkillScore {self.skill} {self.freshness:.1f}>"


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # "scheduler" | "cron" | "manual" -- proves automated ingestion is real.
    trigger: Mapped[str] = mapped_column(String(16), default="manual")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    repos_synced: Mapped[int] = mapped_column(Integer, default=0)
    commits_ingested: Mapped[int] = mapped_column(Integer, default=0)
    commits_tagged: Mapped[int] = mapped_column(Integer, default=0)
    skills_scored: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(16), default="running")
    error: Mapped[Optional[str]] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<SyncRun {self.id} {self.trigger} {self.status}>"
