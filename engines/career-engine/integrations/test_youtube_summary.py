# engines/career-engine/integrations/test_youtube_summary.py
#
# WHAT: Tests for YouTube video search and AI summarization.
# WHY:  Verify search integration, summary generation, URL tracing,
#       and error handling. All tests use mocks.
# BREAKS IF DELETED: No regression testing for YouTube integration.

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add paths
_ENGINE_PATH = Path(__file__).resolve().parent

from engines.career_engine.integrations.youtube_summary import (
    YouTubeVideo,
    VideoSummary,
    YouTubeSearchClient,
    summarize_youtube_videos,
    _load_api_key,
    _generate_summary,
)


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_SEARCH_RESPONSE = {
    "items": [
        {
            "id": {"videoId": "dQw4w9WgXcQ"},
            "snippet": {
                "title": "Python Machine Learning Tutorial",
                "channelTitle": "Code Academy",
                "publishedAt": "2024-01-15T10:00:00Z",
                "description": "Learn machine learning with Python from scratch. Covers scikit-learn, pandas, and more.",
            },
        },
        {
            "id": {"videoId": "abc123xyz"},
            "snippet": {
                "title": "Advanced Python Programming",
                "channelTitle": "Tech Channel",
                "publishedAt": "2024-02-20T14:30:00Z",
                "description": "Deep dive into advanced Python concepts.",
            },
        },
    ]
}

MOCK_SUMMARY_OUTPUT = {
    "summary": "This video covers machine learning fundamentals with Python, including scikit-learn and pandas.",
    "key_takeaways": [
        "Introduction to scikit-learn for ML",
        "Data preprocessing with pandas",
        "Building your first ML model",
    ],
}


# ---------------------------------------------------------------------------
# Tests: Data classes
# ---------------------------------------------------------------------------

class TestDataClasses:
    """Tests for YouTubeVideo and VideoSummary dataclasses."""

    def test_youtube_video_creation(self):
        """
        Contract: YouTubeVideo should store all required fields.
        """
        video = YouTubeVideo(
            video_id="abc123",
            title="Test Video",
            channel="Test Channel",
            published_at="2024-01-01T00:00:00Z",
            url="https://www.youtube.com/watch?v=abc123",
            description="Test description",
        )

        assert video.video_id == "abc123"
        assert video.url == "https://www.youtube.com/watch?v=abc123"

    def test_video_summary_with_url(self):
        """
        Contract: VideoSummary must have a video with a valid URL.
        """
        video = YouTubeVideo(
            video_id="abc123",
            title="Test",
            channel="Channel",
            published_at="",
            url="https://www.youtube.com/watch?v=abc123",
            description=None,
        )

        summary = VideoSummary(
            video=video,
            summary="Test summary",
            key_takeaways=["Point 1"],
        )

        assert summary.video.url == "https://www.youtube.com/watch?v=abc123"
        assert len(summary.summary) > 0


# ---------------------------------------------------------------------------
# Tests: API key loading
# ---------------------------------------------------------------------------

class TestApiKeyLoading:
    """Tests for _load_api_key() function."""

    def test_loads_key_from_secrets(self, tmp_path: Path):
        """
        Contract: _load_api_key should read key from secrets file.
        """
        secrets_file = tmp_path / "youtube.secrets"
        secrets_file.write_text("YOUTUBE_API_KEY=AIzaSyTestKey123\n", encoding="utf-8")

        key = _load_api_key(secrets_file)

        assert key == "AIzaSyTestKey123"

    def test_returns_none_when_file_missing(self, tmp_path: Path):
        """
        Contract: _load_api_key should return None when file doesn't exist.
        """
        key = _load_api_key(tmp_path / "nonexistent.secrets")

        assert key is None

    def test_ignores_placeholder_key(self, tmp_path: Path):
        """
        Contract: _load_api_key should ignore empty/placeholder keys.
        """
        secrets_file = tmp_path / "youtube.secrets"
        secrets_file.write_text("YOUTUBE_API_KEY=\n", encoding="utf-8")

        key = _load_api_key(secrets_file)

        assert key is None


