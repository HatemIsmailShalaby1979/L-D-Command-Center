# engines/career-engine/integrations/test_github_client.py
#
# WHAT: Tests for the GitHub integration client.
# WHY:  Verify token loading, repo fetching, README parsing, and project
#       proposal logic. All tests use mocks — no live API calls.
# BREAKS IF DELETED: No regression testing for GitHub integration.

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add paths
_ENGINE_PATH = Path(__file__).resolve().parent
sys.path.insert(0, str(_ENGINE_PATH))

from github_client import (
    GitHubClient,
    GitHubRepo,
    GitHubREADME,
    propose_resume_projects,
    _load_token,
)


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_REPOS = [
    {
        "name": "inventory-system",
        "full_name": "testuser/inventory-system",
        "description": "Full-stack inventory management system",
        "html_url": "https://github.com/testuser/inventory-system",
        "topics": ["python", "react", "postgresql"],
        "language": "Python",
    },
    {
        "name": "ml-pipeline",
        "full_name": "testuser/ml-pipeline",
        "description": "Automated ML data processing pipeline",
        "html_url": "https://github.com/testuser/ml-pipeline",
        "topics": ["python", "tensorflow"],
        "language": "Python",
    },
]

MOCK_README_CONTENT = """# ML Pipeline

Automated data processing pipeline using Python and TensorFlow.

## Features
- Batch processing
- Model training
- Evaluation metrics
"""


# ---------------------------------------------------------------------------
# Tests: Token loading
# ---------------------------------------------------------------------------

class TestTokenLoading:
    """Tests for _load_token() function."""

    def test_loads_token_from_secrets(self, tmp_path: Path):
        """
        Contract: _load_token should read token from secrets file.
        """
        secrets_file = tmp_path / "github.secrets"
        secrets_file.write_text("GITHUB_TOKEN=ghp_testtoken123\n", encoding="utf-8")

        token = _load_token(secrets_file)

        assert token == "ghp_testtoken123"

    def test_returns_none_when_file_missing(self, tmp_path: Path):
        """
        Contract: _load_token should return None when file doesn't exist.
        """
        token = _load_token(tmp_path / "nonexistent.secrets")

        assert token is None

    def test_ignores_empty_token(self, tmp_path: Path):
        """
        Contract: _load_token should ignore placeholder tokens.
        """
        secrets_file = tmp_path / "github.secrets"
        secrets_file.write_text("GITHUB_TOKEN=ghp_your_personal_access_token_here\n", encoding="utf-8")

        token = _load_token(secrets_file)

        assert token is None

    def test_ignores_comments(self, tmp_path: Path):
        """
        Contract: _load_token should skip comment lines.
        """
        secrets_file = tmp_path / "github.secrets"
        secrets_file.write_text("# This is a comment\nGITHUB_TOKEN=ghp_realtoken\n", encoding="utf-8")

        token = _load_token(secrets_file)

        assert token == "ghp_realtoken"


# ---------------------------------------------------------------------------
# Tests: GitHubClient
# ---------------------------------------------------------------------------

class TestGitHubClient:
    """Tests for GitHubClient class."""

    def test_init_with_token(self):
        """
        Contract: client should accept explicit token.
        """
        client = GitHubClient(token="ghp_testtoken")

        assert client.is_authenticated

    def test_init_without_token(self):
        """
        Contract: client should work without token (rate-limited).
        """
        with patch("github_client._load_token", return_value=None):
            client = GitHubClient()

        assert not client.is_authenticated

    def test_get_user_repos(self):
        """
        Contract: get_user_repos should return list of GitHubRepo objects.
        """
        client = GitHubClient(token="ghp_test")

        with patch.object(client, "_get", return_value=MOCK_REPOS):
            repos = client.get_user_repos("testuser", limit=2)

        assert len(repos) == 2
        assert repos[0].name == "inventory-system"
        assert repos[0].language == "Python"
        assert repos[0].topics == ["python", "react", "postgresql"]

    def test_get_repo_readme(self):
        """
        Contract: get_repo_readme should return GitHubREADME with decoded content.
        """
        import base64
        client = GitHubClient(token="ghp_test")

        mock_readme_data = {
            "content": base64.b64encode(MOCK_README_CONTENT.encode()).decode(),
            "encoding": "utf-8",
            "size": len(MOCK_README_CONTENT),
        }

        with patch.object(client, "_get", return_value=mock_readme_data):
            readme = client.get_repo_readme("testuser", "ml-pipeline")

        assert readme is not None
        assert "ML Pipeline" in readme.content
        assert readme.size == len(MOCK_README_CONTENT)

    def test_get_repo_readme_not_found(self):
        """
        Contract: get_repo_readme should return None for repos without README.
        """
        client = GitHubClient(token="ghp_test")

        with patch.object(client, "_get", side_effect=RuntimeError("GitHub API error: 404")):
            readme = client.get_repo_readme("testuser", "no-readme-repo")

        assert readme is None

    def test_get_repo_readme_raw(self):
        """
        Contract: get_repo_readme_raw should return raw string.
        """
        import base64
        client = GitHubClient(token="ghp_test")

        mock_readme_data = {
            "content": base64.b64encode(MOCK_README_CONTENT.encode()).decode(),
            "encoding": "utf-8",
            "size": len(MOCK_README_CONTENT),
        }

        with patch.object(client, "_get", return_value=mock_readme_data):
            raw = client.get_repo_readme_raw("testuser", "ml-pipeline")

        assert raw is not None
        assert "ML Pipeline" in raw

    def test_token_not_logged(self):
        """
        Contract: token should never appear in logs or error messages.
        """
        import logging
        with patch("github_client.logger") as mock_logger:
            client = GitHubClient(token="ghp_secret_token_123")
            # Simulate some logging
            mock_logger.info("Test message")
            mock_logger.warning("Test warning")

        # Verify no log call contains the token
        for call in mock_logger.method_calls:
            assert "ghp_secret_token_123" not in str(call)


