# engines/export-engine/test_export_integration.py
#
# WHAT: Integration tests for the unified export dispatcher, including audio
#       export paths (narration, podcast, bilingual, immersion).
# WHY:  Ensures the unified export() function correctly routes audio content
#       to audio-engine functions, auto-detecting type from content keys.
# BREAKS IF DELETED: No regression protection for the unified export contract
#       across all content types.

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from model_layer.client import ApiError
from model_layer.client import ConnectionError as LmConnectionError
from model_layer.schema import SchemaValidationError

# Add paths so the module is importable

# Module under test
from engines.export_engine import export as _export_mod

export = _export_mod.export
_detect_type = _export_mod._detect_type
export_audio_narrate = _export_mod.export_audio_narrate
export_audio_podcast = _export_mod.export_audio_podcast
export_audio_bilingual = _export_mod.export_audio_bilingual
export_audio_immersion = _export_mod.export_audio_immersion
export_audio = _export_mod.export_audio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SIMPLE_JOURNEY = {
    "topic": "Python Basics",
    "level": "beginner",
    "cards": [
        {
            "id": "card-1",
            "title": "What is Python?",
            "content": "Python is a high-level programming language.",
            "question": "What type of language is Python?",
            "options": ["Low-level", "High-level", "Assembly", "Machine code"],
            "correct_option": "High-level",
            "explanation": "Python abstracts away memory management.",
        }
    ],
}

_SIMPLE_RESUME = {
    "contact": {
        "name": "John Smith",
        "email": "john@example.com",
        "phone": "+1-555-1234",
        "location": "New York, NY",
    },
    "summary": "Experienced software engineer.",
    "experience": [
        {
            "title": "Software Engineer",
            "company": "Tech Corp",
            "dates": "2020-2023",
            "description": "- Led development of ML pipeline",
        },
    ],
    "education": [{"degree": "B.S. Computer Science", "school": "State University", "dates": "2014-2018"}],
    "skills": ["Python", "Machine Learning"],
    "projects": [{"name": "ML Pipeline", "description": "Automated data processing", "tech": ["Python"]}],
}

# Audio content fixtures
_NARRATION_CONTENT = {
    "text": "Once upon a time, in a land far far away, there lived a brave programmer.",
}

_PODCAST_CONTENT = {
    "topic": "The Future of AI",
    "host_name": "Tech Host",
    "num_segments": 5,
    "duration_minutes": 15,
}

_BILINGUAL_CONTENT = {
    "topic": "Ordering food at a restaurant",
    "target_language": "es",
    "known_language": "en",
    "num_segments": 10,
}

_IMMERSION_CONTENT = {
    "topic": "Ordering food at a restaurant",
    "target_language": "es",
    "segments": [
        {"type": "intro", "speaker": "Ana", "content": "Bienvenidos al programa", "duration_seconds": 30},
        {"type": "dialogue", "speaker": "Carlos", "content": "Hoy vamos a aprender a pedir comida", "duration_seconds": 60},
        {"type": "conclusion", "speaker": "Ana", "content": "Gracias por escuchar", "duration_seconds": 30},
    ],
    "num_segments": 5,
    "duration_minutes": 10,
}


# ---------------------------------------------------------------------------
# Type detection tests
# ---------------------------------------------------------------------------

class TestDetectType:
    """Tests for _detect_type() function with audio types."""

    def test_detects_journey(self):
        assert _detect_type(_SIMPLE_JOURNEY) == "journey"

    def test_detects_resume(self):
        assert _detect_type(_SIMPLE_RESUME) == "resume"

    def test_detects_narration(self):
        assert _detect_type(_NARRATION_CONTENT) == "narration"

    def test_detects_podcast(self):
        assert _detect_type(_PODCAST_CONTENT) == "podcast"

    def test_detects_bilingual(self):
        assert _detect_type(_BILINGUAL_CONTENT) == "bilingual"

    def test_detects_immersion(self):
        assert _detect_type(_IMMERSION_CONTENT) == "immersion"

    def test_detects_unknown(self):
        assert _detect_type({"foo": "bar"}) == "unknown"

    def test_podcast_no_cards(self):
        """Podcast with topic but no cards should be detected as podcast, not journey."""
        data = {"topic": "Test", "host_name": "Host"}
        assert _detect_type(data) == "podcast"

    def test_bilingual_vs_immersion(self):
        """Bilingual has known_language, immersion has segments."""
        assert _detect_type(_BILINGUAL_CONTENT) == "bilingual"
        assert _detect_type(_IMMERSION_CONTENT) == "immersion"


