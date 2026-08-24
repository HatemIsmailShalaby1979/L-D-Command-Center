# engines/audio-engine/podcast_script.py
#
# WHAT: Podcast script generation using the model layer.
# WHY:  Provides a structured script format for podcast episodes with
#       speaker turns, introductions, and conclusions. Scripts are
#       schema-validated with retry logic, following the same pattern
#       as journey-core and career-engine.
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

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Add model-layer to path
_MODEL_LAYER = Path(__file__).resolve().parent.parent.parent / "model-layer"
sys.path.insert(0, str(_MODEL_LAYER))

from client import LmStudioClient
from prompts import PromptRegistry
from schema import SchemaValidator, SchemaValidationError, extract_json_from_text


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROMPT_KEY = "podcast_script_generate"

DEFAULT_HOST_NAME = "Host"
DEFAULT_DURATION_MINUTES = 15
DEFAULT_NUM_SEGMENTS = 5


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

    @property
    def total_duration_seconds(self) -> int:
        return sum(seg.duration_seconds for seg in self.segments)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "title": self.title,
            "host_name": self.host_name,
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
    client: LmStudioClient | None = None,
    model: str = "default",
) -> PodcastScript:
    """
    Contract: generate a podcast script for a topic or Journey.

    Uses the model-layer's SchemaValidator for retry-on-failure.

    Args:
        topic: Optional topic string (e.g., "Python for beginners").
        journey: Optional pre-generated Journey dict to convert to podcast.
        num_segments: Number of segments to generate (1-20).
        duration_minutes: Target duration in minutes.
        host_name: Name of the podcast host.
        client: optional pre-configured LmStudioClient.
        model: model identifier for LM Studio.

    Returns:
        Validated PodcastScript object.

    Raises:
        ValueError: If neither topic nor journey is provided.
        SchemaValidationError: if script generation fails after retries.
        ConnectionError: if LM Studio is unreachable.
    """
    if not topic and not journey:
        raise ValueError("Either 'topic' or 'journey' must be provided")

    # Prepare topic from journey if provided
    if journey:
        topic = journey.get("topic", "General Topic")

    # Build the prompt
    registry = PromptRegistry()
    validator = SchemaValidator(max_attempts=3)

    # Serialize journey if provided
    journey_json = json.dumps(journey, ensure_ascii=False, indent=2) if journey else ""

    # Build the retry callback
    def _retry_callback(errors: list[str]) -> str:
        errors_text = "\n".join(f"  - {e}" for e in errors)
        system, user, _ = registry.render(
            "podcast_script_retry",
            {
                "topic": topic,
                "num_segments": num_segments,
                "errors": errors_text,
            },
        )
        return _call_model(system, user, model, client=client)

    # First attempt: generate the podcast script
    system, user, _ = registry.render(
        PROMPT_KEY,
        {
            "topic": topic,
            "num_segments": num_segments,
            "duration_minutes": duration_minutes,
            "host_name": host_name,
        },
    )
    raw_output = _call_model(system, user, model, client=client)

    # Parse the JSON response
    parsed = extract_json_from_text(raw_output)
    if parsed is None:
        raise SchemaValidationError(["Could not extract JSON from model response"], 1)

    # Validate and retry if needed
    is_valid, errors = validate_podcast_script(parsed)
    if not is_valid:
        parsed = validator.validate(
            raw_output,
            schema_fn=validate_podcast_script,
            retry_callback=_retry_callback,
        )
        is_valid, errors = validate_podcast_script(parsed)
        if not is_valid:
            raise SchemaValidationError(errors, 3)

    logger.info("Podcast script generated for topic: %s", topic[:50])
    return PodcastScript.from_dict(parsed)


def _call_model(
    system: str,
    user: str,
    model: str,
    client: LmStudioClient | None = None,
) -> str:
    """
    Contract: call the LM Studio client with the given prompts.

    Args:
        system: system prompt.
        user: user prompt.
        model: model identifier.
        client: optional pre-configured client.

    Returns:
        Raw model response string.
    """
    if client is None:
        client = LmStudioClient(model=model)
    return client.generate(system, user)


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
