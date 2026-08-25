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

from engines.audio_engine import assembly, voice_catalog
from engines.audio_engine.podcast_audio import PodcastAudioResult
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

# Voice resolution lives ONLY in the Voice Catalog (P2.3); the private
# per-engine tables that used to live here were stale copies that 404'd
# against the real Piper repository.


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
# Translation verification (P3.2)
# ---------------------------------------------------------------------------

@dataclass
class VerificationVerdict:
    """Human-inspectable result of checking a BilingualPair's fidelity."""
    passed: bool
    issues: list[dict[str, Any]]

    def __bool__(self) -> bool:
        return self.passed


@dataclass
class VerifiedBilingualPair:
    """A lesson plus every fidelity verdict collected while producing it."""
    pair: "BilingualPair"
    verdicts: list[VerificationVerdict]

    @property
    def passed(self) -> bool:
        return bool(self.verdicts) and self.verdicts[-1].passed


def _format_segments_for_review(pair: "BilingualPair") -> str:
    return "\n".join(
        f"{i}. [{seg.target_text}] -> [{seg.translation_text}]"
        for i, seg in enumerate(pair.segments)
    )


def validate_verdict(data: Any) -> tuple[bool, list[str]]:
    """Contract: shape-check the reviewer's {passed, issues} payload."""
    if not isinstance(data, dict):
        return False, [f"expected a JSON object, got {type(data).__name__}"]
    errors = []
    if not isinstance(data.get("passed"), bool):
        errors.append("'passed' must be a boolean")
    issues = data.get("issues", [])
    if not isinstance(issues, list):
        errors.append("'issues' must be a list")
    else:
        for i, issue in enumerate(issues):
            if not isinstance(issue, dict) or "segment_index" not in issue or "problem" not in issue:
                errors.append(f"issue {i} needs 'segment_index' and 'problem'")
    return not errors, errors


def verify_bilingual_pair(
    pair: BilingualPair,
    *,
    client: LmStudioClient | None = None,
    model: str = DEFAULT_MODEL,
) -> VerificationVerdict:
    """
    Contract: ask the model to review a BilingualPair sentence-by-sentence
    and return an inspectable fidelity verdict (CONSTITUTION.md §3).

    Single pipeline attempt — a malformed review raises rather than being
    mistaken for a passing one.
    """
    parsed = run_guardrail_loop(
        PromptRegistry(),
        client if client is not None else LmStudioClient(),
        template="bilingual_verify",
        variables={
            "topic": pair.topic,
            "target_language": voice_catalog.language_name(pair.target_language),
            "known_language": voice_catalog.language_name(pair.known_language),
            "segments": _format_segments_for_review(pair),
        },
        validator=validate_verdict,
        model=model,
        max_tokens=1024,
        temperature=0.0,
    )
    return VerificationVerdict(passed=parsed["passed"], issues=parsed.get("issues", []))


def generate_bilingual_pair_verified(
    topic: str,
    target_language: str,
    known_language: str,
    *,
    num_segments: int = DEFAULT_NUM_SEGMENTS,
    max_regenerations: int = 1,
    client: LmStudioClient | None = None,
    model: str = DEFAULT_MODEL,
) -> VerifiedBilingualPair:
    """
    Contract: generate a bilingual lesson, verify its translations, and
    regenerate at most `max_regenerations` times until the review passes.
    Every verdict is kept so humans can audit what the checker said.

    Raises:
        SchemaValidationError: generation or review malformed after retries.
    """
    verdicts: list[VerificationVerdict] = []
    for attempt in range(max_regenerations + 1):
        pair = generate_bilingual_pair(
            topic, target_language, known_language,
            num_segments=num_segments, client=client, model=model,
        )
        verdicts.append(verify_bilingual_pair(pair, client=client, model=model))
        if verdicts[-1].passed:
            break
        logger.warning("Bilingual verification failed (attempt %d): %s",
                       attempt + 1, verdicts[-1].issues)
    return VerifiedBilingualPair(pair=pair, verdicts=verdicts)


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
    Render a BilingualPair to audio via the assembly seam.

    Per sentence pair: target-language voice speaks target_text, brief
    pause, known-language voice speaks translation_text, longer pause.
    Voices resolve through the Voice Catalog (target/known per language).

    Args:
        pair: BilingualPair object to render.
        include_mp3: Whether to convert to MP3 (default True).
        output_path: Optional directory to save bilingual.wav/.mp3.
        speed: Speech speed multiplier.

    Returns:
        PodcastAudioResult with wav/mp3 bytes and segment count.

    Raises:
        ValueError: If pair has no segments.
        RuntimeError: If TTS synthesis fails.
    """
    if not isinstance(pair, BilingualPair):
        raise TypeError(f"Expected BilingualPair, got {type(pair).__name__}")
    if not pair.segments:
        raise ValueError("BilingualPair has no segments")

    target_voice, known_voice = voice_catalog.pair_voices(
        pair.target_language, pair.known_language,
    )

    segments: list[tuple] = []
    for segment in pair.segments:
        segments.append((segment.target_text, target_voice, speed))
        segments.append(("silence", 0.2))  # between target and translation
        segments.append((segment.translation_text, known_voice, speed))
        segments.append(("silence", 0.3))  # between sentence pairs

    audio = assembly.render_segments(
        segments,
        include_mp3=include_mp3,
        output_path=output_path,
        basename="bilingual",
    )

    return PodcastAudioResult(
        wav_bytes=audio.wav_bytes,
        mp3_bytes=audio.mp3_bytes,
        duration_seconds=audio.duration_seconds,
        total_segments=len(pair.segments) * 2,  # target + translation
        backend_used=audio.backend_used,
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
