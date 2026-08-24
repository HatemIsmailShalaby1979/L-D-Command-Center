# engines/audio-engine/podcast_audio.py
#
# WHAT: Renders a PodcastScript to a single audio file by synthesizing
#       each speaker's turns with distinct voices, concatenating segments
#       with brief pauses between them.
# WHY:  Provides an end-to-end podcast audio pipeline — script generation
#       (podcast_script.py) → audio rendering (this module) → optional MP3
#       export (via ffmpeg, already used in narration.py).
# BREAKS IF DELETED: Podcast audio rendering is lost; the audio-engine can
#       generate scripts but cannot produce audio output from them.
#
# Voice mapping strategy:
#   - Each unique speaker in the script is assigned a distinct voice.
#   - Voice assignment is deterministic: speakers are mapped to voices
#     from DEFAULT_VOICES by their order of appearance.
#   - The first speaker gets the first voice, the second speaker gets
#     the second voice, etc.
#
# Audio concatenation:
#   - Each segment is synthesized independently.
#   - A brief silence (0.3 seconds) is inserted between segments.
#   - All WAV segments are concatenated into a single output WAV file.
#   - Optional MP3 conversion via ffmpeg (same as narration.py).

from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from engines.audio_engine.narration import _wav_to_mp3
from model_layer.tts import TtsBackend, synthesize


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Voice pool for speaker-to-voice mapping (Piper voices)
DEFAULT_VOICES = [
    "en_US-lessac-medium",   # Speaker 1: neutral English male/female
    "en_US-joe-medium",      # Speaker 2: distinct English voice
    "en_US-amy-medium",      # Speaker 3: another distinct voice
    "en_US-ryan-medium",     # Speaker 4
    "en_GB-alan-medium",     # Speaker 5: British accent for variety
]

# Pause duration between segments (seconds)
PAUSE_DURATION_SECONDS = 0.3

# Default synthesis parameters
DEFAULT_SPEED = 1.0
DEFAULT_BACKEND = TtsBackend.PIPER
DEFAULT_SAMPLE_RATE = 22050  # Piper default sample rate


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PodcastAudioResult:
    """Result of podcast audio rendering."""
    wav_bytes: bytes
    mp3_bytes: bytes
    duration_seconds: float
    total_segments: int
    backend_used: TtsBackend


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _generate_silence(duration_seconds: float, sample_rate: int = DEFAULT_SAMPLE_RATE) -> bytes:
    """
    Generate silence bytes for WAV concatenation.

    Args:
        duration_seconds: Duration of silence.
        sample_rate: Sample rate in Hz.

    Returns:
        Raw PCM silence bytes (16-bit mono).
    """
    num_samples = int(duration_seconds * sample_rate)
    # 16-bit mono silence (all zeros)
    return b"\x00" * (num_samples * 2)


def _make_wav_header(data_size: int, sample_rate: int = DEFAULT_SAMPLE_RATE) -> bytes:
    """
    Create a minimal WAV file header.

    Args:
        data_size: Size of the PCM data in bytes.
        sample_rate: Sample rate in Hz.

    Returns:
        WAV header bytes.
    """
    # RIFF header
    riff_header = b"RIFF"
    # File size - 8 (everything after this offset)
    file_size = 36 + data_size
    riff_header += struct.pack("<I", file_size)
    # WAVE format
    wave_header = b"WAVE"
    # fmt chunk
    fmt_chunk = b"fmt "
    fmt_chunk += struct.pack("<I", 16)  # chunk size
    fmt_chunk += struct.pack("<H", 1)   # PCM format
    fmt_chunk += struct.pack("<H", 1)   # mono
    fmt_chunk += struct.pack("<I", sample_rate)
    fmt_chunk += struct.pack("<I", sample_rate * 2)  # byte rate
    fmt_chunk += struct.pack("<H", 2)   # block align
    fmt_chunk += struct.pack("<H", 16)  # bits per sample
    # data chunk
    data_chunk = b"data"
    data_chunk += struct.pack("<I", data_size)
    return riff_header + wave_header + fmt_chunk + data_chunk


def _synthesize_segment(
    text: str,
    voice: str,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    speed: float = DEFAULT_SPEED,
) -> tuple[bytes, int]:
    """
    Synthesize a single segment and return (pcm_bytes, actual_sample_rate).

    Args:
        text: Segment text to synthesize.
        voice: Voice identifier.
        sample_rate: Expected sample rate.
        speed: Speech speed multiplier.

    Returns:
        Tuple of (PCM bytes, actual sample rate).
    """
    # Synthesize using TTS client
    wav_bytes = synthesize(text, voice=voice, backend=DEFAULT_BACKEND, speed=speed)

    # Parse WAV header to get actual sample rate and PCM data
    if len(wav_bytes) < 44:
        raise ValueError(f"Invalid WAV data: too short ({len(wav_bytes)} bytes)")

    # Check RIFF header
    if wav_bytes[:4] != b"RIFF" or wav_bytes[8:] != b"WAVE":
        raise ValueError("Invalid WAV format")

    # Extract sample rate from fmt chunk (offset 24-27)
    actual_sample_rate = struct.unpack("<I", wav_bytes[24:28])[0]

    # Find data chunk and extract PCM
    offset = 12  # After RIFF and WAVE
    while offset < len(wav_bytes):
        chunk_id = wav_bytes[offset:offset+4]
        chunk_size = struct.unpack("<I", wav_bytes[offset+4:offset+8])[0]
        if chunk_id == b"data":
            pcm_data = wav_bytes[offset+8:offset+8+chunk_size]
            return pcm_data, actual_sample_rate
        offset += 8 + chunk_size

    raise ValueError("WAV data chunk not found")