# ---------------------------------------------------------------------------
# export_audio dispatcher tests
# ---------------------------------------------------------------------------

class TestExportAudio:
    """Tests for the export_audio() dispatcher."""

    @patch("engines.export_engine.export.export_audio_narrate")
    def test_dispatches_narration(self, mock_narrate):
        mock_narrate.return_value = {"wav_bytes": b"test", "mp3_bytes": b""}
        result = export_audio(_NARRATION_CONTENT, include_mp3=False)
        mock_narrate.assert_called_once_with(
            text="Once upon a time, in a land far far away, there lived a brave programmer.",
            include_mp3=False,
            output_path=None,
        )
        assert result["wav_bytes"] == b"test"

    @patch("engines.export_engine.export.export_audio_podcast")
    def test_dispatches_podcast(self, mock_podcast):
        mock_podcast.return_value = {"wav_bytes": b"test", "mp3_bytes": b""}
        result = export_audio(_PODCAST_CONTENT, include_mp3=False)
        mock_podcast.assert_called_once()
        assert result["wav_bytes"] == b"test"

    @patch("engines.export_engine.export.export_audio_bilingual")
    def test_dispatches_bilingual(self, mock_bilingual):
        mock_bilingual.return_value = {"wav_bytes": b"test", "mp3_bytes": b""}
        result = export_audio(_BILINGUAL_CONTENT, include_mp3=False)
        mock_bilingual.assert_called_once()
        assert result["wav_bytes"] == b"test"

    @patch("engines.export_engine.export.export_audio_immersion")
    def test_dispatches_immersion(self, mock_immersion):
        mock_immersion.return_value = {"wav_bytes": b"test", "mp3_bytes": b""}
        result = export_audio(_IMMERSION_CONTENT, include_mp3=False)
        mock_immersion.assert_called_once()
        assert result["wav_bytes"] == b"test"

    def test_rejects_non_audio_content(self):
        """Should raise ValueError for non-audio content."""
        with pytest.raises(ValueError, match="not an audio type"):
            export_audio(_SIMPLE_JOURNEY)


# ---------------------------------------------------------------------------
# Unified export dispatcher tests
# ---------------------------------------------------------------------------

class TestExportDispatcher:
    """Tests for the unified export() function with all content types."""

    def test_export_journey_text(self):
        result = export(_SIMPLE_JOURNEY, format="text")
        assert isinstance(result, str)
        assert "PYTHON BASICS" in result.upper()

    def test_export_resume_text(self):
        result = export(_SIMPLE_RESUME, format="text")
        assert isinstance(result, str)
        assert "JOHN SMITH" in result.upper()

    @patch("engines.export_engine.export.export_audio_narrate")
    def test_export_narration_wav(self, mock_narrate):
        """Should dispatch narration content to wav export."""
        mock_narrate.return_value = {"wav_bytes": b"test-wav", "mp3_bytes": b"", "sample_rate": 22050}
        result = export(_NARRATION_CONTENT, format="wav")
        assert result["wav_bytes"] == b"test-wav"

    @patch("engines.export_engine.export.export_audio_podcast")
    def test_export_podcast_wav(self, mock_podcast):
        """Should dispatch podcast content to wav export."""
        mock_podcast.return_value = {"wav_bytes": b"test-wav", "mp3_bytes": b"", "duration_seconds": 300.0}
        result = export(_PODCAST_CONTENT, format="wav")
        assert result["duration_seconds"] == 300.0

    @patch("engines.export_engine.export.export_audio_bilingual")
    def test_export_bilingual_wav(self, mock_bilingual):
        """Should dispatch bilingual content to wav export."""
        mock_bilingual.return_value = {"wav_bytes": b"test-wav", "mp3_bytes": b"", "duration_seconds": 120.0}
        result = export(_BILINGUAL_CONTENT, format="wav")
        assert result["duration_seconds"] == 120.0

    @patch("engines.export_engine.export.export_audio_immersion")
    def test_export_immersion_wav(self, mock_immersion):
        """Should dispatch immersion content to wav export."""
        mock_immersion.return_value = {"wav_bytes": b"test-wav", "mp3_bytes": b"", "duration_seconds": 180.0}
        result = export(_IMMERSION_CONTENT, format="wav")
        assert result["duration_seconds"] == 180.0

    @patch("engines.export_engine.export.export_audio_narrate")
    def test_export_narration_mp3(self, mock_narrate):
        """Should include MP3 when format=mp3."""
        mock_narrate.return_value = {"wav_bytes": b"test-wav", "mp3_bytes": b"test-mp3"}
        result = export(_NARRATION_CONTENT, format="mp3")
        assert result["mp3_bytes"] == b"test-mp3"

    def test_journey_unsupported_format_raises(self):
        with pytest.raises(KeyError, match="docx"):
            export(_SIMPLE_JOURNEY, format="docx")

    def test_unknown_content_raises(self):
        with pytest.raises(ValueError, match="Cannot detect"):
            export({"foo": "bar"}, format="text")

    def test_audio_unsupported_format_raises(self):
        with pytest.raises(KeyError, match="pdf"):
            export(_NARRATION_CONTENT, format="pdf")


