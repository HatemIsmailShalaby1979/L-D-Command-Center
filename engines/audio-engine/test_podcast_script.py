# engines/audio-engine/test_podcast_script.py
#
# WHAT: Tests for the podcast script generation module.
# WHY:  Ensures the podcast script generator correctly handles topic
#       input, Journey input, schema validation, retry logic, and
#       error cases.
# BREAKS IF DELETED: No regression protection for podcast script
#       generation contract.

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add paths
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "model-layer"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from podcast_script import (
    PodcastScript,
    PodcastSegment,
    validate_podcast_script,
    generate_podcast_script,
    generate_script_from_journey,
    generate_script_from_topic,
    DEFAULT_HOST_NAME,
    DEFAULT_DURATION_MINUTES,
    DEFAULT_NUM_SEGMENTS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TOPIC = "Python for beginners"
SAMPLE_JOURNEY = {
    "topic": "Python Basics",
    "level": "beginner",
    "cards": [
        {
            "id": "card-1",
            "title": "What is Python?",
            "content": "Python is a high-level programming language.",
        }
    ],
}


def _make_valid_script_dict() -> dict:
    """Factory that returns a fresh copy of VALID_SCRIPT_DICT on each call."""
    return {
        "topic": SAMPLE_TOPIC,
        "title": "Python for Beginners Episode",
        "host_name": "John Doe",
        "duration_minutes": 15,
        "segments": [
            {
                "type": "intro",
                "speaker": "John Doe",
                "content": "Welcome to our episode about Python!",
                "duration_seconds": 60,
            },
            {
                "type": "monologue",
                "speaker": "John Doe",
                "content": "Python is a versatile language...",
                "duration_seconds": 300,
            },
            {
                "type": "dialogue",
                "speaker": "John Doe",
                "content": "Let's discuss some examples.",
                "duration_seconds": 240,
            },
            {
                "type": "conclusion",
                "speaker": "John Doe",
                "content": "Thanks for listening!",
                "duration_seconds": 60,
            },
        ],
        "speakers": ["John Doe"],
    }


# Keep the old name for backward compat, but make it a factory call result
VALID_SCRIPT_DICT = _make_valid_script_dict()

SAMPLE_SCRIPT = PodcastScript(
    topic=SAMPLE_TOPIC,
    title="Python for Beginners Episode",
    host_name="John Doe",
    duration_minutes=15,
    segments=[
        PodcastSegment(type="intro", speaker="John Doe", content="Welcome!", duration_seconds=60),
        PodcastSegment(type="conclusion", speaker="John Doe", content="Thanks!", duration_seconds=60),
    ],
    speakers=["John Doe"],
)


# ---------------------------------------------------------------------------
# Test PodcastSegment
# ---------------------------------------------------------------------------

class TestPodcastSegment:
    """Tests for PodcastSegment dataclass."""

    def test_to_dict(self):
        seg = PodcastSegment(type="intro", speaker="Host", content="Welcome", duration_seconds=60)
        assert seg.to_dict() == {
            "type": "intro",
            "speaker": "Host",
            "content": "Welcome",
            "duration_seconds": 60,
        }

    def test_from_dict(self):
        data = {
            "type": "monologue",
            "speaker": "Host",
            "content": "Hello world",
            "duration_seconds": 120,
        }
        seg = PodcastSegment.from_dict(data)
        assert seg.type == "monologue"
        assert seg.speaker == "Host"
        assert seg.content == "Hello world"
        assert seg.duration_seconds == 120

    def test_from_dict_defaults_duration(self):
        data = {"type": "intro", "speaker": "Host", "content": "Welcome"}
        seg = PodcastSegment.from_dict(data)
        assert seg.duration_seconds == 60  # default


# ---------------------------------------------------------------------------
# Test PodcastScript
# ---------------------------------------------------------------------------

class TestPodcastScript:
    """Tests for PodcastScript dataclass."""

    def test_to_dict(self):
        data = SAMPLE_SCRIPT.to_dict()
        assert data["topic"] == SAMPLE_TOPIC
        assert data["title"] == "Python for Beginners Episode"
        assert len(data["segments"]) == 2
        assert data["speakers"] == ["John Doe"]

    def test_from_dict(self):
        script = PodcastScript.from_dict(_make_valid_script_dict())
        assert script.topic == SAMPLE_TOPIC
        assert script.title == "Python for Beginners Episode"
        assert len(script.segments) == 4
        assert script.speakers == ["John Doe"]

    def test_total_duration_seconds(self):
        assert SAMPLE_SCRIPT.total_duration_seconds == 120

    def test_default_host_name(self):
        data = _make_valid_script_dict()
        del data["host_name"]
        script = PodcastScript.from_dict(data)
        assert script.host_name == DEFAULT_HOST_NAME

    def test_default_duration(self):
        data = _make_valid_script_dict()
        del data["duration_minutes"]
        script = PodcastScript.from_dict(data)
        assert script.duration_minutes == DEFAULT_DURATION_MINUTES


# ---------------------------------------------------------------------------
# Test validate_podcast_script()
# ---------------------------------------------------------------------------

class TestValidatePodcastScript:
    """Tests for schema validation."""

    def test_valid_script(self):
        is_valid, errors = validate_podcast_script(_make_valid_script_dict())
        assert is_valid
        assert errors == []

    def test_missing_topic(self):
        data = _make_valid_script_dict()
        del data["topic"]
        is_valid, errors = validate_podcast_script(data)
        assert not is_valid
        assert any("topic" in e for e in errors)

    def test_missing_title(self):
        data = _make_valid_script_dict()
        del data["title"]
        is_valid, errors = validate_podcast_script(data)
        assert not is_valid
        assert any("title" in e for e in errors)

    def test_missing_segments(self):
        data = _make_valid_script_dict()
        del data["segments"]
        is_valid, errors = validate_podcast_script(data)
        assert not is_valid
        assert any("segments" in e for e in errors)

    def test_empty_segments(self):
        data = _make_valid_script_dict()
        data["segments"] = []
        is_valid, errors = validate_podcast_script(data)
        assert not is_valid
        assert any("segments" in e for e in errors)

    def test_invalid_segment_type(self):
        data = _make_valid_script_dict()
        data["segments"][0]["type"] = "invalid"
        is_valid, errors = validate_podcast_script(data)
        assert not is_valid
        assert any("type" in e for e in errors)

    def test_missing_segment_speaker(self):
        data = _make_valid_script_dict()
        del data["segments"][0]["speaker"]
        is_valid, errors = validate_podcast_script(data)
        assert not is_valid
        assert any("speaker" in e for e in errors)

    def test_missing_segment_content(self):
        data = _make_valid_script_dict()
        del data["segments"][0]["content"]
        is_valid, errors = validate_podcast_script(data)
        assert not is_valid
        assert any("content" in e for e in errors)

    def test_empty_speakers(self):
        data = _make_valid_script_dict()
        data["speakers"] = []
        is_valid, errors = validate_podcast_script(data)
        assert not is_valid
        assert any("speakers" in e for e in errors)


# ---------------------------------------------------------------------------
# Test generate_podcast_script() — error cases
# ---------------------------------------------------------------------------

class TestGeneratePodcastScriptErrors:
    """Tests for generate_podcast_script() error handling."""

    def test_neither_topic_nor_journey_raises(self):
        with pytest.raises(ValueError, match="Either 'topic' or 'journey' must be provided"):
            generate_podcast_script()

    def test_empty_topic_raises(self):
        with pytest.raises(ValueError, match="Either 'topic' or 'journey' must be provided"):
            generate_podcast_script(topic="")


# ---------------------------------------------------------------------------
# Test generate_podcast_script() — happy path (mocked)
# ---------------------------------------------------------------------------

class TestGeneratePodcastScript:
    """Tests for generate_podcast_script() success cases."""

    @patch("podcast_script._call_model")
    def test_generates_from_topic(self, mock_call):
        mock_call.return_value = json.dumps(VALID_SCRIPT_DICT)
        script = generate_podcast_script(topic=SAMPLE_TOPIC)
        assert isinstance(script, PodcastScript)
        assert script.topic == SAMPLE_TOPIC
        mock_call.assert_called_once()

    @patch("podcast_script._call_model")
    def test_generates_from_journey(self, mock_call):
        mock_call.return_value = json.dumps(VALID_SCRIPT_DICT)
        script = generate_podcast_script(journey=SAMPLE_JOURNEY)
        assert isinstance(script, PodcastScript)
        # The script topic comes from the mock response, not the journey
        # What matters is that the journey's topic was used in the prompt
        call_args = mock_call.call_args
        assert SAMPLE_JOURNEY["topic"] in call_args[0][1]  # user prompt should contain journey topic
        mock_call.assert_called_once()

    @patch("podcast_script._call_model")
    def test_passes_num_segments(self, mock_call):
        mock_call.return_value = json.dumps(VALID_SCRIPT_DICT)
        generate_podcast_script(topic=SAMPLE_TOPIC, num_segments=10)
        # Verify the prompt includes num_segments
        call_args = mock_call.call_args
        assert "10" in call_args[0][1]  # user prompt should contain num_segments

    @patch("podcast_script._call_model")
    def test_passes_duration_minutes(self, mock_call):
        mock_call.return_value = json.dumps(VALID_SCRIPT_DICT)
        generate_podcast_script(topic=SAMPLE_TOPIC, duration_minutes=30)
        call_args = mock_call.call_args
        assert "30" in call_args[0][1]

    @patch("podcast_script._call_model")
    def test_passes_host_name(self, mock_call):
        mock_call.return_value = json.dumps(VALID_SCRIPT_DICT)
        generate_podcast_script(topic=SAMPLE_TOPIC, host_name="Custom Host")
        # Verify the function doesn't crash and calls the model
        mock_call.assert_called_once()

    @patch("podcast_script._call_model")
    def test_retries_on_validation_failure(self, mock_call):
        """Should retry when initial validation fails."""
        # First call returns invalid JSON, second call returns valid
        mock_call.side_effect = [
            json.dumps({"invalid": "data"}),
            json.dumps(VALID_SCRIPT_DICT),
        ]
        script = generate_podcast_script(topic=SAMPLE_TOPIC)
        assert isinstance(script, PodcastScript)
        assert mock_call.call_count == 2

    @patch("podcast_script._call_model")
    def test_raises_after_max_retries(self, mock_call):
        """Should raise after exhausting retries."""
        from schema import SchemaValidationError
        # All calls return invalid data
        mock_call.return_value = json.dumps({"invalid": "data"})
        with pytest.raises(SchemaValidationError):
            generate_podcast_script(topic=SAMPLE_TOPIC)

    @patch("podcast_script._call_model")
    def test_raises_on_extract_failure(self, mock_call):
        """Should raise when JSON extraction fails."""
        mock_call.return_value = "Not valid JSON at all"
        from schema import SchemaValidationError
        with pytest.raises(SchemaValidationError, match="Could not extract JSON"):
            generate_podcast_script(topic=SAMPLE_TOPIC)


# ---------------------------------------------------------------------------
# Test convenience functions
# ---------------------------------------------------------------------------

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @patch("podcast_script.generate_podcast_script")
    def test_generate_script_from_journey(self, mock_generate):
        mock_generate.return_value = SAMPLE_SCRIPT
        result = generate_script_from_journey(SAMPLE_JOURNEY)
        mock_generate.assert_called_once_with(journey=SAMPLE_JOURNEY)
        assert result == SAMPLE_SCRIPT

    @patch("podcast_script.generate_podcast_script")
    def test_generate_script_from_topic(self, mock_generate):
        mock_generate.return_value = SAMPLE_SCRIPT
        result = generate_script_from_topic(SAMPLE_TOPIC)
        mock_generate.assert_called_once_with(topic=SAMPLE_TOPIC)
        assert result == SAMPLE_SCRIPT


# ---------------------------------------------------------------------------
# Manual verification
# ---------------------------------------------------------------------------

def test_manual_verification():
    """
    Contract: Manual verification for podcast script generation.

    To test manually:
    1. Ensure LM Studio is running on localhost:1234
    2. Run: python -c "from engines.audio_engine.podcast_script import generate_podcast_script; script = generate_podcast_script('Python for beginners')"
    3. Print the script to verify structure
    """
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
