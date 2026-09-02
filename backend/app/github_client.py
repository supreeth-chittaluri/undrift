"""
A small, purpose-built GitHub API client.

Deliberately not a general-purpose wrapper -- it does exactly the four things
Undrift needs: identify the token owner, list their repositories, list the
commits they authored, and fetch the file list for one commit.

The token is read from settings (env var) and is never logged or persisted.
"""

from datetime import timedelta
from typing import Dict, List, Optional

import httpx

from .config import settings
from .db import utcnow

API_ROOT = "https://api.github.com"


class GitHubError(RuntimeError):
    """Raised when GitHub returns something we can't work with."""


class GitHubClient:
    def __init__(self, token: Optional[str] = None, timeout: float = 20.0):
        self.token = token if token is not None else settings.github_token
        if not self.token:
            raise GitHubError(
                "GITHUB_TOKEN is not set. Add it to your .env file "
                "(see .env.example) -- it is never hardcoded."
            )
        self._client = httpx.Client(
            base_url=API_ROOT,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "undrift",
            },
        )

    # --- plumbing ---------------------------------------------------------

    def _get(self, path: str, **params) -> httpx.Response:
        resp = self._client.get(path, params=params)
        if resp.status_code == 401:
            raise GitHubError("GitHub rejected the token (401). Is GITHUB_TOKEN valid?")
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            raise GitHubError("GitHub rate limit hit. Try again later.")
        return resp

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- the four things we actually need ---------------------------------

    def get_username(self) -> str:
        """The login of whoever owns the token."""
        resp = self._get("/user")
        resp.raise_for_status()
        return resp.json()["login"]

    def list_repos(self, limit: int) -> List[Dict]:
        """
        The token owner's repositories, most recently pushed first.

        Used when GITHUB_REPOS is empty, so the app discovers what to track
        instead of relying on a hand-maintained list. Includes private repos,
        because the token belongs to this user.
        """
        repos: List[Dict] = []
        page = 1
        while len(repos) < limit:
            resp = self._get(
                "/user/repos",
                affiliation="owner",
                sort="pushed",
                direction="desc",
                per_page=100,
                page=page,
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            repos.extend(batch)
            page += 1
        return repos[:limit]

    def list_public_repos(self, username: str, limit: int) -> List[Dict]:
        """
        Someone else's PUBLIC repositories, most recently pushed first.

        This is the endpoint used for sample profiles. It only ever returns
        public data -- we cannot see another user's private repos, and
        shouldn't -- so a sample profile's scores are built purely from
        information that was already public.
        """
        repos: List[Dict] = []
        page = 1
        while len(repos) < limit:
            resp = self._get(
                f"/users/{username}/repos",
                type="owner",
                sort="pushed",
                direction="desc",
                per_page=100,
                page=page,
            )
            if resp.status_code == 404:
                raise GitHubError(f"GitHub user '{username}' does not exist.")
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            # Forks tend to carry thousands of other people's commits and tell
            # us nothing about what this person actually works on.
            repos.extend([r for r in batch if not r.get("fork")])
            page += 1
        return repos[:limit]

    def list_commits(
        self, full_name: str, author: str, days: int, limit: int = 40
    ) -> List[Dict]:
        """
        Commits in `full_name` authored by `author` within the last `days`.

        Filtering by author server-side matters: on a repo you forked or
        collaborated on, we only want to credit skills to commits you wrote.

        `limit` caps how many we take. Every new commit costs one Claude call
        to classify, so an uncapped read of a prolific repo would be slow and
        expensive for very little extra signal.
        """
        since = (utcnow() - timedelta(days=days)).isoformat() + "Z"
        commits: List[Dict] = []
        page = 1
        while True:
            resp = self._get(
                f"/repos/{full_name}/commits",
                author=author,
                since=since,
                per_page=100,
                page=page,
            )
            # An empty repository returns 409; a repo we can't read returns 404.
            # Neither is fatal -- skip it and keep ingesting the others.
            if resp.status_code in (404, 409):
                return commits
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            commits.extend(batch)
            if len(batch) < 100 or len(commits) >= limit:
                break
            page += 1
        return commits[:limit]

    def get_commit_detail(self, full_name: str, sha: str) -> Dict:
        """
        One commit with its file list and line counts.

        Needed because the list endpoint omits `files`, and the changed file
        paths are the single strongest signal the skill classifier gets.
        """
        resp = self._get(f"/repos/{full_name}/commits/{sha}")
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()
