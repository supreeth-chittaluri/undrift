"""
Phase 4: the decay / freshness algorithm.

This is plain arithmetic. No LLM is involved in deciding whether a skill is
stale -- the model only ever chose which skill a commit belongs to. That
separation is deliberate: these numbers are reproducible, and running the
scorer twice on the same data always gives the same answer.

--------------------------------------------------------------------------
THE FORMULA
--------------------------------------------------------------------------

Step 1 -- every commit decays exponentially with age.

    weight(commit) = 0.5 ** (age_in_days / HALF_LIFE)

  This is the same shape as radioactive half-life. A commit made today counts
  as 1.0. A commit made HALF_LIFE days ago counts as 0.5. Twice that age,
  0.25, and so on -- it approaches zero but never reaches it, so a skill fades
  smoothly instead of falling off a cliff on some arbitrary cutoff date.

  HALF_LIFE is 60 days by default (configurable via DECAY_HALF_LIFE_DAYS).
  That number is a judgement call: short enough that a skill you dropped last
  quarter visibly fades, long enough that a two-week holiday doesn't tank you.

Step 2 -- a skill's raw weight is the sum of its commits' weights.

    raw_weight(skill) = sum of weight(commit) for every commit tagged with it

  Summing is what folds in FREQUENCY as well as recency. One commit last week
  scores lower than ten commits last week, because ten near-1.0 weights add up.
  Recency and frequency come out of a single sum rather than needing two
  separate terms bolted together.

Step 3 -- squash the raw weight into a 0-100 score for display.

    freshness(skill) = 100 * raw_weight / (raw_weight + HALF_SATURATION)

  raw_weight is unbounded, but a progress bar needs 0-100. This curve maps 0
  to 0, rises steeply at first, and flattens as it approaches 100 -- so the
  difference between "never" and "occasionally" shows up strongly, while the
  difference between "a lot" and "a whole lot" barely moves the bar. Which is
  what you actually want: past a point, more commits don't make you sharper.

  HALF_SATURATION is 3.0, and it is the one number that gives the score its
  meaning: a skill whose decayed weight equals 3.0 -- roughly three commits
  made in the last few days -- sits at exactly 50/100.

  Note this is an ABSOLUTE scale, not a ranking. Scores are not normalised
  against your best skill. If you stop coding entirely, every bar drops toward
  zero together. Normalising would always leave something pinned at 100 and
  hide exactly the drift this app exists to show.

Deliberately NOT included: lines changed. Weighting by diff size would let one
commit that vendored a dependency outweigh a month of real work.
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import utcnow
from .models import Commit, Profile, SkillScore

log = logging.getLogger(__name__)

# The raw weight at which a skill reads 50/100. See step 3 above.
HALF_SATURATION = 3.0


def commit_weight(age_days: float, half_life_days: Optional[float] = None) -> float:
    """
    Step 1: how much a single commit still counts, given how old it is.

    >>> round(commit_weight(0, 60), 3)    # committed today
    1.0
    >>> round(commit_weight(60, 60), 3)   # one half-life ago
    0.5
    >>> round(commit_weight(120, 60), 3)  # two half-lives ago
    0.25
    """
    half_life = half_life_days or settings.decay_half_life_days
    # Commits dated slightly in the future (clock skew) are treated as "today"
    # so they can't score above 1.0.
    age_days = max(age_days, 0.0)
    return math.pow(0.5, age_days / half_life)


def freshness_from_weight(raw_weight: float) -> float:
    """
    Step 3: squash an unbounded raw weight into 0-100.

    >>> round(freshness_from_weight(0.0), 1)
    0.0
    >>> round(freshness_from_weight(3.0), 1)   # == HALF_SATURATION
    50.0
    """
    return 100.0 * raw_weight / (raw_weight + HALF_SATURATION)


def compute_scores(
    session: Session, profile_id: int, as_of: Optional[datetime] = None
) -> List[SkillScore]:
    """
    Score one profile's skills as they stood at `as_of` (default: right now).

    Scoring is always scoped to a single profile -- two people's commits must
    never be summed into one curve.

    The `as_of` parameter is what makes the trend line possible: we can replay
    the same formula at past dates using the commits that existed then, and
    see how a skill's freshness moved.

    Returns unsaved SkillScore objects; the caller decides whether to persist.
    """
    now = as_of or utcnow()

    # Only this profile's commits, tagged, and existing at `as_of`.
    commits = session.scalars(
        select(Commit).where(
            Commit.profile_id == profile_id,
            Commit.skill.is_not(None),
            Commit.authored_at <= now,
        )
    ).all()

    # Accumulate per skill in one pass.
    raw_weights: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    last_seen: Dict[str, datetime] = {}

    for commit in commits:
        age_days = (now - commit.authored_at).total_seconds() / 86400.0
        skill = commit.skill

        raw_weights[skill] = raw_weights.get(skill, 0.0) + commit_weight(age_days)
        counts[skill] = counts.get(skill, 0) + 1
        if skill not in last_seen or commit.authored_at > last_seen[skill]:
            last_seen[skill] = commit.authored_at

    scores: List[SkillScore] = []
    for skill, raw in raw_weights.items():
        last = last_seen[skill]
        scores.append(
            SkillScore(
                profile_id=profile_id,
                skill=skill,
                raw_weight=raw,
                freshness=freshness_from_weight(raw),
                commit_count=counts[skill],
                last_commit_at=last,
                days_since_last=(now - last).total_seconds() / 86400.0,
                computed_at=now,
            )
        )

    scores.sort(key=lambda s: s.freshness, reverse=True)
    return scores


def score_and_store(session: Session, as_of: Optional[datetime] = None) -> int:
    """
    Compute one snapshot per profile and save them all.

    Returns the total number of skill rows written across every profile.
    """
    total = 0
    for profile_id in session.scalars(select(Profile.id)).all():
        for score in compute_scores(session, profile_id, as_of=as_of):
            session.add(score)
            total += 1
    session.commit()
    return total


def backfill_history(session: Session, weeks: int = 26, step_days: int = 7) -> int:
    """
    Replay the formula at weekly intervals over the past `weeks` weeks.

    Without this the dashboard's trend line would be a single dot until the
    scheduler had been running for months. Because the score at any date is a
    pure function of the commits that existed by then, we can honestly
    reconstruct that history from data we already have.

    Existing snapshots are left alone, so this is safe to re-run.
    """
    # Anchor to midnight UTC, NOT to the current timestamp. The dedupe check
    # below compares exact datetimes, so if the anchor moved by a few
    # microseconds on every run -- which utcnow() does -- no generated date
    # would ever match an existing row and each run would silently append a
    # whole duplicate history. Snapping to midnight makes the dates stable.
    anchor = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    profile_ids = session.scalars(select(Profile.id)).all()

    written = 0
    for profile_id in profile_ids:
        # Dedupe per profile -- a profile added later still gets its own
        # history backfilled even though other profiles already have theirs.
        existing = set(
            session.scalars(
                select(SkillScore.computed_at).where(
                    SkillScore.profile_id == profile_id
                )
            ).all()
        )
        for week in range(weeks, 0, -1):
            as_of = anchor - timedelta(days=week * step_days)
            if as_of in existing:
                continue
            for score in compute_scores(session, profile_id, as_of=as_of):
                session.add(score)
                written += 1

    session.commit()
    log.info("Backfilled %d historical score rows", written)
    return written
