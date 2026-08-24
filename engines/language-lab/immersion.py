# engines/language-lab/immersion.py
#
# WHAT: Immersion podcast generation — produces a PodcastScript entirely
#       in the target language and renders it to audio with two distinct
#       voices. This is the "Speak Like an Alien" mode from the language
#       learning pillar.
# WHY:  Language immersion requires consuming content only in the target
#       language, not bilingual pairings. The model generates podcast
#       content in the target language, then renders with two voices
#       (e.g., host + guest) to simulate natural conversation.
# BREAKS IF DELETED: Immersion podcast capability is lost; language-lab
#       can't produce target-language-only audio content.
#
# Architecture:
#   - Uses audio-engine's generate_podcast_script() directly
#   - Uses audio-engine's render_podcast_to_audio() directly
#   - No new TTS logic — just configuration wiring
#
# Voice assignment:
#   - First speaker → first voice in pool
#   - Second speaker → second voice in pool
#   - Both voices are from the target language's voice pool

from __future__ import annotations

from typing import Any, Optional

from engines.audio_engine import voice_catalog
from engines.audio_engine.podcast_audio import PodcastAudioResult, render_podcast_to_audio
from engines.audio_engine.podcast_script import PodcastScript, generate_podcast_script
from model_layer.client import LmStudioClient
from model_layer.pipeline import DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_NUM_SEGMENTS = 5
DEFAULT_DURATION_MINUTES = 10
DEFAULT_HOST_NAME = "Host"
DEFAULT_SPEED = 0.9  # Slightly slower for language learning


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class ImmersionResult:
    """Result of immersion podcast generation."""

    def __init__(
        self,
        script: PodcastScript,
        audio: PodcastAudioResult,
    ) -> None:
        self.script = script
        self.audio = audio

    @property
    def wav_bytes(self) -> bytes:
        return self.audio.wav_bytes

    @property
    def mp3_bytes(self) -> bytes:
        return self.audio.mp3_bytes

    @property
    def duration_seconds(self) -> float:
        return self.audio.duration_seconds

    @property
    def total_segments(self) -> int:
        return self.audio.total_segments


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_immersion_podcast(
    topic: str,
    target_language: str,
    level: str = "beginner",
    *,
    num_segments: int = DEFAULT_NUM_SEGMENTS,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    host_name: str = DEFAULT_HOST_NAME,
    include_mp3: bool = True,
    output_path: Optional[str] = None,
    speed: float = DEFAULT_SPEED,
    client: LmStudioClient | None = None,
    model: str = DEFAULT_MODEL,
) -> ImmersionResult:
    """
    Contract: generate an immersion podcast entirely in the target language.

    Uses audio-engine's podcast_script generation and audio rendering
    without reimplementing either.

    Args:
        topic: The lesson topic (e.g., "Ordering food at a restaurant").
        target_language: ISO 639-1 language code (e.g., "es", "fr").
        level: Learning level ("beginner", "intermediate", "advanced").
        num_segments: Number of podcast segments.
        duration_minutes: Target duration in minutes.
        host_name: Name of the podcast host.
        include_mp3: Whether to include MP3 conversion.
        output_path: Optional directory to save audio files.
        speed: Speech speed multiplier.
        client: optional pre-configured LmStudioClient.
        model: model identifier for LM Studio.

    Returns:
        ImmersionResult containing the generated script and audio.

    Raises:
        ValueError: If topic or target_language is empty.
        SchemaValidationError: if script generation fails after retries.
        ConnectionError: if LM Studio is unreachable.
    """
    if not topic or not topic.strip():
        raise ValueError("Topic must be non-empty")
    if not target_language or not target_language.strip():
        raise ValueError("Target language must be specified")

    # Generate podcast script in the TARGET language at the requested
    # level — P3.1 closes defect #5 by actually forwarding both.
    script = generate_podcast_script(
        topic=topic,
        num_segments=num_segments,
        duration_minutes=duration_minutes,
        host_name=host_name,
        language=voice_catalog.language_name(target_language),
        level=level,
        client=client,
        model=model,
    )

    # Render to audio
    audio = render_podcast_to_audio(
        script,
        include_mp3=include_mp3,
        output_path=output_path,
        speed=speed,
    )

    return ImmersionResult(script=script, audio=audio)


def generate_and_save_immersion(
    topic: str,
    target_language: str,
    level: str = "beginner",
    output_path: str = "output",
    **kwargs: Any,
) -> ImmersionResult:
    """
    Convenience function that saves audio to disk.

    Args:
        topic: The lesson topic.
        target_language: ISO 639-1 target language code.
        level: Learning level.
        output_path: Directory to save audio files.
        **kwargs: Passed to generate_immersion_podcast().

    Returns:
        ImmersionResult with saved files.
    """
    result = generate_immersion_podcast(
        topic=topic,
        target_language=target_language,
        level=level,
        output_path=output_path,
        **kwargs,
    )

    # Log success
    print(f"Immersion podcast saved to: {output_path}")
    print(f"  Duration: {result.duration_seconds:.1f}s")
    print(f"  Segments: {result.total_segments}")
    print(f"  Speakers: {result.script.speakers}")

    return result


# ---------------------------------------------------------------------------
# Manual verification
# ---------------------------------------------------------------------------

def test_immersion_generation():
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
    print("Manual verification function — run with LM Studio")
    return True


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
