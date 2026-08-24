# model-layer/schema.py
#
# WHAT: Schema-validation layer for LM Studio model outputs.
#       Validates that generated JSON or structured text conforms to
#       a known schema before the caller uses it. Retries on failure
#       according to the retry policy defined here.
# WHY:  CONSTITUTION.md §3 mandates schema-validated model outputs
#       with retry-on-failure instead of best-effort parsing. This
#       module enforces that discipline at the model-layer boundary,
#       so every upstream engine (journey-core, export-engine, etc.)
#       receives outputs it can trust.
# BREAKS IF DELETED: Model outputs flow unchecked into every engine,
#       violating the guardrail philosophy and risking silent
#       corruption of generated journeys, exports, and podcasts.

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Journey schema definition
# ---------------------------------------------------------------------------

JOURNEY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["topic", "level", "cards"],
    "properties": {
        "topic": {"type": "string", "minLength": 1},
        "level": {
            "type": "string",
            "enum": ["beginner", "intermediate", "advanced"],
        },
        "cards": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "title",
                    "content",
                    "question",
                    "options",
                    "correct_option",
                    "explanation",
                ],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "title": {"type": "string", "minLength": 1},
                    "content": {"type": "string", "minLength": 1},
                    "question": {"type": "string", "minLength": 1},
                    "options": {
                        "type": "array",
                        "minItems": 2,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "correct_option": {
                        "oneOf": [
                            {"type": "string", "minLength": 1},
                            {"type": "integer", "ge": 0},
                        ],
                    },
                    "explanation": {"type": "string", "minLength": 1},
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _check_type(value: Any, expected: str, path: str) -> list[str]:
    """Return a list of error strings for type mismatches."""
    errors: list[str] = []
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    if expected in type_map and not isinstance(value, type_map[expected]):
        errors.append(f"{path}: expected {expected}, got {type(value).__name__}")
    return errors


def _validate_object(obj: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Recursively validate obj against a JSON Schema subset."""
    errors: list[str] = []

    # Type check
    expected_type = schema.get("type")
    if expected_type:
        errors.extend(_check_type(obj, expected_type, path))
        if errors:
            return errors  # skip further checks if type is wrong

    # Enum check
    if "enum" in schema:
        if obj not in schema["enum"]:
            errors.append(f"{path}: value {obj!r} not in enum {schema['enum']}")

    # Object properties
    if expected_type == "object" and isinstance(obj, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in obj:
                errors.append(f"{path}: missing required field '{key}'")
        props = schema.get("properties", {})
        for key, value in obj.items():
            if key in props:
                errors.extend(_validate_object(value, props[key], f"{path}.{key}"))
        if schema.get("additionalProperties") is False:
            unknown = set(obj.keys()) - set(props.keys())
            for key in unknown:
                errors.append(f"{path}: unexpected field '{key}'")

    # Array items
    if expected_type == "array" and isinstance(obj, list):
        min_items = schema.get("minItems", 0)
        if len(obj) < min_items:
            errors.append(f"{path}: array has {len(obj)} items, minimum is {min_items}")
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(obj):
                errors.extend(_validate_object(item, items_schema, f"{path}[{i}]"))

    # String constraints
    if expected_type == "string" and isinstance(obj, str):
        min_len = schema.get("minLength")
        if min_len is not None and len(obj) < min_len:
            errors.append(f"{path}: string length {len(obj)} < minLength {min_len}")

    # Number constraints
    if expected_type in ("integer", "number") and isinstance(obj, (int, float)):
        ge = schema.get("ge")
        if ge is not None and obj < ge:
            errors.append(f"{path}: value {obj} < ge {ge}")

    return errors


def validate_journey(raw: Any) -> tuple[bool, list[str]]:
    """
    Contract: validate a parsed journey dict against JOURNEY_SCHEMA.

    Args:
        raw: the parsed Python object (dict/list/str/etc.) from the model.

    Returns:
        (is_valid, errors) — errors is empty when valid.
    """
    if not isinstance(raw, dict):
        return False, [f"expected a JSON object at top level, got {type(raw).__name__}"]
    errors = _validate_object(raw, JOURNEY_SCHEMA, "$")
    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """
    Contract: the canonical result of a schema-validation pass.

    Fields:
      - valid: True if the input conforms to the schema, False otherwise.
      - data: the parsed data if valid; None if invalid.
      - errors: list of human-readable error strings (empty when valid).
      - attempt: which retry attempt produced this result (1-indexed).
    """
    valid: bool
    data: Optional[Any]
    errors: list[str]
    attempt: int


# ---------------------------------------------------------------------------
# Validation error
# ---------------------------------------------------------------------------

class SchemaValidationError(Exception):
    """
    Contract: raised when schema validation fails after exhausting all
    retry attempts. Contains the list of errors so the caller can
    decide whether to surface them to the user or fall back.
    """

    def __init__(self, errors: list[str], attempt: int) -> None:
        self.errors = errors
        self.attempt = attempt
        super().__init__(
            f"Schema validation failed after {attempt} attempt(s): {'; '.join(errors)}"
        )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class SchemaValidator:
    """
    Contract: validates model outputs against a schema and retries on
    failure according to a configurable policy.

    The schema is expressed as a callable that returns (valid, errors).
    This avoids hard dependency on a specific validation library while
    remaining swappable.

    Responsibilities:
      - Accept a schema predicate and raw output string/bytes
      - Parse and validate on each attempt
      - Re-prompt the model on failure via the retry callback
      - Raise SchemaValidationError after max_attempts is exhausted

    Non-responsibilities:
      - Rendering prompts (handled by prompts.py)
      - HTTP communication (handled by client.py)
      - Business-logic interpretation of the validated data
    """

    def __init__(self, max_attempts: int = 3) -> None:
        """
        Args:
            max_attempts: how many times to retry before raising.
        """
        self.max_attempts = max_attempts

    def validate(
        self,
        raw_output: str,
        schema_fn,
        retry_callback=None,
    ):
        """
        Contract: validate raw_output against schema_fn, retry via
        retry_callback on failure, return parsed data on success.

        Args:
            raw_output: the raw model output string (may contain JSON
                        or other structured text).
            schema_fn: a callable taking the parsed data and returning
                       (is_valid: bool, errors: list[str]).
            retry_callback: if provided, called with the previous errors
                            to obtain a fresh raw_output on each failure.
                            If None, SchemaValidationError is raised
                            after the first failure.

        Returns:
            The parsed data object when validation succeeds.

        Raises:
            SchemaValidationError: if validation fails after all
                                   retry attempts are exhausted.
        """
        last_errors = []
        for attempt in range(1, self.max_attempts + 1):
            parsed = extract_json_from_text(raw_output)
            if parsed is None:
                last_errors = [f"Attempt {attempt}: could not extract JSON from model output"]
                logger.warning("Schema validation failed (attempt %d): %s", attempt, last_errors)
                if retry_callback is None:
                    break
                raw_output = retry_callback(last_errors)
                continue

            is_valid, errors = schema_fn(parsed)
            if is_valid:
                logger.info("Schema validation passed on attempt %d", attempt)
                return parsed

            last_errors = errors
            logger.warning(
                "Schema validation failed (attempt %d): %s",
                attempt,
                errors,
            )
            if retry_callback is None:
                break
            raw_output = retry_callback(last_errors)

        raise SchemaValidationError(last_errors, self.max_attempts)


# ---------------------------------------------------------------------------
# JSON extractor
# ---------------------------------------------------------------------------

def extract_json_from_text(text: str) -> Optional[dict | list]:
    """
    Contract: given a raw model output that may contain JSON embedded
    in prose, extract the outermost valid JSON object or array string.

    Strategy:
      1. Try parsing the whole string as JSON first (fast path).
      2. If that fails, scan for the first '{' or '[' and use
         bracket-counting to find the matching close, then try
         parsing the extracted substring.
      3. Fall back to None if no valid JSON is found.

    Returns:
        The parsed dict or list, or None if no valid JSON is found.
    """
    if not text or not isinstance(text, str):
        return None

    # Fast path: the whole string is valid JSON
    text = text.strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Slow path: find the first structural character and extract
    for start_char, end_char in (("{", "}"), ("[", "]")):
        start_idx = text.find(start_char)
        if start_idx == -1:
            continue
        depth = 0
        for i in range(start_idx, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
                if depth == 0:
                    snippet = text[start_idx: i + 1]
                    try:
                        return json.loads(snippet)
                    except (json.JSONDecodeError, ValueError):
                        continue
    return None
