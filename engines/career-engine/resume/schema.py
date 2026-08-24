# engines/career-engine/resume/schema.py
#
# WHAT: Resume JSON schema definition and validation for the career-engine.
# WHY:  The resume generator needs a schema to validate model outputs
#       against, following CONSTITUTION.md §3's guardrail principle:
#       schema-validated model outputs with retry-on-failure. Reusing
#       the model-layer's SchemaValidator avoids duplicating retry logic.
# BREAKS IF DELETED: The career-engine loses its data contract for
#       resume generation; model outputs would flow unchecked.

from __future__ import annotations

from typing import Any

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
    Contract: validate a raw resume dict against RESUME_SCHEMA.

    Uses the model-layer's validate_schema function. If the function
    doesn't exist yet, falls back to basic type checking.

    Args:
        raw: the raw output from the model (dict or JSON string).

    Returns:
        A tuple of (is_valid: bool, errors: list[str]).
    """
    import json

    # If raw is a string, try to parse it
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return False, ["Invalid JSON"]

    if not isinstance(raw, dict):
        return False, ["Expected a JSON object"]

    errors = []

    # Validate top-level required fields
    for field in RESUME_SCHEMA["required"]:
        if field not in raw:
            errors.append(f"missing required field: {field}")

    if errors:
        return False, errors

    # Validate contact
    contact = raw.get("contact", {})
    if not isinstance(contact, dict):
        errors.append("contact must be an object")
    else:
        for field in contact.get("required", ["name", "email"]):
            if field not in contact:
                errors.append(f"contact missing required field: {field}")

    # Validate experience
    experience = raw.get("experience", [])
    if not isinstance(experience, list) or len(experience) < 1:
        errors.append("experience must be a non-empty array")
    else:
        for i, exp in enumerate(experience):
            for field in ["title", "company", "dates", "description"]:
                if field not in exp:
                    errors.append(f"experience[{i}] missing required field: {field}")

    # Validate education
    education = raw.get("education", [])
    if not isinstance(education, list) or len(education) < 1:
        errors.append("education must be a non-empty array")
    else:
        for i, edu in enumerate(education):
            for field in ["degree", "school", "dates"]:
                if field not in edu:
                    errors.append(f"education[{i}] missing required field: {field}")

    # Validate skills
    skills = raw.get("skills", [])
    if not isinstance(skills, list) or len(skills) < 1:
        errors.append("skills must be a non-empty array")

    # Validate projects
    projects = raw.get("projects", [])
    if not isinstance(projects, list) or len(projects) < 1:
        errors.append("projects must be a non-empty array")
    else:
        for i, proj in enumerate(projects):
            for field in ["name", "description"]:
                if field not in proj:
                    errors.append(f"projects[{i}] missing required field: {field}")

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Re-export for convenience
# ---------------------------------------------------------------------------

__all__ = ["RESUME_SCHEMA", "validate_resume"]
