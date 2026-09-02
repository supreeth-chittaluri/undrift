"""
Phase 2: pull commit history from GitHub into the database.

Undrift tracks several people at once. Each tracked person is a Profile -- a
GitHub username -- and ingestion runs once per profile:

  1. Make sure every configured profile exists (the token owner, plus any
     public accounts listed in SAMPLE_PROFILES as demo data).
  2. Work out which repos to read for that profile.
  3. List the commits that person authored in the lookback window.
  4. For any commit we haven't seen before, fetch its file list and store it.

Ingestion is idempotent -- commits are keyed by SHA, so re-running only ever
adds what's new. That's what makes it safe to run on a schedule.

The database is a cache, not the source of truth: everything in it can be
rebuilt from GitHub by deleting it and running a refresh. That's why there is
no migration tooling here -- a schema change means drop and re-ingest.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import utcnow
from .github_client import GitHubClient, GitHubError
from .models import Commit, Profile, Repo

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


def ensure_profiles(session: Session, client: GitHubClient) -> List[Profile]:
    """
    Make sure a Profile row exists for the token owner and every sample user.

    The owner is always first and never flagged as a sample; that is the
    profile the dashboard opens on.
    """
    owner_username = client.get_username()

    wanted = [(owner_username, False)]
    wanted += [
        (name, True) for name in settings.sample_usernames if name != owner_username
    ]

    profiles: List[Profile] = []
    for username, is_sample in wanted:
        profile = session.scalar(select(Profile).where(Profile.username == username))
        if profile is None:
            profile = Profile(username=username, is_sample=is_sample)
            session.add(profile)
            session.flush()
            log.info("Created profile %s (sample=%s)", username, is_sample)
        profiles.append(profile)

    session.commit()
    return profiles


def resolve_repos(client: GitHubClient, profile: Profile) -> List[Dict]:
    """
    Decide which repositories to read for one profile.

    For the token owner we can use the authenticated endpoint, which includes
    private repos. For a sample profile we can only see public ones -- and
    that's the correct boundary, not a limitation to work around.
    """
    if not profile.is_sample:
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

    return client.list_public_repos(profile.username, limit=settings.max_repos)


def ingest_commits(session: Session) -> Dict[str, int]:
    """Run one full ingestion pass across every profile. Returns counts."""
    with GitHubClient() as client:
        profiles = ensure_profiles(session, client)

        repos_synced = 0
        commits_ingested = 0

        for profile in profiles:
            try:
                repo_payloads = resolve_repos(client, profile)
            except GitHubError as exc:
                log.warning("Could not list repos for %s: %s", profile.username, exc)
                continue

            log.info(
                "Ingesting %d repos for %s", len(repo_payloads), profile.username
            )

            for payload in repo_payloads:
                repo = _upsert_repo(session, payload)

                try:
                    listing = client.list_commits(
                        repo.full_name,
                        author=profile.username,
                        days=settings.commit_lookback_days,
                        limit=settings.max_commits_per_repo,
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
                            profile_id=profile.id,
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

            profile.last_synced_at = utcnow()
            session.commit()

    return {"repos_synced": repos_synced, "commits_ingested": commits_ingested}