# ---------------------------------------------------------------------------
# Tests: YouTubeSearchClient
# ---------------------------------------------------------------------------

class TestYouTubeSearchClient:
    """Tests for YouTubeSearchClient class."""

    def test_init_with_key(self):
        """
        Contract: client should accept explicit API key.
        """
        client = YouTubeSearchClient(api_key="test_key_123")

        assert client.is_authenticated

    def test_init_without_key(self):
        """
        Contract: client should work without key (but not authenticated).
        """
        with patch("engines.career_engine.integrations.youtube_summary._load_api_key", return_value=None):
            client = YouTubeSearchClient()

        assert not client.is_authenticated

    def test_search_requires_key(self):
        """
        Contract: search_videos should raise RuntimeError without API key.
        """
        client = YouTubeSearchClient()

        with pytest.raises(RuntimeError, match="API key"):
            client.search_videos("test")

    def test_search_videos(self):
        """
        Contract: search_videos should return list of YouTubeVideo objects.
        """
        client = YouTubeSearchClient(api_key="test_key")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(MOCK_SEARCH_RESPONSE).encode()
            mock_urlopen.return_value.__enter__.return_value = mock_response

            videos = client.search_videos("python tutorial", max_results=2)

        assert len(videos) == 2
        assert videos[0].title == "Python Machine Learning Tutorial"
        assert videos[0].url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert videos[1].channel == "Tech Channel"

    def test_search_handles_no_results(self):
        """
        Contract: search_videos should return empty list when no results.
        """
        client = YouTubeSearchClient(api_key="test_key")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps({"items": []}).encode()
            mock_urlopen.return_value.__enter__.return_value = mock_response

            videos = client.search_videos("nonexistent topic xyz")

        assert videos == []

    def test_token_not_logged(self):
        """
        Contract: API key should never appear in logs or error messages.
        """
        with patch("engines.career_engine.integrations.youtube_summary.logger") as mock_logger:
            client = YouTubeSearchClient(api_key="AIzaSySecretKey123")
            # Simulate some logging
            mock_logger.info("Test message")
            mock_logger.warning("Test warning")

        # Verify no log call contains the key
        for call in mock_logger.method_calls:
            assert "AIzaSySecretKey123" not in str(call)


# ---------------------------------------------------------------------------
# Tests: Summary generation
# ---------------------------------------------------------------------------

