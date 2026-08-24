# engines/career-engine/integrations/linkedin_client.py
#
# WHAT: Read-only LinkedIn OAuth client for self-serve tier.
# WHY:  Users can log in via LinkedIn OAuth to read their own profile
#       and post to their own profile. This is deliberately limited:
#       - NO reading other members' data
#       - NO search or messaging
#       - Only openid + profile scopes for reading
#       - Only w_member_social for posting
#       - Rate limit tracked client-side (~100-150/day ceiling)
#       - Token from secrets file (never hardcoded or logged)
# BREAKS IF DELETED: Resume upload loses the "connect LinkedIn" option.

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from storage.secrets import load_secret as _read_secret

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# LinkedIn API rate limit for self-serve tier (conservative estimate)
DAILY_POST_LIMIT = 100
DAILY_READ_LIMIT = 1000

# Scopes required for self-serve tier
READ_SCOPES = ["openid", "profile"]
WRITE_SCOPES = ["w_member_social"]
ALL_SCOPES = READ_SCOPES + WRITE_SCOPES


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class LinkedInProfile:
    """
    Contract: represents the authenticated user's basic LinkedIn profile.

    Fields:
      - sub: LinkedIn user ID (from openid)
      - name: Full name
      - email: Primary email (if shared)
      - localized_first_name: First name in user's language
      - localized_last_name: Last name in user's language
    """
    sub: str
    name: Optional[str]
    email: Optional[str]
    localized_first_name: Optional[str]
    localized_last_name: Optional[str]


# ---------------------------------------------------------------------------
# Secrets loader
# ---------------------------------------------------------------------------

def _load_token(secrets_path: Optional[Path] = None) -> Optional[str]:
    """
    Contract: resolve LINKEDIN_TOKEN via the storage secrets adapter.

    Local policy: reject ghp_-prefixed (GitHub) tokens and short values.
    """
    token = _read_secret("LINKEDIN_TOKEN", secrets_path=secrets_path)
    if token and not token.startswith("ghp_") and len(token) > 10:
        logger.info("LinkedIn token loaded from secrets file")
        return token
    return None


