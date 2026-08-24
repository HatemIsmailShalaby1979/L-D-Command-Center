# engines/journey-core/generator.py
#
# WHAT: Journey generation entry point — takes (topic, level) and
#       returns a validated Journey dict (or raises).
# WHY:  Single point of contact between the journey-core engine and the
#       Generation Pipeline. Since P1.1 the Guardrail Loop lives in
#       model-layer/pipeline.py; this module contributes only what is
#       specific to Journeys: templates, schema validator, and the
#       level guard. It does NOT render HTML and does NOT export.
# BREAKS IF DELETED: The journey-core engine loses its ability to
#       produce journeys; export, audio, and language-lab all depend on
#       Journey data flowing from this function.

from __future__ import annotations

import logging
from typing import Any

from model_layer.client import ApiError, LmStudioClient
from model_layer.pipeline import DEFAULT_MODEL, generate as run_guardrail_loop
from model_layer.prompts import PromptRegistry
from model_layer.schema import (
    SchemaValidationError,
    SchemaValidator,
    validate_journey,
)

logger = logging.getLogger(__name__)

# Default number of cards to generate per journey
DEFAULT_NUM_CARDS = 5

_VALID_LEVELS = ("beginner", "intermediate", "advanced")


def generate_journey(
    topic: str,
    level: str,
    *,
    client: LmStudioClient | None = None,
    model: str = DEFAULT_MODEL,
    num_cards: int = DEFAULT_NUM_CARDS,
) -> dict[str, Any]:
    """
    Contract: generate a schema-valid Journey dict for the given topic
    and level by running the Generation Pipeline.

    Args:
        topic: the subject to generate a learning journey for.
        level: one of "beginner", "intermediate", "advanced".
        client: optional pre-configured LmStudioClient (or test double).
                A default client (localhost:1234) is created if omitted.
        model: model identifier passed through to LM Studio.
        num_cards: how many cards to request (minimum 1).

    Returns:
        A dict matching JOURNEY_SCHEMA, validated and ready for the HTML
        renderer or the export engine.

    Raises:
        ValueError: invalid level.
        SchemaValidationError: model output failed validation after all
            pipeline attempts.
        ConnectionError / ApiError: client-layer failures per the
            pipeline's transient-error policy.

    Non-responsibilities:
        - HTML rendering (downstream renderer module)
        - Export to PDF/DOCX/etc. (export-engine)
        - Audio generation (audio-engine)
    """
    if level not in _VALID_LEVELS:
        raise ValueError(f"Invalid level {level!r}; expected beginner/intermediate/advanced")

    result = run_guardrail_loop(
        PromptRegistry(),
        client if client is not None else LmStudioClient(),
        template="journey_generate",
        retry_template="journey_retry",
        variables={
            "topic": topic,
            "level": level,
            "num_cards": num_cards,
        },
        validator=validate_journey,
        model=model,
    )

    logger.info(
        "Journey generated for topic=%r level=%r with %d cards",
        topic,
        level,
        len(result.get("cards", [])),
    )
    return result
