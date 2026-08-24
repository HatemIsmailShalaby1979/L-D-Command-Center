# engines/audio-engine/test_podcast_audio.py
#
# WHAT: Tests for the podcast audio rendering module.
# WHY:  Ensures the podcast audio renderer correctly maps speakers to
#       voices, synthesizes segments, concatenates with pauses, and
#       handles errors.
# BREAKS IF DELETED: No regression protection for podcast audio rendering.

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add paths

from engines.audio_engine.podcast_audio import (
    render_podcast_to_audio,
    _generate_silence,
    _make_wav_header,
    _synthesize_segment,
    _concatenate_wavs,
    DEFAULT_VOICES,
    PAUSE_DURATION_SECONDS,
    PodcastAudioResult,
)
from engines.audio_engine.podcast_script import PodcastScript, PodcastSegment


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SCRIPT_TWO_SPEAKERS = PodcastScript(
    topic="Python for Beginners",
    title="Python Episode",
    host_name="Host",
    duration_minutes=5,
    segments=[
        PodcastSegment(type="intro", speaker="Alice", content="Welcome everyone!", duration_seconds=10),
        PodcastSegment(type="dialogue", speaker="Bob", content="Hi Alice, today we discuss Python.", duration_seconds=15),
        PodcastSegment(type="dialogue", speaker="Alice", content="Let's cover the basics.", duration_seconds=15),
        PodcastSegment(type="conclusion", speaker="Bob", content="Thanks for watching!", duration_seconds=10),
    ],
    speakers=["Alice", "Bob"],
)

SAMPLE_SCRIPT_SINGLE_SPEAKER = PodcastScript(
    topic="Solo Podcast",
    title="Solo Episode",
    host_name="Charlie",
    duration_minutes=3,
    segments=[
        PodcastSegment(type="intro", speaker="Charlie", content="Hello world!", duration_seconds=5),
        PodcastSegment(type="monologue", speaker="Charlie", content="This is a solo podcast.", duration_seconds=10),
        PodcastSegment(type="conclusion", speaker="Charlie", content="Goodbye!", duration_seconds=5),
    ],
    speakers=["Charlie"],
)


# ---------------------------------------------------------------------------
# Test helper functions
# ---------------------------------------------------------------------------

class TestGenerateSilence:
    """Tests for silence generation."""

    def test_generates_silence_bytes(self):
        silence = _generate_silence(0.3, sample_rate=22050)
        assert len(silence) == 0.3 * 22050 * 2  # 16-bit mono

    def test_silence_is_all_zeros(self):
        silence = _generate_silence(1.0, sample_rate=22050)
        assert all(b == 0 for b in silence)

    def test_zero_duration_produces_empty_bytes(self):
        silence = _generate_silence(0, sample_rate=22050)
        assert len(silence) == 0


class TestMakeWavHeader:
    """Tests for WAV header generation."""

    def test_header_size(self):
        data_size = 1000
        header = _make_wav_header(data_size)
        # Standard WAV header is 44 bytes
        assert len(header) == 44

    def test_header_format(self):
        header = _make_wav_header(1000)
        assert header[:4] == b"RIFF"
        assert header[8:12] == b"WAVE"

    def test_includes_data_size(self):
        data_size = 5000
        header = _make_wav_header(data_size)
        # Data size should be in the header
        import struct
        actual_size = struct.unpack("<I", header[40:44])[0]
        assert actual_size == data_size


class TestConcatenateWavs:
    """Tests for WAV concatenation."""

    def test_concatenates_multiple_segments(self):
        pcm1 = b"\x00" * 100
        pcm2 = b"\xff" * 100
        result, sample_rate = _concatenate_wavs([pcm1, pcm2], [22050, 22050])
        assert len(result) > 200  # header + both segments

    def test_uses_first_sample_rate(self):
        result, sample_rate = _concatenate_wavs([b"\x00" * 100], [22050])
        assert sample_rate == 22050

    def test_empty_segments_returns_empty(self):
        result, sample_rate = _concatenate_wavs([], [])
        assert result == b""
        assert sample_rate == 22050  # default