class RateLimiter:
    """
    Contract: track daily API calls and enforce rate limits.

    Refuses calls before hitting the limit, rather than waiting for
    LinkedIn to reject them.
    """

    def __init__(self, daily_limit: int):
        self._daily_limit = daily_limit
        self._calls: list[float] = []

    def can_call(self) -> bool:
        """Check if another call is allowed today."""
        now = time.time()
        # Remove calls older than 24 hours
        self._calls = [t for t in self._calls if now - t < 86400]
        return len(self._calls) < self._daily_limit

    def record_call(self) -> None:
        """Record a call for rate limiting."""
        self._calls.append(time.time())

    @property
    def calls_remaining(self) -> int:
        """Number of calls remaining today."""
        now = time.time()
        recent_calls = len([t for t in self._calls if now - t < 86400])
        return max(0, self._daily_limit - recent_calls)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class LinkedInClient:
    """
    Contract: LinkedIn OAuth client for self-serve tier.

    Capabilities:
      - Read authenticated user's basic profile (openid + profile)
      - Post to authenticated user's own profile (w_member_social)
      - Rate limit tracking (~100-150 posts/day)
      - Token loaded from secrets file (never hardcoded or logged)

    Not implemented (require partner approval):
      - Reading other members' data
      - Search functionality
      - Messaging
    """

    def __init__(
        self,
        token: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        """
        Initialize the LinkedIn client.

        Args:
            token: optional OAuth token (falls back to secrets file).
            client_id: optional OAuth client ID (falls back to secrets file).
            client_secret: optional OAuth client secret (falls back to secrets file).
        """
        self._token = token or _load_token()
        self._client_id = client_id or _load_secrets_value("LINKEDIN_CLIENT_ID")
        self._client_secret = client_secret or _load_secrets_value("LINKEDIN_CLIENT_SECRET")

        self._read_limiter = RateLimiter(DAILY_READ_LIMIT)
        self._post_limiter = RateLimiter(DAILY_POST_LIMIT)

        self._authenticated = bool(self._token)

    @property
    def is_authenticated(self) -> bool:
        """Check if client has valid authentication."""
        return self._authenticated

    @property
    def post_calls_remaining(self) -> int:
        """Number of post calls remaining today."""
        return self._post_limiter.calls_remaining

    @property
    def read_calls_remaining(self) -> int:
        """Number of read calls remaining today."""
        return self._read_limiter.calls_remaining

    def _get(self, endpoint: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """
        Contract: make a GET request to the LinkedIn API.

        Args:
            endpoint: API endpoint path.
            params: optional query parameters.

        Returns:
            Parsed JSON response as dict.

        Raises:
            ConnectionError: if API is unreachable.
            RuntimeError: if API returns an error or rate limit exceeded.
        """
        import urllib.request
        import urllib.error
        import json

        if not self._token:
            raise RuntimeError("LinkedIn token not available. Add LINKEDIN_TOKEN to secrets file.")

        if not self._read_limiter.can_call():
            raise RuntimeError(
                f"LinkedIn read rate limit exceeded. "
                f"Calls remaining: {self._read_limiter.calls_remaining}"
            )

        url = f"https://api.linkedin.com/v2/{endpoint.lstrip('/')}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "LinkedIn-Version": "202402",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = response.read().decode("utf-8")
                self._read_limiter.record_call()
                return json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RuntimeError("LinkedIn API rate limit exceeded (429).") from e
            if e.code == 401:
                raise RuntimeError("LinkedIn authentication failed. Token may be expired.") from e
            raise RuntimeError(f"LinkedIn API error: {e.code}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(f"Failed to connect to LinkedIn API: {e.reason}") from e

    def _post(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        """
        Contract: make a POST request to the LinkedIn API.

        Args:
            endpoint: API endpoint path.
            data: JSON body data.

        Returns:
            Parsed JSON response as dict.

        Raises:
            ConnectionError: if API is unreachable.
            RuntimeError: if API returns an error or rate limit exceeded.
        """
        import urllib.request
        import urllib.error
        import json

        if not self._token:
            raise RuntimeError("LinkedIn token not available. Add LINKEDIN_TOKEN to secrets file.")

        if not self._post_limiter.can_call():
            raise RuntimeError(
                f"LinkedIn post rate limit exceeded. "
                f"Calls remaining: {self._post_limiter.calls_remaining}"
            )

        url = f"https://api.linkedin.com/v2/{endpoint.lstrip('/')}"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._token}",
                "LinkedIn-Version": "202402",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                self._post_limiter.record_call()
                data = response.read().decode("utf-8")
                return json.loads(data) if data else {}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RuntimeError("LinkedIn API rate limit exceeded (429).") from e
            if e.code == 401:
                raise RuntimeError("LinkedIn authentication failed. Token may be expired.") from e
            raise RuntimeError(f"LinkedIn API error: {e.code}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(f"Failed to connect to LinkedIn API: {e.reason}") from e

    def get_profile(self) -> LinkedInProfile:
        """
        Contract: fetch the authenticated user's basic LinkedIn profile.

        Uses /v2/userinfo endpoint with openid + profile scopes.
        Returns only basic profile data — no work history, education, etc.

        Returns:
            LinkedInProfile object with basic user info.

        Raises:
            RuntimeError: if authentication fails or rate limit exceeded.
        """
        data = self._get("userinfo")

        return LinkedInProfile(
            sub=data.get("sub", ""),
            name=data.get("name"),
            email=data.get("email"),
            localized_first_name=data.get("localizedFirst Name"),
            localized_last_name=data.get("localizedLast Name"),
        )

    def post_to_profile(
        self,
        text: str,
        *,
        confirm: bool = False,
        visibility: str = "PUBLIC",
    ) -> dict[str, Any]:
        """
        Contract: post content to the authenticated user's LinkedIn profile.

        Requires explicit confirm=True — there is no code path where a post
        fires without the caller deliberately setting it.

        Args:
            text: The post content (plain text or limited markdown).
            confirm: Must be True to actually post. This is the safety gate.
            visibility: Post visibility — "PUBLIC", "CONNECTIONS", or "SELF".

        Returns:
            Dict with post ID and status on success.

        Raises:
            ValueError: if confirm is not True.
            RuntimeError: if rate limit exceeded or API error.
        """
        # Safety gate: require explicit confirmation
        if not confirm:
            raise ValueError(
                "post_to_profile() requires confirm=True. "
                "This is a safety measure — posts should only fire with explicit user confirmation."
            )

        # Check rate limit
        if not self._post_limiter.can_call():
            raise RuntimeError(
                f"LinkedIn post rate limit reached. "
                f"Calls remaining today: {self._post_limiter.calls_remaining}"
            )

        # Build post content
        post_data = {
            "author": f"urn:li:person:{self.get_profile().sub}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": text,
                    },
                    "shareMediaCategory": "NONE",
                },
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility,
            },
        }

        result = self._post("ugcPosts", post_data)
        logger.info("Successfully posted to LinkedIn (post_id: %s)", result.get("id"))
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_secrets_value(key: str, secrets_path: Optional[Path] = None) -> Optional[str]:
    """Contract: any other LinkedIn credential (client id/secret, etc.)."""
    return _read_secret(key, secrets_path=secrets_path)
