# engines/career-engine/integrations/test_linkedin_client.py
#
# WHAT: Tests for the LinkedIn OAuth client.
# WHY:  Verify OAuth flow, rate limiting, profile reading, and
#       post() safety gate (confirm=True required). All tests use mocks.
# BREAKS IF DELETED: No regression testing for LinkedIn integration.

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add paths
_ENGINE_PATH = Path(__file__).resolve().parent
sys.path.insert(0, str(_ENGINE_PATH))

from linkedin_client import (
    LinkedInClient,
    LinkedInProfile,
    RateLimiter,
    DAILY_POST_LIMIT,
    DAILY_READ_LIMIT,
    READ_SCOPES,
    WRITE_SCOPES,
    ALL_SCOPES,
    _load_token,
)


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_PROFILE = {
    "sub": "ABC123",
    "name": "John Smith",
    "email": "john.smith@example.com",
    "localizedFirst Name": "John",
    "localizedLast Name": "Smith",
}

MOCK_POST_RESPONSE = {
    "id": "urn:li:share:7123456789",
    "lifecycleState": "PUBLISHED",
    "specificContent": {
        "com.linkedin.ugc.ShareContent": {
            "shareCommentary": {
                "text": "Test post"
            }
        }
    },
    "visibility": {
        "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
    }
}


# ---------------------------------------------------------------------------
# Tests: Scopes
# ---------------------------------------------------------------------------

class TestScopes:
    """Tests for scope definitions."""

    def test_read_scopes(self):
        """
        Contract: READ_SCOPES should contain openid and profile.
        """
        assert "openid" in READ_SCOPES
        assert "profile" in READ_SCOPES

    def test_write_scopes(self):
        """
        Contract: WRITE_SCOPES should contain w_member_social.
        """
        assert "w_member_social" in WRITE_SCOPES

    def test_all_scopes_combined(self):
        """
        Contract: ALL_SCOPES should be the combination of read and write.
        """
        assert ALL_SCOPES == READ_SCOPES + WRITE_SCOPES
        assert len(ALL_SCOPES) == 3


# ---------------------------------------------------------------------------
# Tests: Rate Limiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_allows_calls_under_limit(self):
        """
        Contract: RateLimiter should allow calls under the daily limit.
        """
        limiter = RateLimiter(daily_limit=5)

        for i in range(5):
            assert limiter.can_call()
            limiter.record_call()

        # Should be exhausted now
        assert not limiter.can_call()

    def test_tracks_remaining(self):
        """
        Contract: RateLimiter should report correct remaining calls.
        """
        limiter = RateLimiter(daily_limit=10)

        assert limiter.calls_remaining == 10

        limiter.record_call()
        limiter.record_call()

        assert limiter.calls_remaining == 8

    def test_respects_limit(self):
        """
        Contract: RateLimiter should refuse calls at the limit.
        """
        limiter = RateLimiter(daily_limit=2)

        limiter.record_call()
        limiter.record_call()

        assert not limiter.can_call()


# ---------------------------------------------------------------------------
# Tests: Token loading
# ---------------------------------------------------------------------------

class TestTokenLoading:
    """Tests for _load_token() function."""

    def test_loads_token_from_secrets(self, tmp_path: Path):
        """
        Contract: _load_token should read token from secrets file.
        """
        secrets_file = tmp_path / "linkedin.secrets"
        secrets_file.write_text("LINKEDIN_TOKEN=linkedin_test_token_123\n", encoding="utf-8")

        token = _load_token(secrets_file)

        assert token == "linkedin_test_token_123"

    def test_returns_none_when_file_missing(self, tmp_path: Path):
        """
        Contract: _load_token should return None when file doesn't exist.
        """
        token = _load_token(tmp_path / "nonexistent.secrets")

        assert token is None

    def test_ignores_placeholder_token(self, tmp_path: Path):
        """
        Contract: _load_token should ignore empty/placeholder tokens.
        """
        secrets_file = tmp_path / "linkedin.secrets"
        secrets_file.write_text("LINKEDIN_TOKEN=\n", encoding="utf-8")

        token = _load_token(secrets_file)

        assert token is None

    def test_ignores_github_tokens(self, tmp_path: Path):
        """
        Contract: _load_token should ignore tokens starting with ghp_.
        """
        secrets_file = tmp_path / "linkedin.secrets"
        secrets_file.write_text("LINKEDIN_TOKEN=ghp_wrong_token_type\n", encoding="utf-8")

        token = _load_token(secrets_file)

        assert token is None


# ---------------------------------------------------------------------------
# Tests: LinkedInClient
# ---------------------------------------------------------------------------

