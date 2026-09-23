# engines/career-engine/resume/schema.py
#
# WHAT: Resume data contract — RESUME_SCHEMA plus validate_resume().
# WHY:  CONSTITUTION.md §3 requires schema-validated model outputs. Since
#       P1.4 the validator is DRIVEN BY the schema via the model-layer
#       JSON-schema engine, so the declared contract and the enforced one
#       cannot drift (the previous hand-rolled copy had a dead contact
#       required-check and never consulted RESUME_SCHEMA at all).
# BREAKS IF DELETED: The career-engine loses its data contract; model
#       outputs would flow unchecked into export and integrations.

from __future__ import annotations

import json
from typing import Any

from model_layer.schema import _validate_object

# ---------------------------------------------------------------------------
# Resume schema definition
# ---------------------------------------------------------------------------

RESUME_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["contact", "summary", "experience", "education", "skills", "projects"],
    "properties": {
        "contact": {
            "type": "object",
            "required": ["name", "email"],
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "email": {"type": "string", "format": "email"},
                "phone": {"type": "string"},
                "location": {"type": "string"},
                "linkedin": {"type": "string"},
                "github": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "summary": {
            "type": "string",
            "minLength": 1,
        },
        "experience": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["title", "company", "dates", "description"],
                "properties": {
                    "title": {"type": "string", "minLength": 1},
                    "company": {"type": "string", "minLength": 1},
                    "dates": {"type": "string", "minLength": 1},
                    "description": {"type": "string", "minLength": 1},
                },
                "additionalProperties": False,
            },
        },
        "education": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["degree", "school", "dates"],
                "properties": {
                    "degree": {"type": "string", "minLength": 1},
                    "school": {"type": "string", "minLength": 1},
                    "dates": {"type": "string", "minLength": 1},
                },
                "additionalProperties": False,
            },
        },
        "skills": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "string",
                "minLength": 1,
            },
        },
        "projects": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["name", "description"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "description": {"type": "string", "minLength": 1},
                    "tech": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_resume(raw: Any) -> tuple[bool, list[str]]:
    """
    Contract: validate a raw resume dict (or JSON string) against
    RESUME_SCHEMA, using the model-layer's JSON-schema engine so the
    declared schema is the single source of truth.

    Args:
        raw: the parsed output from the model, or a JSON string.

    Returns:
        A tuple of (is_valid: bool, errors: list[str]).
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return False, ["Invalid JSON"]

    if not isinstance(raw, dict):
        return False, ["Expected a JSON object"]

    errors = _validate_object(raw, RESUME_SCHEMA, "$")
    return not errors, errors


# ---------------------------------------------------------------------------
# Re-export for convenience
# ---------------------------------------------------------------------------

__all__ = ["RESUME_SCHEMA", "validate_resume"]
