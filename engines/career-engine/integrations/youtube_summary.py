# engines/career-engine/integrations/youtube_summary.py
#
# WHAT: YouTube video search and AI-generated summaries via the model layer.
# WHY:  Users researching a topic need curated video summaries with traceable
#       source URLs — no summary without a URL, per CONSTITUTION.md §3.
#       This only runs when explicitly invoked, never as a side effect.
# BREAKS IF DELETED: Career-engine loses the YouTube research/summarization path.

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from model_layer.client import LmStudioClient, ModelRequest
from model_layer.prompts import PromptRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass
class YouTubeVideo:
    """
    Contract: a single YouTube video result from search.

    Fields:
      - video_id: unique YouTube video identifier
      - title: video title
      - channel: channel name
      - published_at: publication date string (ISO 8601)
      - url: full YouTube URL
      - description: truncated video description (may be None)
    """
    video_id: str
    title: str
    channel: str
    published_at: str
    url: str
    description: Optional[str]


@dataclass
class VideoSummary:
    """
    Contract: an AI-generated summary for a YouTube video with its source.

    Fields:
      - video: the YouTubeVideo this summary is for
      - summary: AI-generated summary text (1-3 paragraphs)
      - key_takeaways: bulleted list of key points

    Invariant: every VideoSummary must have a non-empty summary and
               its associated YouTubeVideo must have a valid url.
    """
    video: YouTubeVideo
    summary: str
    key_takeaways: list[str]


# ---------------------------------------------------------------------------
# Secrets loader
# ---------------------------------------------------------------------------

def _load_api_key(secrets_path: Optional[Path] = None) -> Optional[str]:
    """
    Contract: load YouTube Data API key from secrets file.

    API key is never logged or returned in error messages.
    Returns None if not found or file is empty.

    Args:
        secrets_path: path to secrets file. Defaults to ../secrets/youtube.secrets.

    Returns:
        The YouTube API key string, or None if not found.
    """
    if secrets_path is None:
        secrets_path = Path(__file__).parent.parent.parent.parent / "secrets" / "youtube.secrets"

    try:
        if not secrets_path.exists():
            logger.debug("YouTube secrets file not found at: %s", secrets_path)
            return None

        content = secrets_path.read_text(encoding="utf-8").strip()
        if not content:
            return None

        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                if key.strip() == "YOUTUBE_API_KEY":
                    api_key = value.strip()
                    # Accept keys starting with AIzaSy (standard YouTube API key format)
                    # or any non-empty key longer than 10 characters
                    if api_key and len(api_key) > 10:
                        logger.info("YouTube API key loaded from secrets file")
                        return api_key

    except Exception as e:
        logger.warning("Failed to load YouTube API key: %s", type(e).__name__)

    return None


# ---------------------------------------------------------------------------
# YouTube search client
# ---------------------------------------------------------------------------

