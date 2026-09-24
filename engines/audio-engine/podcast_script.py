# engines/audio-engine/podcast_script.py
#
# WHAT: Podcast script generation using the model layer.
# WHY:  Provides a structured script format for podcast episodes with
#       speaker turns, introductions, and conclusions. Generation runs
#       through the Generation Pipeline (P1.5), which owns validation,
#       extraction, and retry policy.
# BREAKS IF DELETED: Podcast script generation is lost; audio-engine
#       can't produce structured episode content.
#
# Contract (PodcastScript):
#   - topic: str — The subject of the podcast episode
#   - title: str — Episode title
#   - host_name: str — Name of the host
#   - duration_minutes: int — Estimated duration
#   - segments: list[PodcastSegment] — Ordered list of segments
#   - speakers: list[str] — List of speaker names
#
# PodcastSegment:
#   - type: str — "intro", "monologue", "dialogue", "conclusion"
#   - speaker: str — Who is speaking
#   - content: str — What is said
#   - duration_seconds: int — Estimated duration in seconds

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from model_layer.client import LmStudioClient
from model_layer.pipeline import DEFAULT_MODEL, generate as run_guardrail_loop
from model_layer.prompts import PromptRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROMPT_KEY = "podcast_script_generate"

DEFAULT_HOST_NAME = "Alex"
DEFAULT_CO_HOST_NAME = "Maya"
DEFAULT_DURATION_MINUTES = 15
DEFAULT_NUM_SEGMENTS = 5
SEGMENT_SECONDS_PER_MINUTE = 90  # each segment ~90 seconds = 1.5 min

# ---------------------------------------------------------------------------
# Length compliance (2026-09-24, calibrated 2026-09-24 from live granite4.2)
# ---------------------------------------------------------------------------
# Root cause of "15-minute" podcasts rendering as ~10 seconds: TTS duration
# follows WORD COUNT, not the model-invented `duration_seconds` metadata.
# Measured live: Piper en_US-lessac-medium @ speed 1.0 ≈ 205.6 WPM.
# Plan the prompt at ~200 WPM so content lands near the target even before
# the controller's stretch re-render; reject scripts below
# 100×0.90 = 90 words/minute of requested duration. The previous
# 170×0.90 = 153 WPM and then 125×0.90 = 112 WPM floors were walls for
# degraded models: granite4.2 on a 12-min episode varied between ~1083
# and ~1597 words (90–133 WPM) across 5 feedback retries — valid
# conversation, but nondeterministically short of the old floors and
# occasionally with schema noise (missing speakers). Every 12-min
# request failed deterministically. 90 WPM still rejects truly thin
# content (the 15-min pre-fix artifact was 64 WPM) but lets a
# degraded model's short-but-valid output pass and be stretched toward
# target (stretch floor 0.70×: 90/205 ≈ 0.44 raw → 0.63 stretched).
# The validator is a borrowed constraint that must stay calibrated
# to what the seam can actually stretch, not to the idealized prompt.
TARGET_SPEAKING_WPM = 200
MIN_CONTENT_WPM = 100           # floor for the validator (was 170 — wall)
WORD_BUDGET_TOLERANCE = 0.90    # accept 90%+ of the planned word budget
MIN_STRETCH_SPEED = 0.70        # never slow narration below 0.70×
SHORT_RENDER_RATIO = 0.92       # re-render if actual < 92% of target

# A full episode (intro + dialogue + conclusion) is LONG. A tight
# max_tokens budget is what makes a 7B-12B local model "keep producing
# bad output": it hits the wall mid-JSON, or truncates the closing
# segments. The Generation Pipeline already honors an 8192-token budget
# (model-layer/pipeline.py); we pin it HERE so podcast generation can
# never silently fall back to a smaller template default.
PODCAST_MAX_TOKENS = 8192
# 7B-12B models need more feedback rounds to satisfy the strict
# two-speaker conversation + length validator — never a failure wall.
# 2026-09-24: raised 5→7 after live granite4.2 showed 12-min episodes
# failing on schema noise (missing speakers) as well as word-budget;
# 7 attempts still fit inside the 600s client timeout (≈40s per
# attempt) and give a degraded model two extra rolls to land a
# conversation-balanced, length-adequate output.
PODCAST_MAX_ATTEMPTS = 7


def words_for_duration(duration_minutes: int, wpm: int = TARGET_SPEAKING_WPM) -> int:
    """Planned word budget so narration hits `duration_minutes` at `wpm`."""
    return max(1, int(duration_minutes) * max(1, wpm))