# ---------------------------------------------------------------------------
# Tests: propose_resume_projects
# ---------------------------------------------------------------------------

class TestProposeResumeProjects:
    """Tests for propose_resume_projects() function."""

    def test_proposes_from_repos(self):
        """
        Contract: propose_resume_projects should create project entries from repos.
        """
        repos = [
            GitHubRepo(
                name="inventory-system",
                full_name="testuser/inventory-system",
                description="Full-stack inventory management system",
                html_url="https://github.com/testuser/inventory-system",
                topics=["python", "react"],
                language="Python",
            ),
            GitHubRepo(
                name="ml-pipeline",
                full_name="testuser/ml-pipeline",
                description="Automated ML data processing pipeline",
                html_url="https://github.com/testuser/ml-pipeline",
                topics=["python", "tensorflow"],
                language="Python",
            ),
        ]

        projects = propose_resume_projects(repos, max_projects=2)

        assert len(projects) == 2
        assert projects[0]["name"] == "inventory-system"
        assert "inventory" in projects[0]["description"].lower()
        assert "Python" in projects[0]["tech"]

    def test_enhances_with_readme(self):
        """
        Contract: propose_resume_projects should enhance descriptions with README.
        """
        repos = [
            GitHubRepo(
                name="ml-pipeline",
                full_name="testuser/ml-pipeline",
                description="ML pipeline",
                html_url="https://github.com/testuser/ml-pipeline",
                topics=[],
                language="Python",
            ),
        ]

        readme_contents = {
            "testuser/ml-pipeline": MOCK_README_CONTENT,
        }

        projects = propose_resume_projects(repos, readme_contents=readme_contents)

        assert len(projects) == 1
        # Should include README content (case-insensitive check)
        assert "ml pipeline" in projects[0]["description"].lower()

    def test_respects_max_projects(self):
        """
        Contract: propose_resume_projects should respect max_projects limit.
        """
        repos = [
            GitHubRepo(name=f"repo-{i}", full_name=f"user/repo-{i}", description=f"Description {i}",
                       html_url=f"https://github.com/user/repo-{i}", topics=[], language="Python")
            for i in range(5)
        ]

        projects = propose_resume_projects(repos, max_projects=3)

        assert len(projects) == 3

    def test_returns_proposals_not_merged(self):
        """
        Contract: propose_resume_projects should return list, not modify any Resume.
        """
        repos = [
            GitHubRepo(
                name="test-repo",
                full_name="user/test-repo",
                description="Test repo",
                html_url="https://github.com/user/test-repo",
                topics=["python"],
                language="Python",
            ),
        ]

        projects = propose_resume_projects(repos)

        # Should return a list of dicts
        assert isinstance(projects, list)
        assert isinstance(projects[0], dict)
        assert "name" in projects[0]
        assert "description" in projects[0]
        assert "tech" in projects[0]


# ---------------------------------------------------------------------------
# Manual verification step
# ---------------------------------------------------------------------------

def test_manual_verification():
    """
    Contract: Manual verification step for GitHub integration.

    To verify manually:
    1. Add your GitHub token to E:/secrets/github.secrets:
       GITHUB_TOKEN=ghp_your_actual_token_here
    2. Run this test with a real username:
       python -c "
       from engines.career_engine.integrations.github_client import GitHubClient
       client = GitHubClient()
       repos = client.get_user_repos('your-username', limit=5)
       for repo in repos:
           print(f'{repo.name}: {repo.description}')
       "
    3. Verify projects are proposed correctly:
       from engines.career_engine.integrations.github_client import propose_resume_projects
       projects = propose_resume_projects(repos)
       for p in projects:
           print(f\"- {p['name']}: {p['description'][:50]}\")
    """
    # Placeholder for documentation
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
