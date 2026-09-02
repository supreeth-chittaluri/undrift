"""
Phase 3: ask Claude which skill each commit primarily exercises.

Two design decisions worth being able to defend in an interview:

1. The model must choose from a FIXED vocabulary of skills, not invent its own
   label. If it were free to answer "Python", "python3" and "Py" on different
   commits, those would become three separate skills on the dashboard and the
   decay curve for each would be nonsense. The vocabulary is baked into the
   JSON schema as an enum, so the API itself enforces it.

2. The LLM only decides WHICH skill a commit belongs to. It is never asked
   whether a skill "feels stale" -- that is arithmetic, and it lives in
   scoring.py. Keeping the judgement call and the math separate is what makes
   the freshness numbers reproducible.

If the API key is missing, or a call fails or is refused, we fall back to a
deterministic tagger based on file extensions so the pipeline still produces
usable data instead of stalling.
"""

import logging
from typing import List, Literal, Optional

import anthropic
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import utcnow
from .models import Commit

log = logging.getLogger(__name__)

# The controlled vocabulary. Literal turns this into a JSON-schema enum, so
# the API will not return anything outside this list.
Skill = Literal[
    "Python",
    "JavaScript",
    "TypeScript",
    "React",
    "FastAPI",
    "Django/Flask",
    "SQL/Databases",
    "Data Science/ML",
    "Jupyter/Notebooks",
    "DevOps/CI",
    "Docker",
    "Testing",
    "HTML/CSS",
    "Java",
    "C/C++",
    "Go",
    "Rust",
    "Shell/Bash",
    "API Integration",
    "Documentation",
    "Config/Build",
    "Other",
]

# Same list as plain strings, for validating what comes back before we store it.
ALLOWED_SKILLS = set(Skill.__args__)


class CommitTag(BaseModel):
    """The exact JSON shape Claude must return."""

    skill: Skill = Field(description="The single skill this commit primarily exercises.")
    confidence: float = Field(
        ge=0.0, le=1.0, description="How confident you are, from 0.0 to 1.0."
    )
    reason: str = Field(
        max_length=200, description="One short sentence explaining the choice."
    )


SYSTEM_PROMPT = """You classify git commits by the single technical skill they \
primarily exercise.

You are given a commit message and the list of files it changed. The changed \
files are usually the strongest signal -- weight them more heavily than the \
commit message, which is often vague or auto-generated.

Pick exactly one skill, the dominant one. A commit that adds a FastAPI route \
touching a SQL model is "FastAPI", not "SQL/Databases", because the route is \
the point of the change. Use "Other" only when nothing else plausibly fits."""


def _build_prompt(commit: Commit) -> str:
    files = commit.files_changed or "(file list unavailable)"
    message = (commit.message or "").strip() or "(no message)"
    return (
        f"Commit message:\n{message}\n\n"
        f"Files changed:\n{files}\n\n"
        f"Lines added: {commit.additions}, removed: {commit.deletions}"
    )


# --- Deterministic fallback -------------------------------------------------

# Checked in order; first extension match wins. Deliberately coarse -- this is
# a safety net, not a competitor to the LLM.
_EXTENSION_SKILLS = [
    (".ipynb", "Jupyter/Notebooks"),
    (".tsx", "React"),
    (".jsx", "React"),
    (".ts", "TypeScript"),
    (".js", "JavaScript"),
    (".py", "Python"),
    (".sql", "SQL/Databases"),
    (".java", "Java"),
    (".go", "Go"),
    (".rs", "Rust"),
    (".sh", "Shell/Bash"),
    (".css", "HTML/CSS"),
    (".html", "HTML/CSS"),
    (".md", "Documentation"),
    ("dockerfile", "Docker"),
    (".yml", "Config/Build"),
    (".yaml", "Config/Build"),
    (".toml", "Config/Build"),
    (".json", "Config/Build"),
]


def fallback_tag(commit: Commit) -> CommitTag:
    """
    Classify from file extensions alone, no network call.

    Used when ANTHROPIC_API_KEY is unset or the API call fails, so a missing
    key degrades the quality of the tags rather than breaking the pipeline.
    """
    paths = (commit.files_changed or "").lower()
    for needle, skill in _EXTENSION_SKILLS:
        if needle in paths:
            return CommitTag(
                skill=skill, confidence=0.4, reason=f"Matched '{needle}' in changed files."
            )
    return CommitTag(skill="Other", confidence=0.2, reason="No recognisable file types.")


# --- LLM tagging ------------------------------------------------------------


def tag_commit(client: anthropic.Anthropic, commit: Commit) -> tuple[CommitTag, str]:
    """
    Classify one commit. Returns (tag, source) where source is "llm" or "fallback".

    Every failure mode -- refusal, malformed output, network error -- falls back
    to the deterministic tagger rather than raising, because one bad commit
    should never abort a scheduled ingestion run.
    """
    try:
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_prompt(commit)}],
            output_format=CommitTag,
        )

        # Safety classifiers can decline a request; that arrives as a normal
        # 200 response with stop_reason "refusal", not an exception.
        if response.stop_reason == "refusal":
            log.warning("Claude refused to classify %s; using fallback", commit.sha[:7])
            return fallback_tag(commit), "fallback"

        tag = response.parsed_output
        if tag is None:
            raise ValueError("parsed_output was empty")

        # Belt-and-braces validation. The enum in the schema should make this
        # impossible, but we check before writing to the database anyway.
        if tag.skill not in ALLOWED_SKILLS:
            raise ValueError(f"skill '{tag.skill}' is outside the vocabulary")

        return tag, "llm"

    except (anthropic.APIError, ValidationError, ValueError) as exc:
        log.warning("Tagging %s failed (%s); using fallback", commit.sha[:7], exc)
        return fallback_tag(commit), "fallback"


def tag_untagged_commits(session: Session, limit: Optional[int] = None) -> int:
    """
    Tag every commit that doesn't have a skill yet. Returns how many were tagged.

    Only untagged rows are processed, so re-running after an ingestion pass
    costs one API call per genuinely new commit and nothing for the rest.
    """
    query = select(Commit).where(Commit.skill.is_(None)).order_by(Commit.authored_at.desc())
    if limit:
        query = query.limit(limit)
    pending: List[Commit] = list(session.scalars(query))

    if not pending:
        return 0

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
    if client is None:
        log.warning("ANTHROPIC_API_KEY not set -- tagging with the fallback classifier.")

    tagged = 0
    for commit in pending:
        if client is not None:
            tag, source = tag_commit(client, commit)
        else:
            tag, source = fallback_tag(commit), "fallback"

        commit.skill = tag.skill
        commit.skill_confidence = tag.confidence
        commit.tag_source = source
        commit.tagged_at = utcnow()
        tagged += 1

    session.commit()
    return tagged