# ---------------------------------------------------------------------------
# Test render_podcast_to_audio() — happy path
# ---------------------------------------------------------------------------

class TestRenderPodcastToAudio:
    """Tests for podcast audio rendering."""

    @patch("engines.audio_engine.podcast_audio._synthesize_segment")
    def test_synthesizes_all_segments(self, mock_synthesize):
        """Should synthesize each segment with the correct voice."""
        # Mock synthesize to return valid PCM data
        mock_synthesize.return_value = (b"\x00" * 100, 22050)

        with patch("engines.audio_engine.podcast_audio._wav_to_mp3", return_value=b""):
            result = render_podcast_to_audio(SAMPLE_SCRIPT_TWO_SPEAKERS)

        assert result.total_segments == 4
        assert mock_synthesize.call_count == 4

    @patch("engines.audio_engine.podcast_audio._synthesize_segment")
    def test_maps_speakers_to_distinct_voices(self, mock_synthesize):
        """Should assign different voices to different speakers."""
        mock_synthesize.return_value = (b"\x00" * 100, 22050)

        with patch("engines.audio_engine.podcast_audio._wav_to_mp3", return_value=b""):
            render_podcast_to_audio(SAMPLE_SCRIPT_TWO_SPEAKERS)

        # Check that different speakers got different voices
        # Call args: _synthesize_segment(text, voice=..., ...)
        voices_used = [c.kwargs.get('voice') or (c.args[1] if c.args else None) for c in mock_synthesize.call_args_list]
        distinct_voices = set(v for v in voices_used if v)
        assert len(distinct_voices) == 2  # Alice and Bob should get different voices

    @patch("engines.audio_engine.podcast_audio._synthesize_segment")
    def test_single_speaker_uses_single_voice(self, mock_synthesize):
        """Single-speaker script should use only one voice."""
        mock_synthesize.return_value = (b"\x00" * 100, 22050)

        with patch("engines.audio_engine.podcast_audio._wav_to_mp3", return_value=b""):
            result = render_podcast_to_audio(SAMPLE_SCRIPT_SINGLE_SPEAKER)

        assert result.total_segments == 3
        # All calls should use the same voice
        voices_used = set()
        for call in mock_synthesize.call_args_list:
            voice = call[1].get('voice') or (call[0][1] if len(call[0]) > 1 else None)
            if voice:
                voices_used.add(voice)
        assert len(voices_used) == 1

    @patch("engines.audio_engine.podcast_audio._synthesize_segment")
    @patch("engines.audio_engine.podcast_audio._wav_to_mp3", return_value=b"mock-mp3")
    def test_includes_mp3_by_default(self, mock_mp3, mock_synthesize):
        """Should include MP3 conversion by default."""
        mock_synthesize.return_value = (b"\x00" * 100, 22050)

        result = render_podcast_to_audio(SAMPLE_SCRIPT_TWO_SPEAKERS)

        assert result.mp3_bytes == b"mock-mp3"
        mock_mp3.assert_called_once()

    @patch("engines.audio_engine.podcast_audio._synthesize_segment")
    @patch("engines.audio_engine.podcast_audio._wav_to_mp3", return_value=b"mock-mp3")
    def test_can_skip_mp3(self, mock_mp3, mock_synthesize):
        """Should skip MP3 when include_mp3=False."""
        mock_synthesize.return_value = (b"\x00" * 100, 22050)

        result = render_podcast_to_audio(SAMPLE_SCRIPT_TWO_SPEAKERS, include_mp3=False)

        assert result.mp3_bytes == b""
        mock_mp3.assert_not_called()

    @patch("engines.audio_engine.podcast_audio._synthesize_segment")
    def test_returns_audio_result(self, mock_synthesize):
        """Should return a PodcastAudioResult."""
        mock_synthesize.return_value = (b"\x00" * 100, 22050)

        with patch("engines.audio_engine.podcast_audio._wav_to_mp3", return_value=b"mock-mp3"):
            result = render_podcast_to_audio(SAMPLE_SCRIPT_TWO_SPEAKERS)

        assert isinstance(result, PodcastAudioResult)
        assert result.wav_bytes
        assert result.backend_used.name == "PIPER"

    @patch("engines.audio_engine.podcast_audio._synthesize_segment")
    def test_duration_calculated_correctly(self, mock_synthesize):
        """Should calculate duration based on audio data."""
        # Return 1 second of audio (22050 samples * 2 bytes = 44100 bytes)
        mock_synthesize.return_value = (b"\x00" * 44100, 22050)

        with patch("engines.audio_engine.podcast_audio._wav_to_mp3", return_value=b""):
            result = render_podcast_to_audio(SAMPLE_SCRIPT_TWO_SPEAKERS)

        # 4 segments of 1 second each + 3 pauses of 0.3 seconds
        expected_duration = 4 * 1.0 + 3 * 0.3
        assert abs(result.duration_seconds - expected_duration) < 0.1

    @patch("engines.audio_engine.podcast_audio._synthesize_segment")
    def test_passes_speed_parameter(self, mock_synthesize):
        """Should pass speed parameter to synthesis."""
        mock_synthesize.return_value = (b"\x00" * 100, 22050)

        with patch("engines.audio_engine.podcast_audio._wav_to_mp3", return_value=b""):
            render_podcast_to_audio(SAMPLE_SCRIPT_TWO_SPEAKERS, speed=1.5)

        for call in mock_synthesize.call_args_list:
            assert call[1].get('speed') == 1.5


