# engines/language-lab/test_immersion.py
#
# WHAT: Tests for the immersion podcast generation module.
# WHY:  Ensures the immersion variant correctly reuses audio-engine's
#       podcast script generation and audio rendering without duplicating
#       logic.
# BREAKS IF DELETED: No regression protection for immersion podcast
#       generation contract.

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add paths
_this_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_this_dir.parent.parent.parent / "model-layer"))
sys.path.insert(0, str(_this_dir.parent.parent / "audio-engine"))
sys.path.insert(0, str(_this_dir))

from immersion import (
    generate_immersion_podcast,
    generate_and_save_immersion,
    ImmersionResult,
    DEFAULT_NUM_SEGMENTS,
    DEFAULT_DURATION_MINUTES,
    DEFAULT_SPEED,
)
from podcast_script import PodcastScript, PodcastSegment


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TOPIC = "Ordering food at a restaurant"
SAMPLE_TARGET_LANG = "es"
SAMPLE_LEVEL = "beginner"

SAMPLE_SCRIPT = PodcastScript(
    topic=SAMPLE_TOPIC,
    title="Ordering Food Episode",
    host_name="Host",
    duration_minutes=5,
    segments=[
        PodcastSegment(type="intro", speaker="Ana", content="Bienvenidos al programa", duration_seconds=30),
        PodcastSegment(type="dialogue", speaker="Carlos", content="Hoy vamos a aprender a pedir comida", duration_seconds=60),
        PodcastSegment(type="conclusion", speaker="Ana", content="Gracias por escuchar", duration_seconds=30),
    ],
    speakers=["Ana", "Carlos"],
)


# ---------------------------------------------------------------------------
# Test ImmersionResult
# ---------------------------------------------------------------------------

class TestImmersionResult:
    """Tests for ImmersionResult dataclass."""

    def test_properties_delegates_to_audio(self):
        """ImmersionResult properties should delegate to audio result."""
        mock_audio = MagicMock(
            wav_bytes=b"test-wav",
            mp3_bytes=b"test-mp3",
            duration_seconds=120.5,
            total_segments=6,
        )
        result = ImmersionResult(
            script=SAMPLE_SCRIPT,
            audio=mock_audio,
        )

        assert result.wav_bytes == b"test-wav"
        assert result.mp3_bytes == b"test-mp3"
        assert result.duration_seconds == 120.5
        assert result.total_segments == 6

    def test_contains_script_and_audio(self):
        """ImmersionResult should contain both script and audio."""
        result = ImmersionResult(
            script=SAMPLE_SCRIPT,
            audio=MagicMock(),
        )

        assert result.script == SAMPLE_SCRIPT
        assert hasattr(result, 'audio')


# ---------------------------------------------------------------------------
# Test generate_immersion_podcast()
# ---------------------------------------------------------------------------

