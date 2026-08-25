# model-layer/pipeline.py
#
# WHAT: The Generation Pipeline — the single implementation of the
#       Guardrail Loop (render prompt → call model → extract JSON →
#       validate against schema → retry with feedback → typed error).
# WHY:  CONSTITUTION.md §3 mandates this loop for every generation; before
#       P1.1 it was hand-rolled four times across engines, two copies
#       calling an LmStudioClient interface that does not exist. Every
#       artifact type now registers a template + validator here instead of
#       re-implementing the loop (see docs/PRODUCTION_PLAN.md P1.1 and
#       CONTEXT.md "Generation Pipeline").
# BREAKS IF DELETED: Each engine falls back to its own loop; retry policy,
#       JSON extraction, error taxonomy, and model defaults drift apart
#       again, and the broken un-mocked paths return.

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from model_layer.client import ApiError, LmStudioClient, ModelRequest
from model_layer.prompts import PromptRegistry
from model_layer.schema import (
    SchemaValidationError,
    extract_json_from_text,
)

logger = logging.getLogger(__name__)

# One policy for every engine — no more per-module default model ids.
DEFAULT_MODEL = "local-model"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_ATTEMPTS = 3


def _call_model(
    client: LmStudioClient,
    model: str,
    system: str,
    user: str,
    *,
    max_tokens: int,
    temperature: float,
) -> str:
    """One HTTP attempt; returns raw content or raises the ApiError taxonomy."""
    request = ModelRequest(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    response = client.generate(request)
    if response.content is None:
        tool_names = [tc.name for tc in (response.tool_calls or [])]
        raise ApiError(
            f"Model returned tool calls ({tool_names}) instead of content. "
            "This model does not support the requested output shape."
        )
    return response.content


def generate(
    registry: PromptRegistry,
    client: LmStudioClient,
    *,
    template: str,
    variables: dict[str, Any],
    validator: Callable[[Any], tuple[bool, list[str]]],
    retry_template: str | None = None,
    model: str = DEFAULT_MODEL,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
) -> Any:
    """
    Contract: run the full Guardrail Loop for one artifact type and return
    the parsed, validated data.

    The caller supplies everything that varies per artifact type — two
    registered templates and a validator — and nothing that varies between
    engines: extraction, feedback formatting, transient-error handling,
    and the typed error taxonomy live here.

    Retry templates must accept an auto-formatted `{errors}` placeholder
    (bulleted, one line per error) alongside their generate-template
    variables.

    Args:
        registry: PromptRegistry supplying `template` and `retry_template`.
        client: LmStudioClient adapter (inject a fake in tests).
        template: registered generate-template name.
        variables: placeholder values shared by both templates.
        validator: callable(parsed) -> (is_valid, errors) for the schema.
        retry_template: feedback-template name; if None, a failed first
            attempt raises immediately instead of retrying.
        model: LM Studio model id (single project-wide default).
        max_attempts: total generation attempts; validation failures AND
            retryable connection errors both consume attempts.
        max_tokens / temperature: request parameters (uniform across
            attempts).

    Returns:
        The parsed Python object (dict/list) once validation passes.

    Raises:
        SchemaValidationError: extraction/validation still failing after
            all permitted attempts; carries last errors + attempt count.
        ApiError: non-retryable errors propagate immediately; retryable
            ones consume attempts and are raised when exhausted.
    """
    def _call_and_extract(system: str, user: str) -> tuple[Any | None, list[str], Optional[ApiError]]:
        """Returns (parsed, errors, transient_exc). transient_exc carries
        the retryable ApiError when THIS attempt died on connectivity —
        callers surface it verbatim instead of masking a dead server as
        'invalid content'."""
        try:
            raw = _call_model(
                client, model, system, user,
                max_tokens=max_tokens, temperature=temperature,
            )
        except ApiError as exc:
            if not exc.retryable:
                raise
            return None, [f"transient error: {exc}"], exc
        parsed = extract_json_from_text(raw)
        if parsed is None:
            return None, ["could not extract JSON from model output"], None
        return parsed, [], None

    def _feedback_errors(errors: list[str]) -> dict[str, Any]:
        return {**variables, "errors": "\n".join(f"  - {e}" for e in errors)}

    last_errors: list[str] = []
    final_transient: Optional[ApiError] = None

    for attempt in range(1, max_attempts + 1):
        final_transient = None
        if attempt == 1:
            system, user, _ = registry.render(template, variables)
        else:
            if retry_template is None:
                raise SchemaValidationError(last_errors, 1)
            system, user, _ = registry.render(retry_template, _feedback_errors(last_errors))

        parsed, errs, transient = _call_and_extract(system, user)

        if parsed is not None:
            is_valid, validation_errors = validator(parsed)
            if is_valid:
                logger.info("Generation succeeded on attempt %d (%s)", attempt, template)
                return parsed
            errs = validation_errors
        last_errors = errs
        final_transient = transient
        logger.warning("Attempt %d failed (%s): %s", attempt, template, last_errors)

    # Every transport-level failure is NOT a schema problem: if the last
    # attempt died on connectivity/rate-limit, raise THAT so the UI can
    # say "start LM Studio" instead of blaming the model.
    if final_transient is not None:
        raise final_transient
    raise SchemaValidationError(last_errors, max_attempts)
