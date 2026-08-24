# engines/journey-core/generator.py
#
# WHAT: Journey generation entry point — takes (topic, level) and
#       returns a validated Journey dict (or raises).
# WHY:  This is the single point of contact between the journey-core
#       engine and the model-layer. It owns the generate→validate→retry
#       loop so every caller gets a schema-valid Journey or an error.
#       It does NOT render HTML and does NOT export — those belong to
#       other engines.
# BREAKS IF DELETED: The journey-core engine loses its ability to
#       produce journeys; the export, audio, and language-lab engines
#       all depend on journey data flowing from this function.

from __future__ import annotations

import logging
from typing import Any

from model_layer.client import ApiError, LmStudioClient, ModelRequest
from model_layer.prompts import PromptRegistry
from model_layer.schema import (
    SchemaValidationError,
    SchemaValidator,
    validate_journey,
)

logger = logging.getLogger(__name__)
logger.info("journey-core generator loaded")

# Default number of cards to generate per journey
DEFAULT_NUM_CARDS = 5


def generate_journey(
    topic: str,
    level: str,
    *,
    client: LmStudioClient | None = None,
    model: str = "local-model",
    num_cards: int = DEFAULT_NUM_CARDS,
) -> dict[str, Any]:
    """
    Contract: generate a schema-valid Journey dict for the given topic
    and level by calling the local LM Studio model through the
    model-layer stack.

    Args:
        topic: the subject to generate a learning journey for.
        level: one of "beginner", "intermediate", "advanced".
        client: optional pre-configured LmStudioClient. A default
                client (localhost:1234) is created if omitted.
        model: model identifier to pass to LM Studio.
        num_cards: how many cards to request (minimum 1).

    Returns:
        A dict matching the JOURNEY_SCHEMA, validated and ready for
        the journey-core HTML renderer or the export engine.

    Raises:
        SchemaValidationError: if the model fails to produce valid
                               output after all retry attempts.
        ConnectionError: if LM Studio is unreachable.
        ApiError: for other client-layer failures.

    Non-responsibilities:
      - HTML rendering (handled by a downstream renderer module)
      - Export to PDF/DOCX/etc. (handled by export-engine)
      - Audio generation (handled by audio-engine)
    """
    if level not in ("beginner", "intermediate", "advanced"):
        raise ValueError(f"Invalid level {level!r}; expected beginner/intermediate/advanced")

    registry = PromptRegistry()
    validator = SchemaValidator(max_attempts=3)

    # Build the retry callback that re-prompts with validation errors
    def _retry_callback(errors: list[str]) -> str:
        system, user, _ = registry.render(
            "journey_retry",
            {
                "topic": topic,
                "level": level,
                "num_cards": num_cards,
                "errors": "\n".join(f"  - {e}" for e in errors),
            },
        )
        return _call_model(system, user, model, client=client)

    # First attempt: generate the journey
    system, user, schema_key = registry.render(
        "journey_generate",
        {
            "topic": topic,
            "level": level,
            "num_cards": num_cards,
        },
    )
    raw_output = _call_model(system, user, model, client=client)

    # Validate with retry on failure
    result = validator.validate(
        raw_output,
        schema_fn=validate_journey,
        retry_callback=_retry_callback,
    )

    logger.info(
        "Journey generated for topic=%r level=%r with %d cards",
        topic,
        level,
        len(result.get("cards", [])),
    )
    return result


def _call_model(
    system: str,
    user: str,
    model: str,
    *,
    client: LmStudioClient | None = None,
) -> str:
    """
    Contract: send a single chat completion request and return the
    raw content string. Used internally by generate_journey and by
    the retry callback.
    """
    if client is None:
        client = LmStudioClient()

    request = ModelRequest(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=4096,
        temperature=0.7,
    )
    response = client.generate(request)

    if response.content is None:
        # Model returned a tool call instead of content — log and raise
        tool_names = [tc.name for tc in (response.tool_calls or [])]
        raise ApiError(
            f"Model returned tool calls ({tool_names}) instead of content. "
            "This model does not support the requested tool schema."
        )

    return response.content