def segment_word_budget(total_words: int, num_segments: int) -> int:
    """Even per-segment word target (intro/conclusion may run short)."""
    n = max(1, int(num_segments))
    return max(40, round(total_words / n))


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PodcastSegment:
    """A single segment of a podcast episode."""
    type: str  # "intro", "monologue", "dialogue", "conclusion"
    speaker: str
    content: str
    duration_seconds: int = 60

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "speaker": self.speaker,
            "content": self.content,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PodcastSegment":
        return cls(
            type=data["type"],
            speaker=data["speaker"],
            content=data["content"],
            duration_seconds=data.get("duration_seconds", 60),
        )


@dataclass
class PodcastScript:
    """A complete podcast episode script."""
    topic: str
    title: str
    host_name: str
    duration_minutes: int
    segments: list[PodcastSegment]
    speakers: list[str]
    co_host_name: str = "Maya"

    @property
    def total_duration_seconds(self) -> int:
        return sum(seg.duration_seconds for seg in self.segments)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "title": self.title,
            "host_name": self.host_name,
            "co_host_name": self.co_host_name,
            "duration_minutes": self.duration_minutes,
            "segments": [seg.to_dict() for seg in self.segments],
            "speakers": self.speakers,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PodcastScript":
        segments = [PodcastSegment.from_dict(seg) for seg in data.get("segments", [])]
        return cls(
            topic=data["topic"],
            title=data["title"],
            host_name=data.get("host_name", DEFAULT_HOST_NAME),
            co_host_name=data.get("co_host_name", DEFAULT_CO_HOST_NAME),
            duration_minutes=data.get("duration_minutes", DEFAULT_DURATION_MINUTES),
            segments=segments,
            speakers=data.get("speakers", []),
        )


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def validate_podcast_script(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Contract: validate a podcast script dict against the schema.

    Returns:
        (is_valid, errors) tuple.
    """
    errors = []

    # Required fields
    required = ["topic", "title", "segments", "speakers"]
    for field_name in required:
        if field_name not in data:
            errors.append(f"Missing required field: {field_name}")

    if errors:
        return False, errors

    # Validate segments
    if not isinstance(data["segments"], list) or len(data["segments"]) == 0:
        errors.append("segments must be a non-empty list")
    else:
        valid_types = {"intro", "monologue", "dialogue", "conclusion"}
        for i, seg in enumerate(data["segments"]):
            if not isinstance(seg, dict):
                errors.append(f"segment {i} must be a dict")
                continue
            seg_errors = []
            if "type" not in seg:
                seg_errors.append("missing 'type'")
            elif seg["type"] not in valid_types:
                seg_errors.append(f"invalid type: {seg['type']}")
            if "speaker" not in seg:
                seg_errors.append("missing 'speaker'")
            if "content" not in seg:
                seg_errors.append("missing 'content'")
            if seg_errors:
                errors.append(f"segment {i}: {', '.join(seg_errors)}")

    # Validate speakers
    if not isinstance(data["speakers"], list) or len(data["speakers"]) == 0:
        errors.append("speakers must be a non-empty list")

    # A podcast is a CONVERSATION: a script where one host talks to
    # themselves is an audiobook wearing a podcast's name (review
    # 2026-08-25: granite produced exactly that and it shipped).
    segments = data.get("segments") or []
    if isinstance(segments, list) and len(segments) >= 2:
        speakers_in_turns = [s.get("speaker") for s in segments
                             if isinstance(s, dict)]
        distinct = {x for x in speakers_in_turns if x}
        if len(distinct) < 2:
            errors.append(
                "podcast needs at least TWO distinct speakers having a "
                f"conversation; got {sorted(map(str, distinct))!r} — this "
                "is an audiobook, not a podcast")
        else:
            from collections import Counter
            counts = Counter(speakers_in_turns)
            dominant, dominant_n = counts.most_common(1)[0]
            if len(segments) >= 4 and dominant_n > 0.6 * len(segments):
                errors.append(
                    f"speaker {dominant!r} has {dominant_n}/{len(segments)} "
                    "turns — rebalance so both hosts genuinely converse")
            max_consecutive = 0
            streak = 1
            for i in range(1, len(speakers_in_turns)):
                if speakers_in_turns[i] == speakers_in_turns[i - 1]:
                    streak += 1
                    if streak > max_consecutive:
                        max_consecutive = streak
                else:
                    streak = 1
            if max_consecutive > 2:
                errors.append(
                    f"{max_consecutive} consecutive segments with the same "
                    "speaker — hosts should alternate more often to feel "
                    "like a conversation")

    return len(errors) == 0, errors


def content_word_count(data: dict[str, Any]) -> int:
    """Total spoken words across every segment's content."""
    total = 0
    for seg in data.get("segments") or []:
        if isinstance(seg, dict):
            total += len(str(seg.get("content") or "").split())
    return total


def make_length_validator(duration_minutes: int,
                          min_wpm: int = MIN_CONTENT_WPM,
                          tolerance: float = WORD_BUDGET_TOLERANCE):
    """Factory: schema validation + a word-count floor for the target length.

    `validate_podcast_script` alone cannot see the requested duration, so
    generation binds the target through this closure. The plain callable
    stays importable for tests and callers that only need schema checks.
    """
    min_words = max(1, int(duration_minutes * max(1, min_wpm)
                           * float(tolerance)))

    def validator(data: dict[str, Any]) -> tuple[bool, list[str]]:
        ok, errors = validate_podcast_script(data)
        if not ok:
            return ok, errors
        words = content_word_count(data)
        if words < min_words:
            errors = list(errors) + [
                f"content has only {words} words; a ~{duration_minutes}-minute "
                f"episode needs at least {min_words} words at "
                f"{min_wpm} WPM — expand every segment's spoken content so "
                "the audio actually reaches the requested length"
            ]
            return False, errors
        return True, []

    return validator


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_podcast_script(
    topic: Optional[str] = None,
    journey: Optional[dict[str, Any]] = None,
    *,
    num_segments: int = DEFAULT_NUM_SEGMENTS,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    host_name: str = DEFAULT_HOST_NAME,
    co_host_name: str = DEFAULT_CO_HOST_NAME,
    language: str = "English",
    level: str = "beginner",
    client: LmStudioClient | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = PODCAST_MAX_TOKENS,
    max_attempts: int = PODCAST_MAX_ATTEMPTS,
) -> PodcastScript:
    """
    Contract: generate a validated PodcastScript for a topic or Journey
    by running the Generation Pipeline.

    Args:
        topic: Optional topic string (e.g., "Python for beginners").
        journey: Optional Journey dict whose topic seeds the prompt.
        num_segments: Number of segments to generate.
        duration_minutes: Target duration in minutes.
        host_name: Name of the podcast host (interpolated into the prompt).
        language: Language every segment must be written in.
        level: Audience complexity level for the content.
        client: optional pre-configured LmStudioClient (or test double).
        model: model identifier for LM Studio.
        max_tokens: output token budget per attempt (default 8192 — a
            full episode needs it; small budgets truncate mid-JSON).
        max_attempts: feedback-retry budget (default 5 — enough rounds
            for 7B-12B models to satisfy the conversation validator).

    Returns:
        Validated PodcastScript object.

    Raises:
        ValueError: If neither topic nor journey is provided.
        SchemaValidationError: if generation fails after all attempts.
        ConnectionError: if LM Studio is unreachable.
    """
    if not topic and not journey:
        raise ValueError("Either 'topic' or 'journey' must be provided")
    if journey:
        topic = journey.get("topic", "General Topic")

    # Auto-scale segments to match the requested duration
    duration_minutes = max(1, int(duration_minutes))
    total_seg_seconds = duration_minutes * 60
    num_segments = max(num_segments,
                       round(total_seg_seconds / SEGMENT_SECONDS_PER_MINUTE))
    seg_dur = round(total_seg_seconds / num_segments)

    # Word budget is the real length contract: TTS duration follows words,
    # not the model-invented duration_seconds field.
    total_words = words_for_duration(duration_minutes)
    seg_words = segment_word_budget(total_words, num_segments)

    parsed = run_guardrail_loop(
        PromptRegistry(),
        client if client is not None else LmStudioClient(),
        template="podcast_script_generate",
        retry_template="podcast_script_retry",
        variables={
            "topic": topic,
            "num_segments": num_segments,
            "duration_minutes": duration_minutes,
            "segment_duration_seconds": seg_dur,
            "segment_words": seg_words,
            "total_words": total_words,
            "host_name": host_name,
            "co_host_name": co_host_name,
            "language": language,
            "level": level,
        },
        validator=make_length_validator(duration_minutes),
        model=model,
        max_tokens=max_tokens,
        max_attempts=max_attempts,
    )
    logger.info("Podcast script generated for topic: %s", topic[:50])
    return PodcastScript.from_dict(parsed)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def generate_script_from_journey(journey: dict[str, Any], **kwargs) -> PodcastScript:
    """
    Convenience function to generate a podcast script from a Journey.

    Args:
        journey: Journey dict with 'topic', 'level', and 'cards'.
        **kwargs: Passed to generate_podcast_script().

    Returns:
        PodcastScript object.
    """
    return generate_podcast_script(journey=journey, **kwargs)


def generate_script_from_topic(topic: str, **kwargs) -> PodcastScript:
    """
    Convenience function to generate a podcast script from a topic.

    Args:
        topic: Topic string (e.g., "Python for beginners").
        **kwargs: Passed to generate_podcast_script().

    Returns:
        PodcastScript object.
    """
    return generate_podcast_script(topic=topic, **kwargs)
