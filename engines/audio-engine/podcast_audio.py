# engines/audio-engine/podcast_audio.py
#
# WHAT: Renders a PodcastScript to a single audio file — maps each
#       speaker to a distinct voice and delegates byte mechanics to the
#       audio-engine assembly seam (P2.4).
# WHY:  Speaker-to-voice assignment is podcast-specific knowledge;
#       synthesis, silence, concatenation, and MP3 conversion are not —
#       those live behind assembly.render_segments(). Voices resolve only
#       through the Voice Catalog (CONTEXT.md).
# BREAKS IF DELETED: Podcast scripts lose their audio rendering;
#       immersion mode inherits its rendering from here.

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from engines.audio_engine import assembly, voice_catalog
from engines.audio_engine.assembly import (
    DEFAULT_SAMPLE_RATE,
    _make_wav_header,      # noqa: F401 — re-exported for direct unit tests
    _parse_wav_to_pcm,
    generate_silence as _generate_silence,      # noqa: F401
    concatenate as _concatenate_wavs,           # noqa: F401
    synthesize as _synthesize_segment,          # noqa: F401
    wav_to_mp3 as _wav_to_mp3,                  # noqa: F401
)
from model_layer.tts import TtsBackend

logger = logging.getLogger(__name__)

# Historical name for the catalog's speaker pool (kept for direct tests).
DEFAULT_VOICES = voice_catalog.PIPER_SPEAKER_POOL

PAUSE_DURATION_SECONDS = 0.3
DEFAULT_SPEED = 1.0


@dataclass
class PodcastAudioResult:
    """Result of podcast audio rendering."""
    wav_bytes: bytes
    mp3_bytes: bytes
    duration_seconds: float
    total_segments: int
    backend_used: TtsBackend


def render_podcast_to_audio(
    script: "PodcastScript",
    *,
    include_mp3: bool = True,
    output_path: Optional[str] = None,
    speed: float = DEFAULT_SPEED,
    pause_duration: float = PAUSE_DURATION_SECONDS,
    voice_map: Optional[dict[str, str]] = None,
) -> PodcastAudioResult:
    """
    Contract: render a PodcastScript to a single audio artifact.

    Each unique speaker gets a distinct voice from the Voice Catalog's
    speaker pool (ordered by first appearance); a brief silence separates
    consecutive segments.

    Args:
        script: PodcastScript to render.
        include_mp3: attempt MP3 conversion (failure degrades to WAV-only).
        output_path: directory to write podcast.wav / podcast.mp3 into.
        speed: speech speed multiplier.
        pause_duration: seconds of silence between segments.

    Returns:
        PodcastAudioResult with wav/mp3 bytes, duration, segment count.

    Raises:
        TypeError/ValueError: malformed or empty script.
        RuntimeError: TTS synthesis failure propagates.
    """
    from engines.audio_engine.podcast_script import PodcastScript

    if not isinstance(script, PodcastScript):
        raise TypeError(f"Expected PodcastScript, got {type(script).__name__}")
    if not script.segments:
        raise ValueError("PodcastScript has no segments")

    # Distinct voice per speaker, ordered by first appearance. An explicit
    # voice_map (speaker -> voice id) wins — the UI's Voice A / Voice B
    # pickers land here.
    unique_speakers = list(dict.fromkeys(seg.speaker for seg in script.segments))
    assigned = dict(zip(unique_speakers,
                        voice_catalog.speaker_voices(len(unique_speakers))))
    if voice_map:
        unknown = set(voice_map) - set(unique_speakers)
        if unknown:
            raise ValueError(
                f"voice_map names speakers not in the script: {sorted(unknown)}")
        assigned.update({k: v for k, v in voice_map.items() if v})
    voice_map = assigned

    segments: list[tuple] = []
    for i, segment in enumerate(script.segments):
        segments.append((segment.content, voice_map[segment.speaker], speed))
        if i < len(script.segments) - 1:
            segments.append(("silence", pause_duration))

    audio = assembly.render_segments(
        segments,
        include_mp3=include_mp3,
        output_path=output_path,
        basename="podcast",
    )

    return PodcastAudioResult(
        wav_bytes=audio.wav_bytes,
        mp3_bytes=audio.mp3_bytes,
        duration_seconds=audio.duration_seconds,
        total_segments=len(script.segments),
        backend_used=audio.backend_used,
    )
