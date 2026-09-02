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

--------------------------------------------------------------------------
WHY ONE NUMBER WASN'T ENOUGH
--------------------------------------------------------------------------

Freshness alone cannot tell these two people apart:

  A. Wrote Java daily for three years, then stopped eight months ago.
  B. Touched Java twice, last week, and has never used it otherwise.

Both land near the same freshness, because freshness only asks "how recently,
how much". But the honest advice differs completely: A has a real skill going
stale and worth reviving; B never had one. Reporting them identically is the
kind of wrong answer that makes a tool untrustworthy.

So each skill now carries three numbers, and they answer different questions:

  FRESHNESS -- how recently and how heavily have you used it? Decays.
  DEPTH     -- how much evidence is there that you know it at all? Never
               decays; it is what you have banked.
  MOMENTUM  -- are you using it more or less than you were? Signed.

Person A reads low freshness, high depth, negative momentum -- "you are
losing something you paid for". Person B reads low freshness, low depth,
flat momentum -- "you never had this". Same freshness, opposite advice.

DEPTH uses the same saturating curve as freshness, on the undecayed lifetime
commit count:

    depth(skill) = 100 * n / (n + DEPTH_HALF_SATURATION)

  with DEPTH_HALF_SATURATION = 25, so twenty-five commits in a skill -- ever,
  at any age -- reads 50/100. Depth deliberately ignores dates entirely. That
  is the whole point: it is the part of the picture that going quiet cannot
  take away from you.

MOMENTUM compares the last MOMENTUM_WINDOW_DAYS against the window before it:

    momentum(skill) = 100 * (recent - prior) / (recent + prior)

  Bounded to [-100, +100], which the more obvious formula -- percentage change,
  (recent - prior) / prior -- is not: that one divides by zero the moment a
  skill is genuinely new, which is exactly when momentum is most interesting.
  Here, all-recent reads +100, all-prior reads -100 and steady reads 0.

  Momentum is reported as "unknown" rather than as a number when the two
  windows hold fewer than MOMENTUM_MIN_COMMITS between them. One commit is
  arithmetically +100 and substantively nothing.

  Counts are used raw inside each window rather than decayed. Decay within a
  30-day window is a rounding error, and mixing it in would mean momentum
  partly re-measured recency, which freshness already covers.

FORECAST inverts step 1. If no new commits arrive, today's raw weight w decays
to w * 0.5 ** (t / HALF_LIFE), so the day a skill crosses a given freshness is
a closed-form solve, not a simulation -- see `days_until_freshness`.
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

# The lifetime commit count at which DEPTH reads 50/100.
DEPTH_HALF_SATURATION = 25.0

# The comparison window for MOMENTUM: the last N days against the N before.
# 30 days is short enough to notice a skill picking up or being dropped, long
# enough that one quiet fortnight doesn't read as abandonment.
MOMENTUM_WINDOW_DAYS = 30.0

# Commits needed across both windows before momentum is reported at all.
# Three is the smallest number that can express a direction rather than a
# coin flip -- see momentum_from_counts.
MOMENTUM_MIN_COMMITS = 3

# The band boundaries the dashboard colours by, and the targets the forecast
# counts down to. They live here rather than in the frontend so "when does
# this go amber?" is answered by the same numbers that draw it amber.
FRESH_THRESHOLD = 60.0
FADING_THRESHOLD = 25.0


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


def depth_from_count(commit_count: int) -> float:
    """
    How much evidence there is that you know a skill at all. Never decays.

    >>> round(depth_from_count(0), 1)
    0.0
    >>> round(depth_from_count(25), 1)   # == DEPTH_HALF_SATURATION
    50.0
    >>> round(depth_from_count(75), 1)   # three times that
    75.0
    """
    return 100.0 * commit_count / (commit_count + DEPTH_HALF_SATURATION)


