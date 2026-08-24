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

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Resolve paths so we can import sibling modules without package naming
# constraints (the directory is "journey-core" with a hyphen, which
# cannot be a Python package name).
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

_MODEL_LAYER_PATH = _ROOT / "model-layer"
sys.path.insert(0, str(_MODEL_LAYER_PATH))

# Import model-layer modules directly by file path
import client as _client_module
import prompts as _prompts_module
import schema as _schema_module

# Re-export for test imports
client = _client_module
prompts = _prompts_module
schema = _schema_module

# Public API from model-layer (renamed for local use)
LmStudioClient = _client_module.LmStudioClient
ModelRequest = _client_module.ModelRequest
ApiError = _client_module.ApiError
PromptRegistry = _prompts_module.PromptRegistry
SchemaValidator = _schema_module.SchemaValidator
validate_journey = _schema_module.validate_journey
SchemaValidationError = _schema_module.SchemaValidationError

logger.info("journey-core generator loaded (model-layer path: %s)", _MODEL_LAYER_PATH)

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
