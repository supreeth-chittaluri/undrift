"""
Phase 2: pull commit history from GitHub into the database.

Flow:
  1. Work out which repos to track (pinned list, else auto-discover).
  2. Upsert a Repo row for each.
  3. For each repo, list the commits you authored in the lookback window.
  4. For any commit we haven't seen before, fetch its file list and store it.

Ingestion is idempotent -- commits are keyed by SHA, so re-running only ever
adds what's new. That's what makes it safe to run on a schedule.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import utcnow
from .github_client import GitHubClient, GitHubError
from .models import Commit, Repo

log = logging.getLogger(__name__)

# Cap how many files we store per commit. A giant vendored-dependency commit
# would otherwise bloat the row and blow out the classifier prompt.
MAX_FILES_PER_COMMIT = 40


def _parse_github_time(value: Optional[str]) -> datetime:
    """
    "2026-08-14T09:31:02Z" -> naive UTC datetime.

    GitHub always returns UTC with a trailing Z; we drop the tzinfo to match
    the naive-UTC convention used everywhere in the database.
    """
    if not value:
        return utcnow()
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _upsert_repo(session: Session, payload: Dict) -> Repo:
    """Insert the repo if it's new, refresh its metadata if we've seen it."""
    full_name = payload["full_name"]
    repo = session.scalar(select(Repo).where(Repo.full_name == full_name))
    if repo is None:
        repo = Repo(full_name=full_name)
        session.add(repo)
    repo.primary_language = payload.get("language")
    repo.is_private = bool(payload.get("private", False))
    session.flush()
    return repo


def resolve_repos(client: GitHubClient) -> List[Dict]:
    """
    Decide what to ingest.

    If GITHUB_REPOS is set we honour that exact list. Otherwise we discover
    the token owner's most recently pushed repos, so the app keeps working
    when you start a new project without anyone editing config.
    """
    pinned = settings.tracked_repos
    if pinned:
        resolved = []
        for full_name in pinned:
            resp = client._get(f"/repos/{full_name}")
            if resp.status_code == 200:
                resolved.append(resp.json())
            else:
                log.warning("Skipping %s (HTTP %s)", full_name, resp.status_code)
        return resolved
    return client.list_repos(limit=settings.max_repos)


def ingest_commits(session: Session) -> Dict[str, int]:
    """
    Run one full ingestion pass. Returns counts for the sync log.
    """
    with GitHubClient() as client:
        username = client.get_username()
        repo_payloads = resolve_repos(client)
        log.info("Ingesting %d repos as %s", len(repo_payloads), username)

        repos_synced = 0
        commits_ingested = 0

        for payload in repo_payloads:
            repo = _upsert_repo(session, payload)

            try:
                listing = client.list_commits(
                    repo.full_name, author=username, days=settings.commit_lookback_days
                )
            except GitHubError as exc:
                log.warning("Could not list commits for %s: %s", repo.full_name, exc)
                continue

            # Skip SHAs already stored -- this is what makes reruns cheap.
            known = set(
                session.scalars(
                    select(Commit.sha).where(Commit.repo_id == repo.id)
                ).all()
            )

            for entry in listing:
                sha = entry["sha"]
                if sha in known:
                    continue

                detail = client.get_commit_detail(repo.full_name, sha)
                files = [f["filename"] for f in detail.get("files", [])]
                stats = detail.get("stats", {})

                session.add(
                    Commit(
                        repo_id=repo.id,
                        sha=sha,
                        message=(entry.get("commit", {}).get("message") or "")[:2000],
                        authored_at=_parse_github_time(
                            entry.get("commit", {}).get("author", {}).get("date")
                        ),
                        files_changed="\n".join(files[:MAX_FILES_PER_COMMIT]),
                        additions=stats.get("additions", 0),
                        deletions=stats.get("deletions", 0),
                    )
                )
                commits_ingested += 1

            repo.last_synced_at = utcnow()
            repos_synced += 1
            session.commit()

    return {"repos_synced": repos_synced, "commits_ingested": commits_ingested}