def momentum_from_counts(recent: int, prior: int) -> Optional[float]:
    """
    Whether a skill is picking up or being dropped, in [-100, +100].

    Returns None when the two windows hold fewer than MOMENTUM_MIN_COMMITS
    between them. The formula is perfectly happy to call a single commit
    "+100 momentum", but that is one commit, not a trend, and rendering it
    beside a skill genuinely accelerating off forty would be a lie of
    presentation. Below the threshold there is no answer, and the dashboard
    says so rather than inventing one.

    >>> momentum_from_counts(5, 5)      # steady
    0.0
    >>> momentum_from_counts(6, 0)      # brand new, no divide-by-zero
    100.0
    >>> momentum_from_counts(0, 6)      # dropped entirely
    -100.0
    >>> round(momentum_from_counts(9, 3), 1)   # tripled
    50.0
    >>> round(momentum_from_counts(2, 1), 1)   # just enough to report
    33.3

    Too little evidence either side to claim a direction:

    >>> momentum_from_counts(0, 0) is None
    True
    >>> momentum_from_counts(1, 0) is None
    True
    """
    total = recent + prior
    if total < MOMENTUM_MIN_COMMITS:
        return None
    return 100.0 * (recent - prior) / total


def days_until_freshness(
    raw_weight: float,
    target_freshness: float,
    half_life_days: Optional[float] = None,
) -> Optional[float]:
    """
    Days until a skill decays to `target_freshness`, assuming no new commits.

    Returns None when the skill is already at or below the target -- there is
    no future crossing to report, and answering "0 days" would imply one.

    Inverts the decay curve rather than stepping through it day by day:
    freshness `T` corresponds to a raw weight of `HALF_SATURATION * T/(100-T)`,
    and weight halves every `half_life_days`, so the answer is one logarithm.

    A skill sitting at exactly 50/100 (raw weight 3.0) takes just over three
    months to fade to 25 on the default 60-day half-life:

    >>> round(days_until_freshness(3.0, 25.0, 60), 1)
    95.1

    Twice the weight buys exactly one more half-life:

    >>> round(days_until_freshness(6.0, 25.0, 60), 1)
    155.1

    Already below the target, so there is nothing to forecast:

    >>> days_until_freshness(0.5, 25.0, 60) is None
    True
    """
    if not 0.0 < target_freshness < 100.0:
        raise ValueError("target_freshness must be strictly between 0 and 100")

    half_life = half_life_days or settings.decay_half_life_days
    target_weight = HALF_SATURATION * target_freshness / (100.0 - target_freshness)

    if raw_weight <= target_weight:
        return None
    return half_life * math.log2(raw_weight / target_weight)


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
    first_seen: Dict[str, datetime] = {}
    repos: Dict[str, set] = {}
    # Commits in the last MOMENTUM_WINDOW_DAYS, and in the window before it.
    recent_counts: Dict[str, int] = {}
    prior_counts: Dict[str, int] = {}

    for commit in commits:
        age_days = (now - commit.authored_at).total_seconds() / 86400.0
        skill = commit.skill

        raw_weights[skill] = raw_weights.get(skill, 0.0) + commit_weight(age_days)
        counts[skill] = counts.get(skill, 0) + 1
        repos.setdefault(skill, set()).add(commit.repo_id)

        if skill not in last_seen or commit.authored_at > last_seen[skill]:
            last_seen[skill] = commit.authored_at
        if skill not in first_seen or commit.authored_at < first_seen[skill]:
            first_seen[skill] = commit.authored_at

        if age_days < MOMENTUM_WINDOW_DAYS:
            recent_counts[skill] = recent_counts.get(skill, 0) + 1
        elif age_days < MOMENTUM_WINDOW_DAYS * 2:
            prior_counts[skill] = prior_counts.get(skill, 0) + 1

    scores: List[SkillScore] = []
    for skill, raw in raw_weights.items():
        last = last_seen[skill]
        scores.append(
            SkillScore(
                profile_id=profile_id,
                skill=skill,
                raw_weight=raw,
                freshness=freshness_from_weight(raw),
                depth=depth_from_count(counts[skill]),
                momentum=momentum_from_counts(
                    recent_counts.get(skill, 0), prior_counts.get(skill, 0)
                ),
                commit_count=counts[skill],
                repo_count=len(repos[skill]),
                first_commit_at=first_seen[skill],
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