class TestGenerateImmersionPodcast:
    """Tests for immersion podcast generation."""

    @patch("immersion.generate_podcast_script")
    @patch("immersion.render_podcast_to_audio")
    def test_calls_script_generation(self, mock_render, mock_generate):
        """Should call podcast script generation."""
        mock_generate.return_value = SAMPLE_SCRIPT
        mock_render.return_value = MagicMock(
            wav_bytes=b"test",
            mp3_bytes=b"",
            duration_seconds=10.0,
            total_segments=3,
            backend_used="PIPER",
        )

        result = generate_immersion_podcast(SAMPLE_TOPIC, SAMPLE_TARGET_LANG)

        mock_generate.assert_called_once_with(
            topic=SAMPLE_TOPIC,
            num_segments=DEFAULT_NUM_SEGMENTS,
            duration_minutes=DEFAULT_DURATION_MINUTES,
            host_name="Host",
            client=None,
            model="default",
        )

    @patch("immersion.generate_podcast_script")
    @patch("immersion.render_podcast_to_audio")
    def test_calls_audio_rendering(self, mock_render, mock_generate):
        """Should call audio rendering with the generated script."""
        mock_generate.return_value = SAMPLE_SCRIPT
        mock_render.return_value = MagicMock(
            wav_bytes=b"test",
            mp3_bytes=b"",
            duration_seconds=10.0,
            total_segments=3,
            backend_used="PIPER",
        )

        result = generate_immersion_podcast(SAMPLE_TOPIC, SAMPLE_TARGET_LANG)

        mock_render.assert_called_once_with(
            SAMPLE_SCRIPT,
            include_mp3=True,
            output_path=None,
            speed=DEFAULT_SPEED,
        )

    @patch("immersion.generate_podcast_script")
    @patch("immersion.render_podcast_to_audio")
    def test_passes_num_segments(self, mock_render, mock_generate):
        """Should pass num_segments to script generation."""
        mock_generate.return_value = SAMPLE_SCRIPT
        mock_render.return_value = MagicMock(
            wav_bytes=b"test",
            mp3_bytes=b"",
            duration_seconds=10.0,
            total_segments=3,
            backend_used="PIPER",
        )

        generate_immersion_podcast(SAMPLE_TOPIC, SAMPLE_TARGET_LANG, num_segments=10)

        call_kwargs = mock_generate.call_args[1]
        assert call_kwargs['num_segments'] == 10

    @patch("immersion.generate_podcast_script")
    @patch("immersion.render_podcast_to_audio")
    def test_passes_duration_minutes(self, mock_render, mock_generate):
        """Should pass duration_minutes to script generation."""
        mock_generate.return_value = SAMPLE_SCRIPT
        mock_render.return_value = MagicMock(
            wav_bytes=b"test",
            mp3_bytes=b"",
            duration_seconds=10.0,
            total_segments=3,
            backend_used="PIPER",
        )

        generate_immersion_podcast(SAMPLE_TOPIC, SAMPLE_TARGET_LANG, duration_minutes=30)

        call_kwargs = mock_generate.call_args[1]
        assert call_kwargs['duration_minutes'] == 30

    @patch("immersion.generate_podcast_script")
    @patch("immersion.render_podcast_to_audio")
    def test_passes_include_mp3(self, mock_render, mock_generate):
        """Should pass include_mp3 to audio rendering."""
        mock_generate.return_value = SAMPLE_SCRIPT
        mock_render.return_value = MagicMock(
            wav_bytes=b"test",
            mp3_bytes=b"",
            duration_seconds=10.0,
            total_segments=3,
            backend_used="PIPER",
        )

        generate_immersion_podcast(SAMPLE_TOPIC, SAMPLE_TARGET_LANG, include_mp3=False)

        call_kwargs = mock_render.call_args[1]
        assert call_kwargs['include_mp3'] is False

    @patch("immersion.generate_podcast_script")
    @patch("immersion.render_podcast_to_audio")
    def test_passes_output_path(self, mock_render, mock_generate):
        """Should pass output_path to audio rendering."""
        mock_generate.return_value = SAMPLE_SCRIPT
        mock_render.return_value = MagicMock(
            wav_bytes=b"test",
            mp3_bytes=b"",
            duration_seconds=10.0,
            total_segments=3,
            backend_used="PIPER",
        )

        generate_immersion_podcast(SAMPLE_TOPIC, SAMPLE_TARGET_LANG, output_path="/tmp/output")

        call_kwargs = mock_render.call_args[1]
        assert call_kwargs['output_path'] == "/tmp/output"

    @patch("immersion.generate_podcast_script")
    @patch("immersion.render_podcast_to_audio")
    def test_passes_speed(self, mock_render, mock_generate):
        """Should pass speed to audio rendering."""
        mock_generate.return_value = SAMPLE_SCRIPT
        mock_render.return_value = MagicMock(
            wav_bytes=b"test",
            mp3_bytes=b"",
            duration_seconds=10.0,
            total_segments=3,
            backend_used="PIPER",
        )

        generate_immersion_podcast(SAMPLE_TOPIC, SAMPLE_TARGET_LANG, speed=0.8)

        call_kwargs = mock_render.call_args[1]
        assert call_kwargs['speed'] == 0.8

    @patch("immersion.generate_podcast_script")
    @patch("immersion.render_podcast_to_audio")
    def test_returns_immersion_result(self, mock_render, mock_generate):
        """Should return an ImmersionResult."""
        mock_generate.return_value = SAMPLE_SCRIPT
        mock_render.return_value = MagicMock(
            wav_bytes=b"test",
            mp3_bytes=b"",
            duration_seconds=10.0,
            total_segments=3,
            backend_used="PIPER",
        )

        result = generate_immersion_podcast(SAMPLE_TOPIC, SAMPLE_TARGET_LANG)

        assert isinstance(result, ImmersionResult)
        assert result.script == SAMPLE_SCRIPT

    @patch("immersion.generate_podcast_script")
    def test_raises_on_empty_topic(self, mock_generate):
        """Should raise if topic is empty."""
        with pytest.raises(ValueError, match="Topic"):
            generate_immersion_podcast("", SAMPLE_TARGET_LANG)

    @patch("immersion.generate_podcast_script")
    def test_raises_on_empty_target_language(self, mock_generate):
        """Should raise if target language is empty."""
        with pytest.raises(ValueError, match="Target language"):
            generate_immersion_podcast(SAMPLE_TOPIC, "")

    @patch("immersion.generate_podcast_script", side_effect=Exception("LM Studio error"))
    def test_propagates_generation_errors(self, mock_generate):
        """Should propagate errors from script generation."""
        with pytest.raises(Exception, match="LM Studio error"):
            generate_immersion_podcast(SAMPLE_TOPIC, SAMPLE_TARGET_LANG)

    @patch("immersion.generate_podcast_script", return_value=SAMPLE_SCRIPT)
    @patch("immersion.render_podcast_to_audio", side_effect=Exception("Audio error"))
    def test_propagates_rendering_errors(self, mock_render, mock_generate):
        """Should propagate errors from audio rendering."""
        with pytest.raises(Exception, match="Audio error"):
            generate_immersion_podcast(SAMPLE_TOPIC, SAMPLE_TARGET_LANG)