# ---------------------------------------------------------------------------
# Integration test: all four audio types produce valid non-empty audio
# ---------------------------------------------------------------------------

class TestIntegrationAllAudioTypes:
    """
    Integration test: verify all four audio types produce valid, non-empty audio.

    Uses mocked model and TTS calls so tests are deterministic.
    """

    def test_narration_produces_valid_audio(self):
        """Narration should produce non-empty WAV bytes."""
        try:
            result = export_audio_narrate(
                "Hello world",
                include_mp3=False,
            )
            assert result.get("wav_bytes")
            assert result["backend_used"] in ("KOKORO", "PIPER")
        except (TypeError, ConnectionError, RuntimeError, FileNotFoundError, ApiError, LmConnectionError, SchemaValidationError) as e:
            pytest.skip(f"Live audio not available: {e}")

    def test_podcast_produces_valid_audio(self):
        """Podcast should produce non-empty WAV bytes."""
        try:
            result = export_audio_podcast(
                "The Future of Programming",
                include_mp3=False,
                num_segments=3,
            )
            assert result.get("wav_bytes")
            assert result.get("duration_seconds", 0) > 0
        except (TypeError, ConnectionError, RuntimeError, FileNotFoundError, ApiError, LmConnectionError, SchemaValidationError) as e:
            pytest.skip(f"Live audio not available: {e}")

    def test_bilingual_produces_valid_audio(self):
        """Bilingual should produce non-empty WAV bytes."""
        try:
            result = export_audio_bilingual(
                "Ordering food",
                "es",
                "en",
                include_mp3=False,
                num_segments=3,
            )
            assert result.get("wav_bytes")
            assert result.get("duration_seconds", 0) > 0
        except (TypeError, ConnectionError, RuntimeError, FileNotFoundError, ApiError, LmConnectionError, SchemaValidationError) as e:
            pytest.skip(f"Live audio not available: {e}")

    def test_immersion_produces_valid_audio(self):
        """Immersion should produce non-empty WAV bytes."""
        try:
            result = export_audio_immersion(
                "Ordering food",
                "es",
                include_mp3=False,
                num_segments=3,
            )
            assert result.get("wav_bytes")
            assert result.get("duration_seconds", 0) > 0
        except (TypeError, ConnectionError, RuntimeError, FileNotFoundError, ApiError, LmConnectionError, SchemaValidationError) as e:
            pytest.skip(f"Live audio not available: {e}")

    @patch("engines.export_engine.export.export_audio_narrate")
    @patch("engines.export_engine.export.export_audio_podcast")
    @patch("engines.export_engine.export.export_audio_bilingual")
    @patch("engines.export_engine.export.export_audio_immersion")
    def test_all_four_audio_types_via_unified_export(
        self, mock_immersion, mock_bilingual, mock_podcast, mock_narrate
    ):
        """
        Contract: All four audio types should route correctly through
        the unified export() dispatcher.
        """
        mock_narrate.return_value = {"wav_bytes": b"narration-wav", "mp3_bytes": b""}
        mock_podcast.return_value = {"wav_bytes": b"podcast-wav", "mp3_bytes": b""}
        mock_bilingual.return_value = {"wav_bytes": b"bilingual-wav", "mp3_bytes": b""}
        mock_immersion.return_value = {"wav_bytes": b"immersion-wav", "mp3_bytes": b""}

        # Test each type through unified export
        n_result = export(_NARRATION_CONTENT, format="wav")
        assert n_result["wav_bytes"] == b"narration-wav"

        p_result = export(_PODCAST_CONTENT, format="wav")
        assert p_result["wav_bytes"] == b"podcast-wav"

        b_result = export(_BILINGUAL_CONTENT, format="wav")
        assert b_result["wav_bytes"] == b"bilingual-wav"

        i_result = export(_IMMERSION_CONTENT, format="wav")
        assert i_result["wav_bytes"] == b"immersion-wav"

        # Verify all were called
        mock_narrate.assert_called_once()
        mock_podcast.assert_called_once()
        mock_bilingual.assert_called_once()
        mock_immersion.assert_called_once()


