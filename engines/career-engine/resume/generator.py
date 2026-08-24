# engines/career-engine/resume/generator.py
#
# WHAT: Resume generation entry points — generate() turns a free-text
#       profile into a validated Resume dict; enhance() rewrites a Resume
#       toward a target role and returns it together with a
#       human-inspectable changes list.
# WHY:  Single point of contact between the career-engine and the
#       Generation Pipeline (P1.4). The Guardrail Loop lives in
#       model-layer/pipeline.py; this module contributes resume-specific
#       templates and the envelope validator. The changes list always
#       comes from the SAME validated response as the enhanced resume,
#       so inspection can never drift from the artifact (CONSTITUTION §3).
# BREAKS IF DELETED: The career-engine loses its ability to generate or
#       enhance resumes; downstream export and integrations break.

from __future__ import annotations

import json
import logging
from typing import Any

from engines.career_engine.resume.schema import RESUME_SCHEMA, validate_resume
from model_layer.client import ApiError, LmStudioClient
from model_layer.pipeline import DEFAULT_MODEL, generate as run_guardrail_loop
from model_layer.prompts import PromptRegistry
from model_layer.schema import SchemaValidationError, SchemaValidator

logger = logging.getLogger(__name__)

__all__ = ["generate", "enhance"]

# Resume prompts are tuned for shorter, more deterministic output than
# journeys (matches the metadata registered with their templates).
_RESUME_MAX_TOKENS = 2048
_RESUME_TEMPERATURE = 0.3


def generate(
    profile: str,
    *,
    client: LmStudioClient | None = None,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """
    Contract: generate a validated Resume dict from a free-text profile
    by running the Generation Pipeline.

    Args:
        profile: free-text description of the person's background.
        client: optional pre-configured LmStudioClient (or test double).
        model: model identifier passed through to LM Studio.

    Returns:
        A dict matching RESUME_SCHEMA, ready for export or enhancement.

    Raises:
        SchemaValidationError: validation failed after all attempts.
        ConnectionError / ApiError: per the pipeline error taxonomy.
    """
    result = run_guardrail_loop(
        PromptRegistry(),
        client if client is not None else LmStudioClient(),
        template="resume_generate",
        retry_template="resume_retry",
        variables={"profile": profile},
        validator=validate_resume,
        model=model,
        max_tokens=_RESUME_MAX_TOKENS,
        temperature=_RESUME_TEMPERATURE,
    )
    logger.info("Resume generated for profile: %s", profile[:50])
    return result


def enhance(
    resume: dict[str, Any],
    target_role: str,
    *,
    client: LmStudioClient | None = None,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """
    Contract: rewrite `resume` toward `target_role`, returning:

        {
            "enhanced_resume": <dict matching RESUME_SCHEMA>,
            "changes": [{"field", "change", "reason"}, ...],
        }

    The model must answer in an explicit envelope
    (`{"enhanced_resume": ..., "changes": [...]}`); the envelope is what
    the pipeline validates, so a retried response carries its own changes
    list instead of silently inheriting a stale one. If the validated
    response omits `changes`, a single explanatory default entry is
    synthesized so callers always receive an inspectable list.

    Raises:
        SchemaValidationError: envelope invalid after all attempts.
        ConnectionError / ApiError: per the pipeline error taxonomy.
    """
    def envelope_validator(parsed: Any) -> tuple[bool, list[str]]:
        if not isinstance(parsed, dict) or "enhanced_resume" not in parsed:
            return False, ["missing 'enhanced_resume' envelope in model output"]
        is_valid, errors = validate_resume(parsed["enhanced_resume"])
        if not is_valid:
            errors = [f"enhanced_resume: {e}" for e in errors]
        return is_valid, errors

    validated = run_guardrail_loop(
        PromptRegistry(),
        client if client is not None else LmStudioClient(),
        template="resume_enhance",
        retry_template="resume_enhance_retry",
        variables={
            "target_role": target_role,
            "resume": json.dumps(resume, ensure_ascii=False, indent=2),
        },
        validator=envelope_validator,
        model=model,
        max_tokens=4096,
        temperature=_RESUME_TEMPERATURE,
    )

    changes = validated.get("changes") or [{
        "field": "summary",
        "change": "Updated to reflect target role",
        "reason": f"Tailored for {target_role}",
    }]

    logger.info("Resume enhanced for role: %s", target_role[:50])
    return {
        "enhanced_resume": validated["enhanced_resume"],
        "changes": changes,
    }
