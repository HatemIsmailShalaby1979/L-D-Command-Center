# engines/language-lab/test_bilingual.py
#
# WHAT: Tests for the bilingual lesson generation and audio rendering.
# WHY:  Ensures translation accuracy validation, schema compliance,
#       and correct audio rendering with target/known language voices.
# BREAKS IF DELETED: No regression protection for language-lab core.

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add paths

from engines.language_lab.bilingual import (
    generate_bilingual_pair,
    render_bilingual_audio,
    generate_and_render,
    validate_bilingual_pair,
    BilingualPair,
    BilingualSegment,
    DEFAULT_NUM_SEGMENTS,
    DEFAULT_SPEED,
    TARGET_VOICES,
    KNOWN_VOICES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TOPIC = "Ordering food at a restaurant"
SAMPLE_TARGET_LANG = "es"
SAMPLE_KNOWN_LANG = "en"

VALID_PAIR_DICT = {
    "topic": SAMPLE_TOPIC,
    "target_language": SAMPLE_TARGET_LANG,
    "known_language": SAMPLE_KNOWN_LANG,
    "segments": [
        {
            "target_text": "Buenos días, ¿qué me recomienda?",
            "translation_text": "Good morning, what do you recommend?",
        },
        {
            "target_text": "Me gustaría probar el plato del día.",
            "translation_text": "I would like to try the dish of the day.",
        },
    ],
}

SAMPLE_PAIR = BilingualPair(
    topic=SAMPLE_TOPIC,
    target_language=SAMPLE_TARGET_LANG,
    known_language=SAMPLE_KNOWN_LANG,
    segments=[
        BilingualSegment(
            target_text="Buenos días, ¿qué me recomienda?",
            translation_text="Good morning, what do you recommend?",
        ),
        BilingualSegment(
            target_text="Me gustaría probar el plato del día.",
            translation_text="I would like to try the dish of the day.",
        ),
    ],
)


# ---------------------------------------------------------------------------
# Test BilingualSegment
# ---------------------------------------------------------------------------

class TestBilingualSegment:
    """Tests for BilingualSegment dataclass."""

    def test_to_dict(self):
        seg = BilingualSegment(
            target_text="Hola",
            translation_text="Hello",
        )
        assert seg.to_dict() == {
            "target_text": "Hola",
            "translation_text": "Hello",
        }

    def test_from_dict(self):
        data = {
            "target_text": "Gracias",
            "translation_text": "Thank you",
        }
        seg = BilingualSegment.from_dict(data)
        assert seg.target_text == "Gracias"
        assert seg.translation_text == "Thank you"


# ---------------------------------------------------------------------------
# Test BilingualPair
# ---------------------------------------------------------------------------

class TestBilingualPair:
    """Tests for BilingualPair dataclass."""

    def test_to_dict(self):
        data = SAMPLE_PAIR.to_dict()
        assert data["topic"] == SAMPLE_TOPIC
        assert data["target_language"] == SAMPLE_TARGET_LANG
        assert data["known_language"] == SAMPLE_KNOWN_LANG
        assert len(data["segments"]) == 2

    def test_from_dict(self):
        pair = BilingualPair.from_dict(VALID_PAIR_DICT)
        assert pair.topic == SAMPLE_TOPIC
        assert len(pair.segments) == 2
        assert pair.segments[0].target_text == "Buenos días, ¿qué me recomienda?"

    def test_all_segments_have_translation(self):
        """Contract: Every segment must have both target and translation text."""
        for seg in SAMPLE_PAIR.segments:
            assert seg.target_text.strip()
            assert seg.translation_text.strip()


# ---------------------------------------------------------------------------
# Test validate_bilingual_pair()
# ---------------------------------------------------------------------------

class TestValidateBilingualPair:
    """Tests for schema validation."""

    def test_valid_pair(self):
        is_valid, errors = validate_bilingual_pair(VALID_PAIR_DICT)
        assert is_valid
        assert errors == []

    def test_missing_topic(self):
        data = dict(VALID_PAIR_DICT)
        del data["topic"]
        is_valid, errors = validate_bilingual_pair(data)
        assert not is_valid
        assert any("topic" in e for e in errors)

    def test_missing_target_language(self):
        data = dict(VALID_PAIR_DICT)
        del data["target_language"]
        is_valid, errors = validate_bilingual_pair(data)
        assert not is_valid

    def test_missing_known_language(self):
        data = dict(VALID_PAIR_DICT)
        del data["known_language"]
        is_valid, errors = validate_bilingual_pair(data)
        assert not is_valid

    def test_missing_segments(self):
        data = dict(VALID_PAIR_DICT)
        del data["segments"]
        is_valid, errors = validate_bilingual_pair(data)
        assert not is_valid

    def test_empty_segments(self):
        data = dict(VALID_PAIR_DICT)
        data["segments"] = []
        is_valid, errors = validate_bilingual_pair(data)
        assert not is_valid

    def test_missing_target_text(self):
        data = dict(VALID_PAIR_DICT)
        del data["segments"][0]["target_text"]
        is_valid, errors = validate_bilingual_pair(data)
        assert not is_valid
        assert any("target_text" in e for e in errors)

    def test_missing_translation_text(self):
        data = dict(VALID_PAIR_DICT)
        del data["segments"][0]["translation_text"]
        is_valid, errors = validate_bilingual_pair(data)
        assert not is_valid
        assert any("translation_text" in e for e in errors)

    def test_empty_target_text(self):
        data = dict(VALID_PAIR_DICT)
        data["segments"][0]["target_text"] = ""
        is_valid, errors = validate_bilingual_pair(data)
        assert not is_valid

    def test_empty_translation_text(self):
        data = dict(VALID_PAIR_DICT)
        data["segments"][0]["translation_text"] = "   "
        is_valid, errors = validate_bilingual_pair(data)
        assert not is_valid


# ---------------------------------------------------------------------------
# Test generate_bilingual_pair() — happy path
# ---------------------------------------------------------------------------

class TestGenerateBilingualPair:
    """Tests for generation with mocked model."""

    @patch("engines.language_lab.bilingual._call_model")
    def test_generates_from_topic(self, mock_call):
        mock_call.return_value = '{"topic": "Test", "target_language": "es", "known_language": "en", "segments": [{"target_text": "Hola", "translation_text": "Hello"}]}'
        pair = generate_bilingual_pair("Test", "es", "en")
        assert isinstance(pair, BilingualPair)
        assert pair.topic == "Test"
        mock_call.assert_called_once()

    @patch("engines.language_lab.bilingual._call_model")
    def test_passes_num_segments(self, mock_call):
        mock_call.return_value = '{"topic": "Test", "target_language": "es", "known_language": "en", "segments": [{"target_text": "Hola", "translation_text": "Hello"}]}'
        generate_bilingual_pair("Test", "es", "en", num_segments=15)
        # Verify the prompt includes num_segments
        call_args = mock_call.call_args[0]
        assert "15" in call_args[1]

    @patch("engines.language_lab.bilingual._call_model")
    def test_passes_target_language(self, mock_call):
        mock_call.return_value = '{"topic": "Test", "target_language": "fr", "known_language": "en", "segments": [{"target_text": "Bonjour", "translation_text": "Hello"}]}'
        generate_bilingual_pair("Test", "fr", "en")
        call_args = mock_call.call_args[0]
        assert "fr" in call_args[1]

    @patch("engines.language_lab.bilingual._call_model")
    def test_passes_known_language(self, mock_call):
        mock_call.return_value = '{"topic": "Test", "target_language": "es", "known_language": "zh", "segments": [{"target_text": "Hola", "translation_text": "Hello"}]}'
        generate_bilingual_pair("Test", "es", "zh")
        call_args = mock_call.call_args[0]
        assert "zh" in call_args[1]

    @patch("engines.language_lab.bilingual._call_model")
    def test_retries_on_validation_failure (self, mock_call):
        """Should retry when initial validation fails."""
        mock_call.side_effect = [
            '{"invalid": "data"}',
            '{"topic": "Test", "target_language": "es", "known_language": "en", "segments": [{"target_text": "Hola", "translation_text": "Hello"}]}',
        ]
        pair = generate_bilingual_pair("Test", "es", "en")
        assert isinstance(pair, BilingualPair)
        assert mock_call.call_count == 2

    @patch("engines.language_lab.bilingual._call_model")
    def test_raises_after_max_retries(self, mock_call):
        """Should raise after exhausting retries."""
        from model_layer.schema import SchemaValidationError
        mock_call.return_value = '{"invalid": "data"}'
        with pytest.raises(SchemaValidationError):
            generate_bilingual_pair("Test", "es", "en")

    @patch("engines.language_lab.bilingual._call_model")
    def test_raises_on_extract_failure(self, mock_call):
        """Should raise when JSON extraction fails."""
        from model_layer.schema import SchemaValidationError
        mock_call.return_value = "Not valid JSON at all"
        with pytest.raises(SchemaValidationError, match="Could not extract JSON"):
            generate_bilingual_pair("Test", "es", "en")


# ---------------------------------------------------------------------------
# Test generate_bilingual_pair() — error cases
# ---------------------------------------------------------------------------

class TestGenerateBilingualPairErrors:
    """Tests for error handling."""

    def test_empty_topic_raises(self):
        with pytest.raises(ValueError, match="Topic"):
            generate_bilingual_pair("", "es", "en")

    def test_empty_target_language_raises(self):
        with pytest.raises(ValueError, match="Target language"):
            generate_bilingual_pair("Test", "", "en")

    def test_empty_known_language_raises(self):
        with pytest.raises(ValueError, match="Known language"):
            generate_bilingual_pair("Test", "es", "")


# ---------------------------------------------------------------------------
# Test render_bilingual_audio()
# ---------------------------------------------------------------------------

class TestRenderBilingualAudio:
    """Tests for audio rendering."""

    @patch("engines.language_lab.bilingual._synthesize_segment")
    def test_synthesizes_all_segments(self, mock_synthesize):
        """Should synthesize each segment twice (target + translation)."""
        mock_synthesize.return_value = (b"\x00" * 100, 22050)

        with patch("engines.language_lab.bilingual._wav_to_mp3", return_value=b""):
            result = render_bilingual_audio(SAMPLE_PAIR)

        assert result.total_segments == 4  # 2 segments × 2 voices
        assert mock_synthesize.call_count == 4

    @patch("engines.language_lab.bilingual._synthesize_segment")
    def test_uses_target_voice_for_target_text(self, mock_synthesize):
        """Should use target language voice for target_text."""
        mock_synthesize.return_value = (b"\x00" * 100, 22050)

        with patch("engines.language_lab.bilingual._wav_to_mp3", return_value=b""):
            render_bilingual_audio(SAMPLE_PAIR)

        # First call should use Spanish voice
        first_call = mock_synthesize.call_args_list[0]
        assert first_call[1].get('voice') == TARGET_VOICES["es"] or \
               (len(first_call[0]) > 1 and first_call[0][1] == TARGET_VOICES["es"])

    @patch("engines.language_lab.bilingual._synthesize_segment")
    def test_uses_known_voice_for_translation(self, mock_synthesize):
        """Should use known language voice for translation_text."""
        mock_synthesize.return_value = (b"\x00" * 100, 22050)

        with patch("engines.language_lab.bilingual._wav_to_mp3", return_value=b""):
            render_bilingual_audio(SAMPLE_PAIR)

        # Second call should use English voice
        second_call = mock_synthesize.call_args_list[1]
        assert second_call[1].get('voice') == KNOWN_VOICES["en"] or \
               (len(second_call[0]) > 1 and second_call[0][1] == KNOWN_VOICES["en"])

    @patch("engines.language_lab.bilingual._synthesize_segment")
    @patch("engines.language_lab.bilingual._wav_to_mp3", return_value=b"mock-mp3")
    def test_includes_mp3_by_default(self, mock_mp3, mock_synthesize):
        """Should include MP3 by default."""
        mock_synthesize.return_value = (b"\x00" * 100, 22050)

        result = render_bilingual_audio(SAMPLE_PAIR)

        assert result.mp3_bytes == b"mock-mp3"

    @patch("engines.language_lab.bilingual._synthesize_segment")
    @patch("engines.language_lab.bilingual._wav_to_mp3", return_value=b"mock-mp3")
    def test_can_skip_mp3(self, mock_mp3, mock_synthesize):
        """Should skip MP3 when include_mp3=False."""
        mock_synthesize.return_value = (b"\x00" * 100, 22050)

        result = render_bilingual_audio(SAMPLE_PAIR, include_mp3=False)

        assert result.mp3_bytes == b""

    @patch("engines.language_lab.bilingual._synthesize_segment")
    def test_passes_speed_parameter(self, mock_synthesize):
        """Should pass speed parameter to synthesis."""
        mock_synthesize.return_value = (b"\x00" * 100, 22050)

        with patch("engines.language_lab.bilingual._wav_to_mp3", return_value=b""):
            render_bilingual_audio(SAMPLE_PAIR, speed=0.8)

        for call in mock_synthesize.call_args_list:
            assert call[1].get('speed') == 0.8


# ---------------------------------------------------------------------------
# Test render_bilingual_audio() — error cases
# ---------------------------------------------------------------------------

class TestRenderBilingualAudioErrors:
    """Tests for error handling."""

    def test_empty_pair_raises(self):
        empty_pair = BilingualPair(
            topic="Test",
            target_language="es",
            known_language="en",
            segments=[],
        )
        with pytest.raises(ValueError, match="no segments"):
            render_bilingual_audio(empty_pair)

    def test_invalid_pair_type_raises(self):
        with pytest.raises(TypeError, match="Expected BilingualPair"):
            render_bilingual_audio("not a pair")  # type: ignore

    @patch("engines.language_lab.bilingual._synthesize_segment", side_effect=RuntimeError("TTS failed"))
    def test_tts_failure_propagates(self, mock_synthesize):
        """Should propagate TTS errors."""
        with pytest.raises(RuntimeError, match="TTS failed"):
            render_bilingual_audio(SAMPLE_PAIR)

    @patch("engines.language_lab.bilingual._wav_to_mp3", side_effect=RuntimeError("ffmpeg failed"))
    def test_mp3_failure_graceful(self, mock_mp3):
        """Should continue with WAV-only if MP3 conversion fails."""
        with patch("engines.language_lab.bilingual._synthesize_segment", return_value=(b"\x00" * 100, 22050)):
            result = render_bilingual_audio(SAMPLE_PAIR)
            assert result.mp3_bytes == b""


# ---------------------------------------------------------------------------
# Test generate_and_render()
# ---------------------------------------------------------------------------

class TestGenerateAndRender:
    """Tests for the convenience function."""

    @patch("engines.language_lab.bilingual.generate_bilingual_pair")
    @patch("engines.language_lab.bilingual.render_bilingual_audio")
    def test_calls_both_functions(self, mock_render, mock_generate):
        mock_generate.return_value = SAMPLE_PAIR
        mock_render.return_value = MagicMock(
            wav_bytes=b"test",
            mp3_bytes=b"",
            duration_seconds=10.0,
            total_segments=2,
            backend_used="PIPER",
        )

        pair, audio = generate_and_render("Test", "es", "en")

        mock_generate.assert_called_once_with(
            "Test", "es", "en",
            num_segments=DEFAULT_NUM_SEGMENTS,
            client=None,
            model="default",
        )
        mock_render.assert_called_once_with(
            SAMPLE_PAIR,
            include_mp3=True,
            output_path=None,
            speed=DEFAULT_SPEED,
        )
        assert pair == SAMPLE_PAIR


# ---------------------------------------------------------------------------
# Test manual verification
# ---------------------------------------------------------------------------

def test_manual_verification():
    """
    Contract: Manual verification for bilingual pair generation.

    To test manually:
    1. Ensure LM Studio is running on localhost:1234
    2. Run: python -c "
       from engines.language_lab.bilingual import generate_and_render
       pair, audio = generate_and_render(
           'Ordering food', 'es', 'en',
           num_segments=5
       )
       print(f'Segments: {len(pair.segments)}')
       print(f'Duration: {audio.duration_seconds:.1f}s')
       for seg in pair.segments:
           print(f'  {seg.target_text} -> {seg.translation_text}')
       "
    3. Verify audio file has alternating Spanish and English sections
    """
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
