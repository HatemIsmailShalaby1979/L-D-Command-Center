# engines/career-engine/integrations/github_client.py
#
# WHAT: Read-only GitHub integration client for resume enhancement.
# WHY:  Users can seed Resume.projects from their public GitHub repos.
#       This client reads only — no write access, no API mutations.
#       Token is loaded from secrets file per CONSTITUTION.md §3.
# BREAKS IF DELETED: Resume upload flow loses the "import from GitHub" option.

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from storage.secrets import load_secret as _read_secret

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GitHubRepo:
    """
    Contract: represents a GitHub repository for resume project seeding.

    Fields:
      - name: repository name
      - full_name: owner/repo format
      - description: repo description (may be None)
      - html_url: web URL to the repo
      - topics: list of topic tags
      - language: primary programming language
    """
    name: str
    full_name: str
    description: Optional[str]
    html_url: str
    topics: list[str]
    language: Optional[str]


@dataclass
class GitHubREADME:
    """
    Contract: represents README content for a repository.

    Fields:
      - content: raw markdown text
      - encoding: file encoding (e.g., "utf-8")
      - size: file size in bytes
    """
    content: str
    encoding: str = "utf-8"
    size: int = 0


# ---------------------------------------------------------------------------
# Secrets loader
# ---------------------------------------------------------------------------

def _load_token(secrets_path: Optional[Path] = None) -> Optional[str]:
    """
    Contract: resolve GITHUB_TOKEN via the storage secrets adapter.

    Parsing lives in storage/secrets.py (P5.1); this wrapper keeps only
    GitHub's own validity policy (reject the docs placeholder).
    """
    token = _read_secret("GITHUB_TOKEN", secrets_path=secrets_path)
    placeholders = {"ghp_your_personal_access_token_here"}
    if token and token not in placeholders:
        logger.info("GitHub token loaded from secrets file")
        return token
    return None


