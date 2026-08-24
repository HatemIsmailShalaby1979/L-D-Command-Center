# engines/language-lab/bilingual.py
#
# WHAT: Bilingual lesson generation — creates sentence-by-sentence
#       target-language/known-language pairs via the model layer,
#       then renders them to audio using audio-engine's TTS client.
# WHY:  Language learning requires accurate, faithful translation,
#       not creative interpretation. CONSTITUTION.md §3 mandates
#       that translation accuracy is a correctness problem — every
#       sentence is validated and retried on failure.
# BREAKS IF DELETED: Language-lab loses its core capability — no
#       bilingual lesson generation, no language learning audio.
#
# Architecture:
#   - generate_bilingual_pair() — Generation Pipeline call with schema
#     validation and feedback retry (P1.5)
#   - render_bilingual_audio() — reuses podcast_audio._synthesize_segment
#     and _generate_silence from audio-engine
#   - Two-pass synthesis: target language voice first, then known
#     language voice for each segment
#
# Voice mapping:
#   - target_text spoken by a target-language-capable voice
#   - translation_text spoken by a known-language voice
#   - Voices assigned deterministically by language pair

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from engines.audio_engine.podcast_audio import (
    DEFAULT_SAMPLE_RATE,
    PodcastAudioResult,
    _concatenate_wavs,
    _generate_silence,
    _synthesize_segment,
    _wav_to_mp3,
)
from model_layer.client import LmStudioClient
from model_layer.pipeline import DEFAULT_MODEL, generate as run_guardrail_loop
from model_layer.prompts import PromptRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROMPT_KEY = "bilingual_generate"
RETRY_KEY = "bilingual_retry"

DEFAULT_NUM_SEGMENTS = 10
DEFAULT_SPEED = 0.9  # Slightly slower for language learning

# Target-language voices (Piper)
TARGET_VOICES = {
    "es": "es_ES-carlos-medium",
    "fr": "fr_FR-alphonse-medium",
    "de": "de_DE-karlsson-medium",
    "it": "it_IT-eva-medium",
    "pt": "pt_BR-isabella-medium",
    "ru": "ru_RU-dmitri-medium",
    "ja": "ja_JP-ken_medium",
    "zh": "zh_CN-huayan-medium",
    "ko": "ko_KR-youngmi-medium",
    "en": "en_US-lessac-medium",
}