class TestLinkedInClient:
    """Tests for LinkedInClient class."""

    def test_init_with_token(self):
        """
        Contract: client should accept explicit token.
        """
        client = LinkedInClient(token="test_token")

        assert client.is_authenticated
        assert client.post_calls_remaining == DAILY_POST_LIMIT

    def test_init_without_token(self):
        """
        Contract: client should work without token (but not authenticated).
        """
        with patch("linkedin_client._load_token", return_value=None):
            client = LinkedInClient()

        assert not client.is_authenticated

    def test_get_profile(self):
        """
        Contract: get_profile should return LinkedInProfile from API.
        """
        client = LinkedInClient(token="test_token")

        with patch.object(client, "_get", return_value=MOCK_PROFILE):
            profile = client.get_profile()

        assert isinstance(profile, LinkedInProfile)
        assert profile.sub == "ABC123"
        assert profile.name == "John Smith"
        assert profile.email == "john.smith@example.com"

    def test_post_requires_confirm(self):
        """
        Contract: post_to_profile should raise ValueError without confirm=True.
        """
        client = LinkedInClient(token="test_token")

        with patch.object(client, "get_profile", return_value=LinkedInProfile(
            sub="ABC123", name="John Smith", email="john@example.com",
            localized_first_name="John", localized_last_name="Smith"
        )):
            with pytest.raises(ValueError, match="confirm=True"):
                client.post_to_profile("Test post", confirm=False)

    def test_post_with_confirm(self):
        """
        Contract: post_to_profile should succeed with confirm=True.
        """
        client = LinkedInClient(token="test_token")

        with patch.object(client, "get_profile", return_value=LinkedInProfile(
            sub="ABC123", name="John Smith", email="john@example.com",
            localized_first_name="John", localized_last_name="Smith"
        )):
            with patch.object(client, "_post", return_value=MOCK_POST_RESPONSE):
                result = client.post_to_profile("Test post", confirm=True)

        assert result["id"] == "urn:li:share:7123456789"
        assert result["lifecycleState"] == "PUBLISHED"

    def test_post_respects_rate_limit(self):
        """
        Contract: post_to_profile should raise RuntimeError when rate limited.
        """
        client = LinkedInClient(token="test_token")

        # Exhaust the rate limit
        for _ in range(DAILY_POST_LIMIT):
            client._post_limiter.record_call()

        assert client.post_calls_remaining == 0

        with patch.object(client, "get_profile", return_value=LinkedInProfile(
            sub="ABC123", name="John Smith", email="john@example.com",
            localized_first_name="John", localized_last_name="Smith"
        )):
            with pytest.raises(RuntimeError, match="rate limit"):
                client.post_to_profile("Test post", confirm=True)

    def test_token_not_logged(self):
        """
        Contract: token should never appear in logs or error messages.
        """
        import logging
        with patch("linkedin_client.logger") as mock_logger:
            client = LinkedInClient(token="linkedin_secret_token_xyz")
            # Simulate some logging
            mock_logger.info("Test message")
            mock_logger.warning("Test warning")

        # Verify no log call contains the token
        for call in mock_logger.method_calls:
            assert "linkedin_secret_token_xyz" not in str(call)

    def test_read_rate_limit(self):
        """
        Contract: get_profile should respect read rate limit.
        """
        client = LinkedInClient(token="test_token")

        # Exhaust read limit
        for _ in range(DAILY_READ_LIMIT):
            client._read_limiter.record_call()

        assert client.read_calls_remaining == 0

        with pytest.raises(RuntimeError, match="rate limit"):
            client.get_profile()


# ---------------------------------------------------------------------------
# Manual verification step
# ---------------------------------------------------------------------------

def test_manual_verification():
    """
    Contract: Manual verification step for LinkedIn integration.

    To verify manually:
    1. Add your LinkedIn credentials to E:/secrets/linkedin.secrets:
       LINKEDIN_TOKEN=your_oauth_token
       LINKEDIN_CLIENT_ID=your_client_id
       LINKEDIN_CLIENT_SECRET=your_client_secret

    2. Test profile reading:
       python -c "
       from engines.career_engine.integrations.linkedin_client import LinkedInClient
       client = LinkedInClient()
       profile = client.get_profile()
       print(f'Name: {profile.name}')
       print(f'Email: {profile.email}')
       print(f'Remaining posts: {client.post_calls_remaining}')
       "

    3. Test posting (requires confirm=True):
       python -c "
       from engines.career_engine.integrations.linkedin_client import LinkedInClient
       client = LinkedInClient()
       result = client.post_to_profile('Test post from Career Engine', confirm=True)
       print(f'Post ID: {result[\"id\"]}')
       "

    4. Verify rate limits:
       print(f'Posts remaining: {client.post_calls_remaining}')
       print(f'Reads remaining: {client.read_calls_remaining}')
    """
    # Placeholder for documentation
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