class GitHubClient:
    """
    Contract: read-only GitHub API client for resume integration.

    Capabilities:
      - Fetch user's public repositories
      - Fetch README content for repos
      - Never write, edit, or delete anything

    Token loading:
      - Reads from secrets file (never hardcoded)
      - Never logs the token value
    """

    def __init__(self, token: Optional[str] = None, base_url: str = "https://api.github.com"):
        """
        Initialize the GitHub client.

        Args:
            token: optional token string (falls back to secrets file).
            base_url: GitHub API base URL.
        """
        self._base_url = base_url.rstrip("/")
        self._token = token or _load_token()
        self._headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Career-Engine/1.0",
        }
        if self._token:
            self._headers["Authorization"] = f"token {self._token}"
            self._authenticated = True
        else:
            self._authenticated = False
            logger.warning("No GitHub token available — API requests will be rate-limited")

    @property
    def is_authenticated(self) -> bool:
        """Check if client has valid authentication."""
        return self._authenticated

    def _get(self, endpoint: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """
        Contract: make a GET request to the GitHub API.

        Args:
            endpoint: API endpoint path.
            params: optional query parameters.

        Returns:
            Parsed JSON response as dict.

        Raises:
            ConnectionError: if API is unreachable.
            RuntimeError: if API returns an error.
        """
        import urllib.request
        import urllib.error
        import json

        url = f"{self._base_url}/{endpoint.lstrip('/')}"
        req = urllib.request.Request(url, headers=self._headers)

        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query}"
            req = urllib.request.Request(url, headers=self._headers)

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = response.read().decode("utf-8")
                return json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code == 403 and "rate limit" in str(e).lower():
                raise RuntimeError("GitHub API rate limit exceeded. Provide a personal access token.") from e
            raise RuntimeError(f"GitHub API error: {e.code}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(f"Failed to connect to GitHub API: {e.reason}") from e

    def get_user_repos(self, username: str, limit: int = 10) -> list[GitHubRepo]:
        """
        Contract: fetch a user's public repositories.

        Args:
            username: GitHub username.
            limit: maximum number of repos to fetch.

        Returns:
            List of GitHubRepo objects (read-only data).
        """
        params = {
            "type": "owner",
            "sort": "updated",
            "per_page": limit,
        }
        data = self._get(f"/users/{username}/repos", params=params)

        repos = []
        for item in data:
            repo = GitHubRepo(
                name=item.get("name", ""),
                full_name=item.get("full_name", ""),
                description=item.get("description"),
                html_url=item.get("html_url", ""),
                topics=item.get("topics", []),
                language=item.get("language"),
            )
            repos.append(repo)

        logger.info("Fetched %d repos for user: %s", len(repos), username)
        return repos

    def get_repo_readme(self, owner: str, repo: str) -> Optional[GitHubREADME]:
        """
        Contract: fetch README content for a repository.

        Args:
            owner: repository owner username.
            repo: repository name.

        Returns:
            GitHubREADME object if README exists, None otherwise.
        """
        try:
            data = self._get(f"/repos/{owner}/{repo}/readme")
            import base64
            content = base64.b64decode(data.get("content", "")).decode("utf-8")
            return GitHubREADME(
                content=content,
                encoding=data.get("encoding", "utf-8"),
                size=data.get("size", 0),
            )
        except RuntimeError as e:
            if "404" in str(e):
                logger.debug("No README found for %s/%s", owner, repo)
                return None
            raise

    def get_repo_readme_raw(self, owner: str, repo: str) -> Optional[str]:
        """
        Contract: fetch raw README content as a string.

        Convenience wrapper around get_repo_readme().

        Args:
            owner: repository owner username.
            repo: repository name.

        Returns:
            Raw markdown string or None if no README exists.
        """
        readme = self.get_repo_readme(owner, repo)
        return readme.content if readme else None


# ---------------------------------------------------------------------------
# Resume seeding
# ---------------------------------------------------------------------------

def propose_resume_projects(
    repos: list[GitHubRepo],
    readme_contents: Optional[dict[str, str]] = None,
    max_projects: int = 5,
) -> list[dict[str, Any]]:
    """
    Contract: propose Resume.project entries from fetched GitHub repos.

    Does NOT modify any existing Resume — returns a proposal list only.
    The caller must choose to merge these into an existing Resume.

    Args:
        repos: list of GitHubRepo objects from get_user_repos().
        readme_contents: optional dict mapping "owner/repo" -> README content.
        max_projects: maximum number of projects to propose.

    Returns:
        List of project dicts matching RESUME_SCHEMA project shape:
        - name: repo name
        - description: extracted from repo description + README
        - tech: list of programming languages from repos
    """
    readme_contents = readme_contents or {}
    projects = []

    for repo in repos[:max_projects]:
        # Extract project description
        description_parts = []

        # Use repo description if available
        if repo.description:
            description_parts.append(repo.description)

        # Enhance with README content if available
        readme_key = f"{repo.full_name}"
        if readme_key in readme_contents:
            readme = readme_contents[readme_key]
            # Take first paragraph or first 200 chars
            lines = readme.strip().split("\n")
            lines = [l.strip() for l in lines if l.strip()]
            if lines:
                # Skip markdown headers
                content_lines = [l for l in lines if not l.startswith("#")]
                if content_lines:
                    description_parts.append(content_lines[0][:200])

        description = " | ".join(description_parts) if description_parts else repo.description or ""

        # Extract tech stack
        tech = []
        if repo.language:
            tech.append(repo.language)
        tech.extend(repo.topics[:3])  # Add up to 3 topics

        projects.append({
            "name": repo.name,
            "description": description,
            "tech": tech,
        })

    logger.info("Proposed %d projects from %d repos", len(projects), len(repos))
    return projects


# ---------------------------------------------------------------------------
# Re-export
# ---------------------------------------------------------------------------

__all__ = [
    "GitHubClient",
    "GitHubRepo",
    "GitHubREADME",
    "propose_resume_projects",
    "_load_token",
]