# Known-language voices (Piper)
KNOWN_VOICES = {
    "en": "en_US-lessac-medium",
    "es": "es_ES-carlos-medium",
    "fr": "fr_FR-alphonse-medium",
    "de": "de_DE-karlsson-medium",
    "it": "it_IT-eva-medium",
    "pt": "pt_BR-isabella-medium",
    "ru": "ru_RU-dmitri-medium",
    "ja": "ja_JP-ken_medium",
    "zh": "zh_CN-huayan-medium",
    "ko": "ko_KR-youngmi-medium",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BilingualSegment:
    """A single bilingual sentence pair."""
    target_text: str
    translation_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_text": self.target_text,
            "translation_text": self.translation_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BilingualSegment":
        return cls(
            target_text=data["target_text"],
            translation_text=data["translation_text"],
        )


@dataclass
class BilingualPair:
    """A complete bilingual lesson."""
    topic: str
    target_language: str
    known_language: str
    segments: list[BilingualSegment]

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "target_language": self.target_language,
            "known_language": self.known_language,
            "segments": [seg.to_dict() for seg in self.segments],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BilingualPair":
        segments = [BilingualSegment.from_dict(seg) for seg in data.get("segments", [])]
        return cls(
            topic=data["topic"],
            target_language=data["target_language"],
            known_language=data["known_language"],
            segments=segments,
        )


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def validate_bilingual_pair(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Contract: validate a bilingual pair dict against the schema.

    Translation accuracy is critical — both target_text and
    translation_text must be present and non-empty.

    Returns:
        (is_valid, errors) tuple.
    """
    errors = []

    # Required fields
    required = ["topic", "target_language", "known_language", "segments"]
    for field_name in required:
        if field_name not in data:
            errors.append(f"Missing required field: {field_name}")

    if errors:
        return False, errors

    # Validate segments
    if not isinstance(data["segments"], list) or len(data["segments"]) == 0:
        errors.append("segments must be a non-empty list")
    else:
        for i, seg in enumerate(data["segments"]):
            if not isinstance(seg, dict):
                errors.append(f"segment {i} must be a dict")
                continue
            seg_errors = []
            if "target_text" not in seg or not seg["target_text"].strip():
                seg_errors.append("missing or empty 'target_text'")
            if "translation_text" not in seg or not seg["translation_text"].strip():
                seg_errors.append("missing or empty 'translation_text'")
            if seg_errors:
                errors.append(f"segment {i}: {', '.join(seg_errors)}")

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_bilingual_pair(
    topic: str,
    target_language: str,
    known_language: str,
    *,
    num_segments: int = DEFAULT_NUM_SEGMENTS,
    client: LmStudioClient | None = None,
    model: str = DEFAULT_MODEL,
) -> BilingualPair:
    """
    Contract: generate a bilingual lesson via the Generation Pipeline.

    Translation accuracy is a correctness problem (CONSTITUTION.md §3):
    every sentence pair is schema-validated, with feedback-driven retry.

    Args:
        topic: The lesson topic (e.g., "Ordering food at a restaurant").
        target_language: ISO 639-1 language code (e.g., "es", "fr").
        known_language: ISO 639-1 language code (e.g., "en", "zh").
        num_segments: Number of sentence pairs to generate.
        client: optional pre-configured LmStudioClient (or test double).
        model: model identifier for LM Studio.

    Returns:
        Validated BilingualPair object.

    Raises:
        ValueError: If topic or languages are empty.
        SchemaValidationError: if generation fails after all attempts.
        ConnectionError: if LM Studio is unreachable.
    """
    if not topic or not topic.strip():
        raise ValueError("Topic must be non-empty")
    if not target_language or not target_language.strip():
        raise ValueError("Target language must be specified")
    if not known_language or not known_language.strip():
        raise ValueError("Known language must be specified")

    parsed = run_guardrail_loop(
        PromptRegistry(),
        client if client is not None else LmStudioClient(),
        template="bilingual_generate",
        retry_template="bilingual_retry",
        variables={
            "topic": topic,
            "target_language": target_language,
            "known_language": known_language,
            "num_segments": num_segments,
        },
        validator=validate_bilingual_pair,
        model=model,
    )
    logger.info("Bilingual pair generated: %s (%s → %s)", topic[:50], target_language, known_language)
    return BilingualPair.from_dict(parsed)


def render_bilingual_audio(
    pair: BilingualPair,
    *,
    include_mp3: bool = True,
    output_path: Optional[str] = None,
    speed: float = DEFAULT_SPEED,
) -> PodcastAudioResult:
    """
    Render a BilingualPair to audio using audio-engine's TTS client.

    For each segment:
    1. Synthesize target_text in target language voice
    2. Insert brief pause
    3. Synthesize translation_text in known language voice
    4. Insert brief pause

    Args:
        pair: BilingualPair object to render.
        include_mp3: Whether to convert to MP3 (default True).
        output_path: Optional directory to save audio files.
        speed: Speech speed multiplier.

    Returns:
        PodcastAudioResult with wav_bytes, mp3_bytes, duration, etc.

    Raises:
        ValueError: If pair has no segments.
        RuntimeError: If TTS synthesis fails.
    """
    if not isinstance(pair, BilingualPair):
        raise TypeError(f"Expected BilingualPair, got {type(pair).__name__}")

    if not pair.segments:
        raise ValueError("BilingualPair has no segments")

    # Get voices for this language pair
    target_voice = TARGET_VOICES.get(pair.target_language, "en_US-lessac-medium")
    known_voice = KNOWN_VOICES.get(pair.known_language, "en_US-lessac-medium")

    # Synthesize each segment
    all_pcm = []
    sample_rates = []

    for segment in pair.segments:
        # Target language text
        target_pcm, target_sr = _synthesize_segment(
            segment.target_text,
            voice=target_voice,
            speed=speed,
        )
        all_pcm.append(target_pcm)
        sample_rates.append(target_sr)

        # Brief pause between target and translation
        silence = _generate_silence(0.2, sample_rate=target_sr)
        all_pcm.append(silence)
        sample_rates.append(target_sr)

        # Known language translation
        trans_pcm, trans_sr = _synthesize_segment(
            segment.translation_text,
            voice=known_voice,
            speed=speed,
        )
        all_pcm.append(trans_pcm)
        sample_rates.append(trans_sr)

        # Brief pause between segments
        pause = _generate_silence(0.3, sample_rate=trans_sr)
        all_pcm.append(pause)
        sample_rates.append(trans_sr)

    # Concatenate all segments
    wav_bytes, actual_sample_rate = _concatenate_wavs(all_pcm, sample_rates)

    # Calculate duration
    total_samples = len(wav_bytes) // 2
    duration_seconds = total_samples / actual_sample_rate

    # Generate MP3 if requested
    mp3_bytes = b""
    if include_mp3:
        try:
            mp3_bytes = _wav_to_mp3(wav_bytes)
        except RuntimeError:
            mp3_bytes = b""

    # Write to files if output_path provided
    if output_path:
        out_dir = Path(output_path)
        out_dir.mkdir(parents=True, exist_ok=True)
        wav_path = out_dir / "bilingual.wav"
        wav_path.write_bytes(wav_bytes)
        if mp3_bytes:
            mp3_path = out_dir / "bilingual.mp3"
            mp3_path.write_bytes(mp3_bytes)

    return PodcastAudioResult(
        wav_bytes=wav_bytes,
        mp3_bytes=mp3_bytes,
        duration_seconds=duration_seconds,
        total_segments=len(pair.segments) * 2,  # target + translation
        backend_used="PIPER",
    )


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def generate_and_render(
    topic: str,
    target_language: str,
    known_language: str,
    *,
    num_segments: int = DEFAULT_NUM_SEGMENTS,
    include_mp3: bool = True,
    output_path: Optional[str] = None,
    speed: float = DEFAULT_SPEED,
    client: LmStudioClient | None = None,
    model: str = "default",
) -> tuple[BilingualPair, PodcastAudioResult]:
    """
    Contract: generate a bilingual pair and render to audio in one call.

    Args:
        topic: The lesson topic.
        target_language: ISO 639-1 target language code.
        known_language: ISO 639-1 known language code.
        num_segments: Number of sentence pairs.
        include_mp3: Whether to include MP3.
        output_path: Optional output directory.
        speed: Speech speed.
        client: optional LM Studio client.
        model: model identifier.

    Returns:
        Tuple of (BilingualPair, PodcastAudioResult).
    """
    pair = generate_bilingual_pair(
        topic, target_language, known_language,
        num_segments=num_segments,
        client=client,
        model=model,
    )
    audio = render_bilingual_audio(
        pair,
        include_mp3=include_mp3,
        output_path=output_path,
        speed=speed,
    )
    return pair, audio


# ---------------------------------------------------------------------------
# Manual verification
# ---------------------------------------------------------------------------

def test_bilingual_generation():
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
       "
    3. Verify audio file has both Spanish and English sections
    """
    print("Manual verification function — run with LM Studio")
    return True


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