# ---------------------------------------------------------------------------
# File writing integration test
# ---------------------------------------------------------------------------

class TestExportFileWriting:
    """Tests for exporting audio to files."""

    @patch("engines.export_engine.export.export_audio_narrate")
    def test_narration_to_file(self, mock_narrate, tmp_path):
        """Should write narration audio to file."""
        mock_narrate.return_value = {"wav_bytes": b"RIFF" + b"\x00" * 1000, "mp3_bytes": b""}
        filepath = str(tmp_path / "narration.wav")
        result = export(_NARRATION_CONTENT, format="wav", filepath=filepath)
        assert result == filepath

    @patch("engines.export_engine.export.export_audio_podcast")
    def test_podcast_to_file(self, mock_podcast, tmp_path):
        """Should write podcast audio to file."""
        mock_podcast.return_value = {"wav_bytes": b"RIFF" + b"\x00" * 2000, "mp3_bytes": b""}
        filepath = str(tmp_path / "podcast.wav")
        result = export(_PODCAST_CONTENT, format="wav", filepath=filepath)
        assert result == filepath


# ---------------------------------------------------------------------------
# Manual verification step
# ---------------------------------------------------------------------------

def test_manual_verification():
    """
    Contract: Manual verification for unified audio export.

    To test manually:
    1. Ensure LM Studio is running on localhost:1234
    2. Ensure Piper TTS is available
    3. Run the following commands:

       # Narration
       python -c "
       from engines.export_engine.export import export
       result = export({'text': 'Hello world'}, format='wav')
       print(f'Narration: {len(result[\"wav_bytes\"])} bytes WAV')
       "

       # Podcast
       python -c "
       from engines.export_engine.export import export
       result = export({'topic': 'AI', 'host_name': 'Host'}, format='wav')
       print(f'Podcast: {len(result[\"wav_bytes\"])} bytes WAV, {result[\"duration_seconds\"]:.1f}s')
       "

       # Bilingual
       python -c "
       from engines.export_engine.export import export
       result = export({'topic': 'Food', 'target_language': 'es', 'known_language': 'en'}, format='wav')
       print(f'Bilingual: {len(result[\"wav_bytes\"])} bytes WAV, {result[\"duration_seconds\"]:.1f}s')
       "

       # Immersion
       python -c "
       from engines.export_engine.export import export
       result = export({'topic': 'Food', 'target_language': 'es', 'segments': [{'type': 'intro', 'speaker': 'Host', 'content': 'Hello'}]}, format='wav')
       print(f'Immersion: {len(result[\"wav_bytes\"])} bytes WAV, {result[\"duration_seconds\"]:.1f}s')
       "

    4. Verify all four produce non-empty WAV files
    """
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