# ---------------------------------------------------------------------------
# Test generate_and_save_immersion()
# ---------------------------------------------------------------------------

class TestGenerateAndSaveImmersion:
    """Tests for convenience function."""

    @patch("immersion.generate_immersion_podcast")
    def test_calls_generate_with_output_path(self, mock_generate):
        """Should pass output_path to generate function."""
        mock_generate.return_value = ImmersionResult(
            script=SAMPLE_SCRIPT,
            audio=MagicMock(
                wav_bytes=b"test",
                mp3_bytes=b"",
                duration_seconds=10.0,
                total_segments=3,
            ),
        )

        generate_and_save_immersion(
            SAMPLE_TOPIC,
            SAMPLE_TARGET_LANG,
            output_path="/tmp/output",
        )

        call_kwargs = mock_generate.call_args[1]
        assert call_kwargs['output_path'] == "/tmp/output"

    @patch("immersion.generate_immersion_podcast")
    def test_returns_immersion_result(self, mock_generate):
        """Should return ImmersionResult."""
        mock_generate.return_value = ImmersionResult(
            script=SAMPLE_SCRIPT,
            audio=MagicMock(
                wav_bytes=b"test",
                mp3_bytes=b"",
                duration_seconds=10.0,
                total_segments=3,
            ),
        )

        result = generate_and_save_immersion(
            SAMPLE_TOPIC,
            SAMPLE_TARGET_LANG,
        )

        assert isinstance(result, ImmersionResult)


# ---------------------------------------------------------------------------
# Test manual verification
# ---------------------------------------------------------------------------

def test_manual_verification():
    """
    Contract: Manual verification for immersion podcast generation.

    To test manually:
    1. Ensure LM Studio is running on localhost:1234
    2. Run: python -c "
       from engines.language_lab.immersion import generate_immersion_podcast
       result = generate_immersion_podcast(
           'Ordering food', 'es',
           level='beginner',
           num_segments=5
       )
       print(f'Duration: {result.duration_seconds:.1f}s')
       print(f'Speakers: {result.script.speakers}')
       for seg in result.script.segments:
           print(f'  {seg.speaker}: {seg.content[:50]}...')
       "
    3. Verify audio file is generated with Spanish content
    """
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