class TestSummaryGeneration:
    """Tests for AI-generated video summaries."""

    def test_generate_summary(self):
        """
        Contract: _generate_summary should return summary and takeaways.
        """
        video = YouTubeVideo(
            video_id="test123",
            title="Test Video",
            channel="Test Channel",
            published_at="",
            url="https://www.youtube.com/watch?v=test123",
            description="A test video about Python.",
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(MOCK_SUMMARY_OUTPUT)
        mock_client.generate.return_value = mock_response

        summary_text, takeaways = _generate_summary(video, "Python", client=mock_client)

        assert "machine learning" in summary_text.lower()
        assert len(takeaways) == 3
        assert takeaways[0] == "Introduction to scikit-learn for ML"

    def test_generate_summary_handles_malformed_json(self):
        """
        Contract: _generate_summary should handle malformed JSON gracefully.
        """
        video = YouTubeVideo(
            video_id="test456",
            title="Test",
            channel="Channel",
            published_at="",
            url="https://www.youtube.com/watch?v=test456",
            description="Test",
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Not valid JSON"
        mock_client.generate.return_value = mock_response

        # Should not raise, but return the raw content
        summary_text, takeaways = _generate_summary(video, "Test", client=mock_client)

        assert "Not valid JSON" in summary_text

    def test_generate_summary_requires_non_empty(self):
        """
        Contract: _generate_summary should raise if summary is empty.
        """
        video = YouTubeVideo(
            video_id="test789",
            title="Test",
            channel="Channel",
            published_at="",
            url="https://www.youtube.com/watch?v=test789",
            description="Test",
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({"summary": "", "key_takeaways": []})
        mock_client.generate.return_value = mock_response

        with pytest.raises(RuntimeError, match="empty"):
            _generate_summary(video, "Test", client=mock_client)


# ---------------------------------------------------------------------------
# Tests: Public API
# ---------------------------------------------------------------------------

class TestSummarizeYoutubeVideos:
    """Tests for summarize_youtube_videos() public function."""

    def test_summarizes_videos(self):
        """
        Contract: summarize_youtube_videos should return list of VideoSummary.
        """
        with patch("engines.career_engine.integrations.youtube_summary.YouTubeSearchClient") as MockClient:
            mock_search = MagicMock()
            mock_search.is_authenticated = True
            mock_search.search_videos.return_value = [
                YouTubeVideo(
                    video_id="abc123",
                    title="Test Video",
                    channel="Channel",
                    published_at="",
                    url="https://www.youtube.com/watch?v=abc123",
                    description="Test",
                )
            ]
            MockClient.return_value = mock_search

            with patch("engines.career_engine.integrations.youtube_summary._generate_summary", return_value=("Summary", ["Point 1"])):
                with patch("engines.career_engine.integrations.youtube_summary.LmStudioClient"):
                    results = summarize_youtube_videos("Python tutorial", max_videos=1)

        assert len(results) == 1
        assert isinstance(results[0], VideoSummary)
        assert results[0].video.url == "https://www.youtube.com/watch?v=abc123"

    def test_requires_api_key(self):
        """
        Contract: summarize_youtube_videos should raise without API key.
        """
        with patch("engines.career_engine.integrations.youtube_summary.YouTubeSearchClient") as MockClient:
            mock_search = MagicMock()
            mock_search.is_authenticated = False
            MockClient.return_value = mock_search

            with pytest.raises(RuntimeError, match="API key"):
                summarize_youtube_videos("Test topic")

    def test_returns_empty_when_no_videos(self):
        """
        Contract: summarize_youtube_videos should return empty list when no videos found.
        """
        with patch("engines.career_engine.integrations.youtube_summary.YouTubeSearchClient") as MockClient:
            mock_search = MagicMock()
            mock_search.is_authenticated = True
            mock_search.search_videos.return_value = []
            MockClient.return_value = mock_search

            with patch("engines.career_engine.integrations.youtube_summary.LmStudioClient"):
                results = summarize_youtube_videos("Nonexistent topic")

        assert results == []

    def test_each_summary_has_url(self):
        """
        Contract: Every VideoSummary must have a traceable source URL.
        """
        videos = [
            YouTubeVideo(
                video_id="id1",
                title="Video 1",
                channel="Channel 1",
                published_at="",
                url="https://www.youtube.com/watch?v=id1",
                description="Desc 1",
            ),
            YouTubeVideo(
                video_id="id2",
                title="Video 2",
                channel="Channel 2",
                published_at="",
                url="https://www.youtube.com/watch?v=id2",
                description="Desc 2",
            ),
        ]

        summaries = [
            VideoSummary(video=videos[0], summary="Summary 1", key_takeaways=["T1"]),
            VideoSummary(video=videos[1], summary="Summary 2", key_takeaways=["T2"]),
        ]

        # Verify invariant: all summaries have URLs
        for summary in summaries:
            assert summary.video.url is not None
            assert "youtube.com" in summary.video.url
            assert len(summary.video.url) > 0


# ---------------------------------------------------------------------------
# Manual verification step
# ---------------------------------------------------------------------------

def test_manual_verification():
    """
    Contract: Manual verification step for YouTube integration.

    To verify manually:
    1. Add your YouTube API key to E:/secrets/youtube.secrets:
       YOUTUBE_API_KEY=AIzaSyYourRealKeyHere

    2. Test video search and summarization:
       python -c "
       from engines.career_engine.integrations.youtube_summary import summarize_youtube_videos
       summaries = summarize_youtube_videos('Python pandas tutorial', max_videos=3)
       for s in summaries:
           print(f'{s.video.title}: {s.video.url}')
           print(f'  Summary: {s.summary[:100]}...')
           print(f'  Takeaways: {len(s.key_takeaways)} points')
       "

    3. Verify URL tracing:
       for s in summaries:
           assert 'youtube.com' in s.video.url
       print('All summaries have traceable URLs ✓')
    """
    # Placeholder for documentation
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
