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
#       2026-09-05 hardening (owner directive: 7B-14B models must never
#       hit a format wall): 8192-token default budget, truncation repair
#       via finish_reason, JSON mode with runtime fallback, and the
#       JSON-discipline addendum from policy.py injected into every call.
# BREAKS IF DELETED: Each engine falls back to its own loop; retry policy,
#       JSON extraction, error taxonomy, and model defaults drift apart
#       again, and the broken un-mocked paths return.

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from model_layer.client import ApiError, LmStudioClient, ModelRequest
from model_layer.policy import policy_for
from model_layer.prompts import PromptRegistry
from model_layer.schema import (
    SchemaValidationError,
    extract_json_from_text,
    repair_truncated_json,
)

logger = logging.getLogger(__name__)

# One policy for every engine — no more per-module default model ids.
DEFAULT_MODEL = "local-model"
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_ATTEMPTS = 3

_JSON_MODE_REJECT_HINTS = (
    "response_format", "grammar", "structured output", "json_schema",
    "json_object", "unsupported", "not supported",
)


def _call_model(
    client: LmStudioClient,
    model: str,
    system: str,
    user: str,
    *,
    max_tokens: int,
    temperature: float,
    json_mode: bool,
) -> tuple[str, Optional[str]]:
    """One HTTP attempt; returns (raw content, finish_reason) or raises
    the ApiError taxonomy. json_mode asks the runtime to constrain the
    output to JSON (LM Studio structured output) when supported."""
    request = ModelRequest(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if json_mode:
        request.extra["response_format"] = {"type": "json_object"}
    response = client.generate(request)
    if response.content is None:
        tool_names = [tc.name for tc in (response.tool_calls or [])]
        raise ApiError(
            f"Model returned tool calls ({tool_names}) instead of content. "
            "This model does not support the requested output shape."
        )
    return response.content, response.finish_reason


def _wants_json_mode_fallback(exc: ApiError) -> bool:
    """Contract: True when the API error looks like 'this runtime/model
    rejects response_format' — a capability mismatch, not bad content.
    Retrying without the field is correct; consuming an attempt is not."""
    if getattr(exc, "status_code", None) not in (400, 404, 422, 501):
        return False
    text = str(exc).lower()
    return any(hint in text for hint in _JSON_MODE_REJECT_HINTS)


def generate(
    registry: PromptRegistry,
    client: LmStudioClient,
    *,
    template: str,
    variables: dict[str, Any],
    validator: Callable[[Any], tuple[bool, list[str]]],
    retry_template: str | None = None,
    model: str = DEFAULT_MODEL,
    max_attempts: int | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    system_addendum: str | None = None,
) -> Any:
    """
    Contract: run the full Guardrail Loop for one artifact type and return
    the parsed, validated data.

    The caller supplies everything that varies per artifact type — two
    registered templates and a validator — and nothing that varies between
    engines: extraction, feedback formatting, truncation repair,
    transient-error handling, JSON-mode fallback, and the typed error
    taxonomy live here.

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
        max_attempts: total generation attempts; None = policy decides
            (small models get a bigger budget). Validation failures AND
            retryable connection errors both consume attempts.
        max_tokens / temperature: request parameters (uniform across
            attempts).
        system_addendum: extra discipline text appended to every system
            prompt; None = policy default (JSON discipline).

    Returns:
        The parsed Python object (dict/list) once validation passes.

    Raises:
        SchemaValidationError: extraction/validation still failing after
            all permitted attempts; carries last errors + attempt count.
        ApiError: non-retryable errors propagate immediately; retryable
            ones consume attempts and are raised when exhausted.
    """
    policy = policy_for(model)
    if max_attempts is None:
        max_attempts = policy["max_attempts"]
    addendum = (policy["system_addendum"] if system_addendum is None
                else system_addendum)
    json_mode = bool(policy["json_mode"])
    rendered_system: str = ""
    rendered_user: str = ""

    def _call_and_extract(system: str, user: str,
                          temperature: float) -> tuple[
            Any | None, list[str], Optional[ApiError]]:
        """Returns (parsed, errors, transient_exc). transient_exc carries
        the retryable ApiError when THIS attempt died on connectivity —
        callers surface it verbatim instead of masking a dead server as
        'invalid content'."""
        try:
            raw, finish_reason = _call_model(
                client, model, system, user,
                max_tokens=max_tokens, temperature=temperature,
                json_mode=json_mode,
            )
        except ApiError as exc:
            if json_mode and _wants_json_mode_fallback(exc):
                logger.info("Runtime rejected response_format; disabling "
                            "JSON mode and retrying without it")
                return _SIGNAL_JSON_MODE_FALLBACK, [], None
            if not exc.retryable:
                raise
            return None, [f"transient error: {exc}"], exc
        parsed = extract_json_from_text(raw)
        if parsed is None and finish_reason == "length":
            # Output was cut by the token limit mid-JSON — salvage the
            # complete members instead of failing the attempt.
            parsed = repair_truncated_json(raw)
            if parsed is not None:
                logger.warning("Output truncated at token limit; repaired "
                               "salvage accepted for validation")
        if parsed is None:
            if finish_reason == "length":
                return None, ["output was cut off by the token limit "
                              "before the JSON completed — make every "
                              "field much shorter and finish the JSON "
                              "within the budget"], None
            return None, ["could not extract JSON from model output "
                          "(remove all prose, fences, and reasoning "
                          "blocks; reply with the JSON object only)"], None
        return parsed, [], None

    _SIGNAL_JSON_MODE_FALLBACK = object()

    last_errors: list[str] = []
    final_transient: Optional[ApiError] = None

    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        final_transient = None
        if attempt == 1:
            system, user, _ = registry.render(template, variables)
        else:
            if retry_template is None:
                raise SchemaValidationError(last_errors, 1)
            system, user, _ = registry.render(
                retry_template, _feedback_errors(last_errors, variables))

        rendered_system, rendered_user = system, user
        if addendum:
            rendered_system = system.rstrip() + "\n\n" + addendum
        if attempt > 1:
            # Retry diversity: the previous attempt burned a full
            # budget (usually deliberating, not answering). Restate
            # the urgency AND re-roll the sampling trajectory —
            # temperature climbs each retry so a loop replay becomes
            # increasingly unlikely instead of replaying the same
            # failure at the same setting.
            rendered_user = rendered_user.rstrip() + "\n\n" + (
                "Begin the corrected JSON immediately (no preamble), "
                "write EVERY field completely with real content — "
                "empty strings fail — then stop.")
            attempt_temperature = min(1.0, temperature + 0.15
                                      * (attempt - 1))
        else:
            attempt_temperature = temperature

        parsed, errs, transient = _call_and_extract(
            rendered_system, rendered_user, attempt_temperature)

        if parsed is _SIGNAL_JSON_MODE_FALLBACK:
            json_mode = False
            attempt -= 1  # capability mismatch: attempt not consumed
            continue

        if parsed is not None:
            is_valid, validation_errors = validator(parsed)
            if is_valid:
                logger.info("Generation succeeded on attempt %d (%s)",
                            attempt, template)
                return parsed
            errs = validation_errors
        last_errors = errs
        final_transient = transient
        logger.warning("Attempt %d failed (%s): %s", attempt, template,
                       last_errors)

    # Every transport-level failure is NOT a schema problem: if the last
    # attempt died on connectivity/rate-limit, raise THAT so the UI can
    # say "start LM Studio" instead of blaming the model.
    if final_transient is not None:
        raise final_transient
    raise SchemaValidationError(last_errors, max_attempts)


def _feedback_errors(errors: list[str],
                     variables: dict[str, Any]) -> dict[str, Any]:
    return {**variables, "errors": "\n".join(f"  - {e}" for e in errors)}