class YouTubeSearchClient:
    """
    Contract: search YouTube videos using the Data API v3.

    Only search functionality — no uploads, no comments, no channel management.
    API key loaded from secrets file per CONSTITUTION.md §3.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize with optional explicit API key (falls back to secrets file).
        """
        self._api_key = api_key or _load_api_key()
        self._base_url = "https://www.googleapis.com/youtube/v3"

    @property
    def is_authenticated(self) -> bool:
        """Check if client has a valid API key."""
        return bool(self._api_key)

    def search_videos(self, query: str, max_results: int = 5) -> list[YouTubeVideo]:
        """
        Contract: search YouTube for videos matching the query.

        Args:
            query: search term (e.g., "Python machine learning tutorial")
            max_results: maximum number of videos to return (1-50)

        Returns:
            List of YouTubeVideo objects with title, channel, URL, etc.

        Raises:
            RuntimeError: if no API key is available
            ConnectionError: if YouTube API is unreachable
            RuntimeError: if API returns an error
        """
        if not self._api_key:
            raise RuntimeError(
                "YouTube API key not available. "
                "Add YOUTUBE_API_KEY to secrets/youtube.secrets."
            )

        import urllib.request
        import urllib.parse
        import urllib.error

        # Sanitize query for URL encoding
        encoded_query = urllib.parse.quote(query)

        url = (
            f"{self._base_url}/search"
            f"?part=snippet"
            f"&q={encoded_query}"
            f"&type=video"
            f"&maxResults={min(max_results, 50)}"
            f"&key={self._api_key}"
            f"&order=relevance"
        )

        req = urllib.request.Request(url, headers={"User-Agent": "Career-Engine/1.0"})

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise RuntimeError("YouTube API quota exceeded or key invalid.") from e
            if e.code == 400:
                raise RuntimeError(f"Invalid YouTube API request: {e.reason}") from e
            raise RuntimeError(f"YouTube API error: {e.code}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(f"Failed to connect to YouTube API: {e.reason}") from e

        videos = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId", "")
            if not video_id:
                continue

            video = YouTubeVideo(
                video_id=video_id,
                title=snippet.get("title", "Untitled"),
                channel=snippet.get("channelTitle", "Unknown"),
                published_at=snippet.get("publishedAt", ""),
                url=f"https://www.youtube.com/watch?v={video_id}",
                description=snippet.get("description"),
            )
            videos.append(video)

        logger.info("Found %d videos for query: %s", len(videos), query)
        return videos

    def get_video_details(self, video_id: str) -> Optional[dict[str, Any]]:
        """
        Contract: fetch extended details for a single video.

        Returns video description, duration, and tags.
        """
        if not self._api_key:
            raise RuntimeError("YouTube API key not available.")

        import urllib.request
        import urllib.parse

        url = (
            f"{self._base_url}/videos"
            f"?part=snippet,contentDetails,statistics"
            f"&id={video_id}"
            f"&key={urllib.parse.quote(self._api_key)}"
        )

        req = urllib.request.Request(url, headers={"User-Agent": "Career-Engine/1.0"})

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("items", [{}])[0] if data.get("items") else None
        except Exception as e:
            logger.warning("Failed to fetch video details for %s: %s", video_id, e)
            return None


# ---------------------------------------------------------------------------
# Summary generation
# ---------------------------------------------------------------------------

# Prompt template for video summarization (rendered at runtime)
_SUMMARY_SYSTEM = (
    "You are a research assistant that summarizes YouTube educational content. "
    "Extract the key points from the video description and any provided transcript. "
    "Be concise, factual, and highlight practical takeaways. "
    "Return ONLY valid JSON — no prose, no markdown fences."
)

_SUMMARY_USER_TEMPLATE = (
    "Summarize this YouTube video about {topic}:\n\n"
    "Title: {title}\n"
    "Channel: {channel}\n"
    "URL: {url}\n"
    "Description:\n{description}\n\n"
    "Return a JSON object with this structure:\n"
    "{{\n"
    '  "summary": "<1-3 paragraph summary of the video content>",\n'
    '  "key_takeaways": [\n'
    '    "<key point 1>",\n'
    '    "<key point 2>",\n'
    '    "<key point 3>"\n'
    "  ]\n"
    "}}\n\n"
    "Requirements:\n"
    "- Summary must be informative but concise (100-300 words)\n"
    "- Key takeaways should be actionable insights\n"
    "- Include at least 2-5 key points\n"
    "- Return valid JSON only."
)


def _generate_summary(
    video: YouTubeVideo,
    topic: str,
    client: Optional[LmStudioClient] = None,
) -> tuple[str, list[str]]:
    """
    Contract: generate an AI summary for a YouTube video via the model layer.

    Args:
        video: the YouTubeVideo to summarize
        topic: the original search topic (for context)
        client: optional LmStudioClient (uses default if not provided)

    Returns:
        Tuple of (summary_text, key_takeaways_list)

    Raises:
        RuntimeError: if model generation fails
    """
    from model_layer.client import LmStudioClient as _Client

    model_client = client or _Client()

    # Render prompt template
    registry = PromptRegistry()
    # Create a temporary template for video summarization
    system_prompt = _SUMMARY_SYSTEM
    user_prompt = _SUMMARY_USER_TEMPLATE.format(
        topic=topic,
        title=video.title,
        channel=video.channel,
        url=video.url,
        description=video.description[:2000] if video.description else "No description available.",
    )

    request = ModelRequest(
        model="local-model",  # Will use LM Studio default
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=1024,
        temperature=0.3,
    )

    try:
        response = model_client.generate(request)
    except Exception as e:
        logger.error("Model generation failed: %s", e)
        raise RuntimeError(f"Failed to generate summary: {e}") from e

    # Parse JSON response
    content = response.content or ""
    try:
        result = json.loads(content)
        summary = result.get("summary", "")
        takeaways = result.get("key_takeaways", [])
    except json.JSONDecodeError:
        # Fallback: extract JSON from text
        match = re.search(r'\{[^}]+\}', content, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                summary = result.get("summary", "")
                takeaways = result.get("key_takeaways", [])
            except json.JSONDecodeError:
                summary = content
                takeaways = []
        else:
            summary = content
            takeaways = []

    # Validate: summary must not be empty
    if not summary:
        raise RuntimeError("Generated summary is empty — regeneration required")

    return summary, takeaways


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def summarize_youtube_videos(
    topic: str,
    max_videos: int = 3,
    *,
    client: Optional[LmStudioClient] = None,
) -> list[VideoSummary]:
    """
    Contract: search YouTube for a topic and generate summaries for each video.

    This is an explicit invocation only — never called as a side effect.
    Every VideoSummary includes a traceable source URL.

    Args:
        topic: the search topic (e.g., "Python pandas tutorial")
        max_videos: number of videos to summarize (1-5)
        client: optional LmStudioClient for summary generation

    Returns:
        List of VideoSummary objects, each with a source URL

    Raises:
        RuntimeError: if YouTube API key is missing or generation fails
    """
    # Search YouTube
    search_client = YouTubeSearchClient()
    if not search_client.is_authenticated:
        raise RuntimeError(
            "YouTube API key not found. "
            "Add YOUTUBE_API_KEY to E:/secrets/youtube.secrets"
        )

    logger.info("Searching YouTube for: %s", topic)
    videos = search_client.search_videos(topic, max_results=max_videos)

    if not videos:
        logger.warning("No YouTube videos found for topic: %s", topic)
        return []

    # Generate summaries for each video
    summaries = []
    for video in videos:
        logger.info("Summarizing video: %s", video.url)
        try:
            summary_text, takeaways = _generate_summary(video, topic, client)
            summaries.append(
                VideoSummary(
                    video=video,
                    summary=summary_text,
                    key_takeaways=takeaways,
                )
            )
        except Exception as e:
            logger.error("Failed to summarize %s: %s", video.url, e)
            # Continue with other videos — don't fail the whole batch

    logger.info("Generated %d/%d summaries for topic: %s", len(summaries), len(videos), topic)
    return summaries


def print_youtube_summaries(summaries: list[VideoSummary]) -> None:
    """
    Contract: pretty-print a list of VideoSummary objects for display.

    Args:
        summaries: list of VideoSummary to print
    """
    if not summaries:
        print("No summaries generated.")
        return

    for i, summary in enumerate(summaries, 1):
        print(f"\n{'=' * 60}")
        print(f"Video {i}/{len(summaries)}")
        print(f"Title: {summary.video.title}")
        print(f"Channel: {summary.video.channel}")
        print(f"URL: {summary.video.url}")
        print(f"Published: {summary.video.published_at}")
        print(f"{'=' * 60}")
        print(f"\nSummary:\n{summary.summary}")
        print(f"\nKey Takeaways:")
        for takeaway in summary.key_takeaways:
            print(f"  - {takeaway}")


# ---------------------------------------------------------------------------
# Re-export
# ---------------------------------------------------------------------------

__all__ = [
    "YouTubeVideo",
    "VideoSummary",
    "YouTubeSearchClient",
    "summarize_youtube_videos",
    "print_youtube_summaries",
]
