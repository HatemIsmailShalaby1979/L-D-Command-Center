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
            for i in range(1, len(speakers_in_turns)):
                if speakers_in_turns[i] == speakers_in_turns[i - 1]:
                    errors.append(
                        f"segment {i}: same speaker as previous turn — "
                        "hosts must alternate to read as a conversation")
                    break

    return len(errors) == 0, errors


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
    total_seg_seconds = duration_minutes * 60
    num_segments = max(num_segments,
                       round(total_seg_seconds / SEGMENT_SECONDS_PER_MINUTE))
    seg_dur = round(total_seg_seconds / num_segments)

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
            "host_name": host_name,
            "co_host_name": co_host_name,
            "language": language,
            "level": level,
        },
        validator=validate_podcast_script,
        model=model,
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