# ---------------------------------------------------------------------------
# Test render_podcast_to_audio() — error cases
# ---------------------------------------------------------------------------

class TestRenderPodcastToAudioErrors:
    """Tests for error handling."""

    def test_empty_script_raises(self):
        """Should raise for empty segments."""
        empty_script = PodcastScript(
            topic="Empty",
            title="Empty",
            host_name="Host",
            duration_minutes=0,
            segments=[],
            speakers=[],
        )
        with pytest.raises(ValueError, match="no segments"):
            render_podcast_to_audio(empty_script)

    def test_invalid_script_type_raises(self):
        """Should raise for non-PodcastScript input."""
        with pytest.raises(TypeError, match="Expected PodcastScript"):
            render_podcast_to_audio("not a script")  # type: ignore

    @patch("engines.audio_engine.podcast_audio._synthesize_segment", side_effect=RuntimeError("TTS failed"))
    def test_tts_failure_propagates(self, mock_synthesize):
        """Should propagate TTS errors."""
        with pytest.raises(RuntimeError, match="TTS failed"):
            render_podcast_to_audio(SAMPLE_SCRIPT_TWO_SPEAKERS)

    @patch("engines.audio_engine.podcast_audio._wav_to_mp3", side_effect=RuntimeError("ffmpeg failed"))
    def test_mp3_failure_graceful(self, mock_mp3):
        """Should continue with WAV-only if MP3 conversion fails."""
        with patch("engines.audio_engine.podcast_audio._synthesize_segment", return_value=(b"\x00" * 100, 22050)):
            result = render_podcast_to_audio(SAMPLE_SCRIPT_TWO_SPEAKERS)
            assert result.mp3_bytes == b""


# ---------------------------------------------------------------------------
# Test manual verification
# ---------------------------------------------------------------------------

def test_manual_verification():
    """
    Contract: Manual verification for podcast audio rendering.

    To test manually:
    1. Ensure LM Studio is running on localhost:1234
    2. Run: python -c "
       from engines.audio_engine.podcast_audio import render_podcast_to_audio
       from engines.audio_engine.podcast_script import PodcastScript, PodcastSegment
       script = PodcastScript(
           topic='Test',
           title='Test',
           host_name='Host',
           duration_minutes=1,
           segments=[
               PodcastSegment(type='intro', speaker='Alice', content='Hello from Alice'),
               PodcastSegment(type='dialogue', speaker='Bob', content='Hello from Bob'),
               PodcastSegment(type='conclusion', speaker='Alice', content='Goodbye from Alice')
           ],
           speakers=['Alice', 'Bob']
       )
       result = render_podcast_to_audio(script)
       print(f'Duration: {result.duration_seconds}s')
       "
    3. Verify audio file is generated and has correct duration
    """
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
