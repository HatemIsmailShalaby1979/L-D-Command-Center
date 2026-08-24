# engines/career-engine/resume/generator.py
#
# WHAT: Resume generation entry point — takes a free-text profile
#       description and produces a validated Resume dict.
# WHY:  This is the single point of contact between the career-engine
#       and the model-layer. It owns the generate→validate→retry loop
#       so every caller gets a schema-valid Resume or an error.
#       Reuses the SchemaValidator from model-layer rather than
#       duplicating retry logic (CONSTITUTION.md §3).
# BREAKS IF DELETED: The career-engine loses its ability to generate
#       resumes; downstream export and platform integration break.

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Resolve paths
_ROOT = Path(__file__).resolve().parent.parent.parent
_MODEL_LAYER = _ROOT / "model-layer"

# Load local resume schema explicitly to avoid conflict with model-layer/schema
_local_schema_path = Path(__file__).parent / "schema.py"
_spec = importlib.util.spec_from_file_location("resume_schema", _local_schema_path)
_resume_schema = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_resume_schema)

RESUME_SCHEMA = _resume_schema.RESUME_SCHEMA
validate_resume = _resume_schema.validate_resume

# Add model-layer to path after local schema is loaded
sys.path.insert(0, str(_MODEL_LAYER))

# Import model-layer modules
import client as _ml_client
import prompts as _ml_prompts
import schema as _ml_schema

# Re-export for use in this module
LmStudioClient = _ml_client.LmStudioClient
ModelRequest = _ml_client.ModelRequest
ApiError = _ml_client.ApiError
SchemaValidationError = _ml_schema.SchemaValidationError
PromptRegistry = _ml_prompts.PromptRegistry
SchemaValidator = _ml_schema.SchemaValidator

# Public API
__all__ = ["generate", "enhance"]


def enhance(
    resume: dict[str, Any],
    target_role: str,
    *,
    client: LmStudioClient | None = None,
    model: str = "qwen2.5-7b-instruct-uncensored",
) -> dict[str, Any]:
    """
    Contract: enhance an existing resume for a target role.

    Takes a validated Resume dict and a target job description/role,
    calls the model to produce an enhanced resume plus a list of changes.

    Args:
        resume: a validated Resume dict (output from generate() or manual).
        target_role: description of the target role or job posting.
        client: optional pre-configured LmStudioClient.
        model: model identifier for LM Studio.

    Returns:
        A dict with:
          - "enhanced_resume": dict matching RESUME_SCHEMA
          - "changes": list of dicts with "field", "change", "reason"

    Raises:
        SchemaValidationError: if enhanced resume fails validation after retries.
        ConnectionError: if LM Studio is unreachable.
        ApiError: for other client-layer failures.
    """
    registry = PromptRegistry()
    validator = SchemaValidator(max_attempts=3)

    # Serialize resume to JSON for the prompt
    resume_json = json.dumps(resume, ensure_ascii=False, indent=2)

    # Build the retry callback
    def _retry_callback(errors: list[str]) -> str:
        errors_text = "\n".join(f"  - {e}" for e in errors)
        system, user, _ = registry.render(
            "resume_enhance_retry",
            {
                "target_role": target_role,
                "resume": resume_json,
                "errors": errors_text,
            },
        )
        raw_retry = _call_model(system, user, model, client=client)
        # Extract just the enhanced_resume from the retry response
        try:
            retry_result = json.loads(raw_retry)
            return json.dumps(retry_result.get("enhanced_resume", retry_result))
        except json.JSONDecodeError:
            return _ml_schema.extract_json_from_text(raw_retry) or raw_retry

    # First attempt: enhance the resume
    system, user, _ = registry.render(
        "resume_enhance",
        {
            "target_role": target_role,
            "resume": resume_json,
        },
    )
    raw_output = _call_model(system, user, model, client=client)

    # Parse the JSON response
    try:
        result = json.loads(raw_output)
    except json.JSONDecodeError:
        # Try to extract JSON from the response
        result = _ml_schema.extract_json_from_text(raw_output)
        if result is None:
            raise SchemaValidationError(["Invalid JSON in model response"], 1)

    # Extract enhanced resume and changes
    enhanced_resume = result.get("enhanced_resume", result)
    changes = result.get("changes", [])

    # Validate the enhanced resume
    is_valid, errors = validate_resume(enhanced_resume)
    if not is_valid and len(errors) > 0:
        # Try with retry
        enhanced_resume = validator.validate(
            json.dumps(enhanced_resume),
            schema_fn=validate_resume,
            retry_callback=_retry_callback,
        )
        is_valid, errors = validate_resume(enhanced_resume)
        if not is_valid:
            raise SchemaValidationError(errors, 3)

    # If no changes were provided, generate a default one
    if not changes:
        changes = [{
            "field": "summary",
            "change": "Updated to reflect target role",
            "reason": f"Tailored for {target_role}",
        }]

    logger.info("Resume enhanced for role: %s", target_role[:50])
    return {
        "enhanced_resume": enhanced_resume,
        "changes": changes,
    }


def generate(
    profile: str,
    *,
    client: LmStudioClient | None = None,
    model: str = "qwen2.5-7b-instruct-uncensored",
) -> dict[str, Any]:
    """
    Contract: generate a validated Resume dict from a free-text profile.

    Uses the model-layer's SchemaValidator for retry-on-failure.

    Args:
        profile: free-text description of the person's background.
        client: optional pre-configured LmStudioClient.
        model: model identifier for LM Studio.

    Returns:
        A dict matching RESUME_SCHEMA, validated and ready for export.

    Raises:
        SchemaValidationError: if validation fails after all retries.
        ConnectionError: if LM Studio is unreachable.
        ApiError: for other client-layer failures.
    """
    registry = PromptRegistry()
    validator = SchemaValidator(max_attempts=3)

    # Build the retry callback
    def _retry_callback(errors: list[str]) -> str:
        system, user, _ = registry.render(
            "resume_retry",
            {
                "profile": profile,
                "errors": "\n".join(f"  - {e}" for e in errors),
            },
        )
        return _call_model(system, user, model, client=client)

    # First attempt: generate the resume
    system, user, _ = registry.render(
        "resume_generate",
        {"profile": profile},
    )
    raw_output = _call_model(system, user, model, client=client)

    # Validate with retry on failure
    result = validator.validate(
        raw_output,
        schema_fn=validate_resume,
        retry_callback=_retry_callback,
    )

    logger.info("Resume generated for profile: %s", profile[:50])
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
    raw content string. Used internally by generate and by the retry
    callback.
    """
    if client is None:
        client = LmStudioClient()

    request = ModelRequest(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=2048,
        temperature=0.3,
    )
    response = client.generate(request)

    if response.content is None:
        tool_names = [tc.name for tc in (response.tool_calls or [])]
        raise ApiError(
            f"Model returned tool calls ({tool_names}) instead of content."
        )

    return response.content
