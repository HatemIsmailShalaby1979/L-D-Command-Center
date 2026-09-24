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

from engines.audio_engine.podcast_script import (
    PodcastScript,
    PodcastSegment,
    validate_podcast_script,
    generate_podcast_script,
    generate_script_from_journey,
    generate_script_from_topic,
    make_length_validator,
    words_for_duration,
    content_word_count,
    DEFAULT_HOST_NAME,
    DEFAULT_DURATION_MINUTES,
    DEFAULT_NUM_SEGMENTS,
    MIN_CONTENT_WPM,
    WORD_BUDGET_TOLERANCE,
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


def _pad_words(phrase: str, n: int) -> str:
    """Repeat `phrase` until it has at least `n` whitespace-separated words."""
    base = (phrase + " ").split()
    if not base:
        base = ["word"]
    out = []
    while len(out) < n:
        out.extend(base)
    return " ".join(out[:n])


def _make_valid_script_dict(*, duration_minutes: int = 15,
                            min_words: bool = True) -> dict:
    """Factory that returns a fresh valid script.

    With min_words=True (default), each segment's content is padded to the
    length validator's word floor so generate_podcast_script() accepts it.
    Conversation-contract tests that only need structure can pass
    min_words=False.
    """
    # 15 min × 170 WPM × 0.90 tolerance ≈ 2295 words total.
    # Intro/conclusion ~10%, body ~80% split across monologue+dialogue.
    if min_words:
        # Pad past the validator floor: intro/body rounding can leave the
        # fixture one or two words short of the exact threshold.
        total_target = int(words_for_duration(
            duration_minutes,
            wpm=int(MIN_CONTENT_WPM * WORD_BUDGET_TOLERANCE)) * 1.05) + 5
        intro_w = max(30, total_target // 10)
        body_w = max(40, (total_target - 2 * intro_w) // 2)
        c_intro = _pad_words("Welcome to our episode about Python!", intro_w)
        c_monologue = _pad_words(
            "Python is a versatile language used for scripts and web apps.",
            body_w)
        c_dialogue = _pad_words(
            "Let us discuss some examples and practical patterns together.",
            body_w)
        c_conclusion = _pad_words("Thanks for listening to the show!",
                                  intro_w + 20)  # buffer for floor
    else:
        c_intro = "Welcome to our episode about Python!"
        c_monologue = "Python is a versatile language..."
        c_dialogue = "Let's discuss some examples."
        c_conclusion = "Thanks for listening!"
    return {
        "topic": SAMPLE_TOPIC,
        "title": "Python for Beginners Episode",
        "host_name": "Alex",
        "co_host_name": "Maya",
        "duration_minutes": duration_minutes,
        "segments": [
            {
                "type": "intro",
                "speaker": "Alex",
                "content": c_intro,
                "duration_seconds": 60,
            },
            {
                "type": "monologue",
                "speaker": "Maya",
                "content": c_monologue,
                "duration_seconds": 300,
            },
            {
                "type": "dialogue",
                "speaker": "Alex",
                "content": c_dialogue,
                "duration_seconds": 240,
            },
            {
                "type": "conclusion",
                "speaker": "Maya",
                "content": c_conclusion,
                "duration_seconds": 60,
            },
        ],
        "speakers": ["Alex", "Maya"],
    }


# Keep the old name for backward compat, but make it a factory call result
VALID_SCRIPT_DICT = _make_valid_script_dict(min_words=False)

SAMPLE_SCRIPT = PodcastScript(
    topic=SAMPLE_TOPIC,
    title="Python for Beginners Episode",
    host_name="Alex",
    co_host_name="Maya",
    duration_minutes=15,
    segments=[
        PodcastSegment(type="intro", speaker="Alex", content="Welcome!", duration_seconds=60),
        PodcastSegment(type="conclusion", speaker="Maya", content="Thanks!", duration_seconds=60),
    ],
    speakers=["Alex", "Maya"],
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
        assert data["speakers"] == ["Alex", "Maya"]

    def test_from_dict(self):
        script = PodcastScript.from_dict(_make_valid_script_dict())
        assert script.topic == SAMPLE_TOPIC
        assert script.title == "Python for Beginners Episode"
        assert len(script.segments) == 4
        assert script.speakers == ["Alex", "Maya"]

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




class TestLengthValidator:
    """Word-budget contract: TTS duration follows content words."""

    def test_words_for_duration(self):
        assert words_for_duration(5) == 5 * 200
        assert words_for_duration(1, wpm=100) == 100

    def test_content_word_count(self):
        data = _make_valid_script_dict(min_words=False)
        assert content_word_count(data) > 0
        assert content_word_count({"segments": []}) == 0

    def test_validator_accepts_padded_script(self):
        data = _make_valid_script_dict(duration_minutes=5)
        # Build validator for same duration
        v = make_length_validator(5)
        ok, errors = v(data)
        assert ok, errors

    def test_validator_rejects_thin_script(self):
        data = _make_valid_script_dict(min_words=False, duration_minutes=15)
        v = make_length_validator(15)
        ok, errors = v(data)
        assert not ok
        assert any("words" in e and "length" in e for e in errors)

    def test_plain_schema_validator_ignores_word_budget(self):
        """validate_podcast_script stays schema-only (tests/conversation)."""
        data = _make_valid_script_dict(min_words=False, duration_minutes=15)
        ok, errors = validate_podcast_script(data)
        assert ok, errors

    def test_segment_word_budget_floor(self):
        from engines.audio_engine.podcast_script import segment_word_budget
        assert segment_word_budget(800, 6) >= 40
        assert segment_word_budget(10, 6) == 40  # floor


class _ScriptedClient:
    """Fake LmStudioClient returning queued raw strings; records requests."""
    def __init__(self, *raw_outputs):
        self.outs = list(raw_outputs)
        self.requests = []
    def generate(self, request):
        from types import SimpleNamespace
        self.requests.append(request)
        raw = self.outs.pop(0) if len(self.outs) > 1 else self.outs[0]
        return SimpleNamespace(content=raw, model="default",
                               finish_reason="stop", tool_calls=None, raw={})

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

    @staticmethod
    def _client_for(duration_minutes: int = 15, *extra_outputs):
        """Scripted client returning a length-compliant script for duration."""
        payload = json.dumps(
            _make_valid_script_dict(duration_minutes=duration_minutes))
        return _ScriptedClient(payload, *extra_outputs)

    def test_generates_from_topic(self):
        client = self._client_for()
        script = generate_podcast_script(topic=SAMPLE_TOPIC, client=client)
        assert isinstance(script, PodcastScript)
        assert script.topic == SAMPLE_TOPIC
        assert len(client.requests) == 1

    def test_generates_from_journey(self):
        client = self._client_for()
        script = generate_podcast_script(journey=SAMPLE_JOURNEY, client=client)
        assert isinstance(script, PodcastScript)
        # The journey's topic must appear in the user prompt
        user_prompt = client.requests[0].messages[1]["content"]
        assert SAMPLE_JOURNEY["topic"] in user_prompt
        assert len(client.requests) == 1

    def test_passes_num_segments(self):
        client = self._client_for()
        generate_podcast_script(topic=SAMPLE_TOPIC, num_segments=10, client=client)
        user_prompt = client.requests[0].messages[1]["content"]
        assert "10" in user_prompt

    def test_passes_duration_minutes(self):
        client = self._client_for(duration_minutes=30)
        generate_podcast_script(topic=SAMPLE_TOPIC, duration_minutes=30,
                                client=client)
        user_prompt = client.requests[0].messages[1]["content"]
        assert "30" in user_prompt

    def test_prompt_carries_word_budget(self):
        """Word budget (not duration_seconds) is what drives TTS length."""
        client = self._client_for()
        generate_podcast_script(topic=SAMPLE_TOPIC, duration_minutes=5,
                                client=client)
        user_prompt = client.requests[0].messages[1]["content"]
        # 5 min × 200 WPM planned total must appear in the prompt.
        assert "1000" in user_prompt  # total_words
        assert "words" in user_prompt.lower()

    def test_passes_host_name(self):
        client = self._client_for()
        script = generate_podcast_script(topic=SAMPLE_TOPIC,
                                         host_name="Custom Host", client=client)
        assert isinstance(script, PodcastScript)
        assert len(client.requests) == 1

    def test_prompt_carries_language_level_and_host(self):
        """P3.1: template must interpolate language, level, and host_name."""
        client = self._client_for()
        generate_podcast_script(
            topic=SAMPLE_TOPIC, num_segments=5, host_name="Klara",
            language="German", level="advanced", client=client,
        )
        user_prompt = client.requests[0].messages[1]["content"]
        assert "entirely" in user_prompt and "German" in user_prompt
        assert "advanced" in user_prompt
        assert "Klara" in user_prompt

    def test_length_validator_rejects_thin_content(self):
        """Thin content must fail the length floor and trigger a retry."""
        thin = json.dumps(_make_valid_script_dict(min_words=False))
        fat = json.dumps(_make_valid_script_dict())
        client = _ScriptedClient(thin, fat)
        script = generate_podcast_script(topic=SAMPLE_TOPIC, client=client)
        assert isinstance(script, PodcastScript)
        assert len(client.requests) == 2

    def test_retries_on_validation_failure(self):
        """Should retry when initial validation fails."""
        client = _ScriptedClient(
            json.dumps({"invalid": "data"}),
            json.dumps(_make_valid_script_dict()),
        )
        script = generate_podcast_script(topic=SAMPLE_TOPIC, client=client)
        assert isinstance(script, PodcastScript)
        assert len(client.requests) == 2

    def test_raises_after_max_retries(self):
        """Should raise after exhausting retries."""
        from model_layer.schema import SchemaValidationError
        client = _ScriptedClient(json.dumps({"invalid": "data"}))  # repeats last
        with pytest.raises(SchemaValidationError):
            generate_podcast_script(topic=SAMPLE_TOPIC, client=client)

    def test_raises_on_extract_failure(self):
        """Should raise when JSON extraction fails."""
        from model_layer.schema import SchemaValidationError
        client = _ScriptedClient("Not valid JSON at all")  # repeats last
        with pytest.raises(SchemaValidationError, match="could not extract JSON"):
            generate_podcast_script(topic=SAMPLE_TOPIC, client=client)


# ---------------------------------------------------------------------------
# Test convenience functions
# ---------------------------------------------------------------------------

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @patch("engines.audio_engine.podcast_script.generate_podcast_script")
    def test_generate_script_from_journey(self, mock_generate):
        mock_generate.return_value = SAMPLE_SCRIPT
        result = generate_script_from_journey(SAMPLE_JOURNEY)
        mock_generate.assert_called_once_with(journey=SAMPLE_JOURNEY)
        assert result == SAMPLE_SCRIPT

    @patch("engines.audio_engine.podcast_script.generate_podcast_script")
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


# ---------------------------------------------------------------------------
# Conversation contract (a podcast is TWO people talking — review 2026-08-25)
# ---------------------------------------------------------------------------

class TestConversationContract:
    from engines.audio_engine.podcast_script import validate_podcast_script
    def _script(self):
        return validate_podcast_script

    def test_single_speaker_rejected_as_audiobook(self):
        data = _make_valid_script_dict()
        for seg in data["segments"]:
            seg["speaker"] = "Alex"
        ok, errors = self._script()(data)
        assert not ok
        assert any("audiobook" in e for e in errors)

    def test_consecutive_same_speaker_rejected(self):
        data = _make_valid_script_dict()
        data["segments"][1]["speaker"] = "Alex"  # Alex twice in a row
        ok, errors = self._script()(data)
        assert not ok and any("alternate" in e for e in errors)

    def test_dominant_host_rebalanced(self):
        data = _make_valid_script_dict()
        # base is alternating A/M/A/M; two extra Alex turns -> 4/6 = 67%
        extra = [{"type": "dialogue", "speaker": "Alex",
                  "content": "more", "duration_seconds": 30}
                 for _ in range(2)]
        data["segments"] = data["segments"] + extra
        ok, errors = self._script()(data)
        assert not ok and any("rebalance" in e for e in errors)

    def test_template_names_both_hosts(self):
        import pytest
        from model_layer.prompts import PromptRegistry
        system, user, _ = PromptRegistry().render("podcast_script_generate", {
            "topic": "t", "num_segments": 6, "duration_minutes": 5,
            "segment_duration_seconds": 50,
            "segment_words": 167, "total_words": 1000,
            "host_name": "Alex", "co_host_name": "Maya",
            "language": "English", "level": "beginner"})
        assert "Maya" in user and "EXACTLY TWO hosts" in user

    def test_retry_template_carries_word_budget(self):
        from model_layer.prompts import PromptRegistry
        _, user, _ = PromptRegistry().render("podcast_script_retry", {
            "errors": "content too short", "topic": "t",
            "num_segments": 6, "duration_minutes": 5,
            "segment_duration_seconds": 50,
            "segment_words": 167, "total_words": 1000,
            "host_name": "Alex", "co_host_name": "Maya",
            "language": "English", "level": "beginner"})
        assert "1000" in user and "WORD COUNT" in user