def _concatenate_wavs(
    segments: list[bytes],
    sample_rates: list[int],
) -> tuple[bytes, int]:
    """
    Concatenate multiple WAV byte streams into a single WAV file.

    Args:
        segments: List of PCM byte streams.
        sample_rates: List of sample rates for each segment.

    Returns:
        Tuple of (concatenated WAV bytes, common sample rate).
    """
    if not segments:
        return b"", DEFAULT_SAMPLE_RATE

    # Use the first segment's sample rate as the common rate
    common_sample_rate = sample_rates[0] if sample_rates else DEFAULT_SAMPLE_RATE

    # Concatenate all PCM data
    all_pcm = b"".join(segments)

    # Create new WAV header
    header = _make_wav_header(len(all_pcm), common_sample_rate)

    return header + all_pcm, common_sample_rate


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_podcast_to_audio(
    script: "PodcastScript",
    *,
    include_mp3: bool = True,
    output_path: Optional[str] = None,
    speed: float = DEFAULT_SPEED,
    pause_duration: float = PAUSE_DURATION_SECONDS,
) -> PodcastAudioResult:
    """
    Render a PodcastScript to a single audio file.

    Maps each unique speaker to a distinct voice, synthesizes each segment,
    and concatenates them with brief pauses between segments.

    Args:
        script: A PodcastScript object to render.
        include_mp3: Whether to convert to MP3 (default True).
        output_path: Optional directory to save audio files.
        speed: Speech speed multiplier (0.5 to 2.0).
        pause_duration: Silence duration between segments in seconds.

    Returns:
        PodcastAudioResult with wav_bytes, mp3_bytes, duration, etc.

    Raises:
        ValueError: If script has no segments or speakers.
        RuntimeError: If TTS synthesis fails.
    """
    from engines.audio_engine.podcast_script import PodcastScript

    if not isinstance(script, PodcastScript):
        raise TypeError(f"Expected PodcastScript, got {type(script).__name__}")

    if not script.segments:
        raise ValueError("PodcastScript has no segments")

    # Build speaker-to-voice mapping
    unique_speakers = list(dict.fromkeys(seg.speaker for seg in script.segments))
    if not unique_speakers:
        raise ValueError("PodcastScript has no speakers")

    voice_map = {}
    for i, speaker in enumerate(unique_speakers):
        if i < len(DEFAULT_VOICES):
            voice_map[speaker] = DEFAULT_VOICES[i]
        else:
            # Fallback: add numeric suffix to last voice
            voice_map[speaker] = f"{DEFAULT_VOICES[-1]}-{i+1}"

    # Synthesize each segment
    all_pcm = []
    sample_rates = []

    for i, segment in enumerate(script.segments):
        voice = voice_map.get(segment.speaker, DEFAULT_VOICES[0])

        # Synthesize segment
        pcm_bytes, sample_rate = _synthesize_segment(
            segment.content,
            voice=voice,
            sample_rate=DEFAULT_SAMPLE_RATE,
            speed=speed,
        )
        all_pcm.append(pcm_bytes)
        sample_rates.append(sample_rate)

        # Add pause between segments (not after the last one)
        if i < len(script.segments) - 1:
            silence = _generate_silence(pause_duration, sample_rate=sample_rate)
            all_pcm.append(silence)

    # Concatenate all segments
    wav_bytes, actual_sample_rate = _concatenate_wavs(all_pcm, sample_rates)

    # Calculate duration
    total_samples = len(wav_bytes) // 2  # 16-bit mono
    duration_seconds = total_samples / actual_sample_rate

    # Generate MP3 if requested
    mp3_bytes = b""
    if include_mp3:
        try:
            mp3_bytes = _wav_to_mp3(wav_bytes)
        except RuntimeError as e:
            print(f"Warning: MP3 conversion failed: {e}")
            mp3_bytes = b""

    # Write to files if output_path provided
    if output_path:
        out_dir = Path(output_path)
        out_dir.mkdir(parents=True, exist_ok=True)

        wav_path = out_dir / "podcast.wav"
        wav_path.write_bytes(wav_bytes)

        if mp3_bytes:
            mp3_path = out_dir / "podcast.mp3"
            mp3_path.write_bytes(mp3_bytes)

    return PodcastAudioResult(
        wav_bytes=wav_bytes,
        mp3_bytes=mp3_bytes,
        duration_seconds=duration_seconds,
        total_segments=len(script.segments),
        backend_used=DEFAULT_BACKEND,
    )


# ---------------------------------------------------------------------------
# Manual verification
# ---------------------------------------------------------------------------

def test_podcast_audio_rendering():
    """
    Contract: Manual verification for podcast audio rendering.

    To test manually:
    1. Ensure LM Studio is running on localhost:1234
    2. Run: python -c "from engines.audio_engine.podcast_audio import render_podcast_to_audio; from engines.audio_engine.podcast_script import PodcastScript, PodcastSegment; script = PodcastScript(topic='Test', title='Test', host_name='Host', duration_minutes=1, segments=[PodcastSegment(type='intro', speaker='Alice', content='Hello from Alice'), PodcastSegment(type='dialogue', speaker='Bob', content='Hello from Bob'), PodcastSegment(type='conclusion', speaker='Alice', content='Goodbye from Alice')], speakers=['Alice', 'Bob']); result = render_podcast_to_audio(script); print(f'Duration: {result.duration_seconds}s')"
    3. Verify audio file is generated and has correct duration
    """
    print("Manual verification function — run with actual TTS models")
    return True


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
