# engines/journey-core/test_generator.py
#
# WHAT: Tests for the journey-core generator module.
# WHY:  Ensures generate_journey() correctly wires the model-layer
#       stack (prompt -> client -> validate -> retry) and returns a
#       schema-valid Journey dict. Covers happy path and retry path.
# BREAKS IF DELETED: No regression protection for the core generation
#       contract; bugs in prompt rendering, client calling, or schema
#       validation would go undetected.

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

# ------------------------------------------------------------------
# Path setup — must run BEFORE any project imports.
#
# The directory is named "journey-core" (hyphenated) which is NOT a
# valid Python package name, so we import generator.py directly as a
# module from its directory.
# ------------------------------------------------------------------
from engines.journey_core import generator as _journey_gen
from model_layer import client as _ml_client
from model_layer import prompts as _ml_prompts
from model_layer import schema as _ml_schema

import pytest

# Re-export for test use
generate_journey = _journey_gen.generate_journey
DEFAULT_NUM_CARDS = _journey_gen.DEFAULT_NUM_CARDS
validate_journey = _ml_schema.validate_journey
SchemaValidationError = _ml_schema.SchemaValidationError
ApiError = _ml_client.ApiError
LmStudioClient = _ml_client.LmStudioClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VALID_JOURNEY = {
    "topic": "Python basics",
    "level": "beginner",
    "cards": [
        {
            "id": "card-1",
            "title": "What is Python?",
            "content": "Python is a high-level programming language.",
            "question": "What type of language is Python?",
            "options": ["Low-level", "High-level", "Assembly", "Machine code"],
            "correct_option": "High-level",
            "explanation": "Python abstracts away memory management and hardware details.",
        }
    ],
}

_VALID_RAW_OUTPUT = (
    '{"topic": "Python basics", "level": "beginner", '
    '"cards": [{"id": "card-1", "title": "What is Python?", '
    '"content": "Python is a high-level programming language.", '
    '"question": "What type of language is Python?", '
    '"options": ["Low-level", "High-level", "Assembly", "Machine code"], '
    '"correct_option": "High-level", '
    '"explanation": "Python abstracts away memory management and hardware details."}]}'
)

_INVALID_RAW_OUTPUT = '{"topic": "Python basics", "level": "beginner", "cards": []}'

_BAD_RAW_OUTPUT = "This is not JSON at all, just prose."


def _make_mock_client(raw_response: str) -> MagicMock:
    """Build a mock LmStudioClient that returns the given raw string."""
    client = MagicMock()
    client.generate.return_value = SimpleNamespace(
        content=raw_response,
        model="local-model",
        finish_reason="stop",
        tool_calls=None,
        raw={"choices": [{"message": {"content": raw_response}}]},
    )
    client.is_available.return_value = True
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGenerateJourney:
    """Tests for the generate_journey() entry point."""

    def test_generates_valid_journey(self):
        """
        Contract: given a valid topic and level, generate_journey()
        returns a dict that passes validate_journey().
        """
        mock_client = _make_mock_client(_VALID_RAW_OUTPUT)

        result = generate_journey(
            topic="Python basics",
            level="beginner",
            client=mock_client,
        )

        assert isinstance(result, dict)
        is_valid, errors = validate_journey(result)
        assert is_valid, f"Journey failed validation: {errors}"
        assert result["topic"] == "Python basics"
        assert result["level"] == "beginner"
        assert len(result["cards"]) == 1
        assert result["cards"][0]["id"] == "card-1"

    def test_raises_on_schema_failure_after_retries(self):
        """
        Contract: if the model consistently returns invalid output,
        generate_journey() must raise SchemaValidationError, not
        silently return malformed data (CONSTITUTION.md §3).
        """
        mock_client = _make_mock_client(_INVALID_RAW_OUTPUT)

        with pytest.raises(SchemaValidationError):
            generate_journey(
                topic="Python basics",
                level="beginner",
                client=mock_client,
            )

    def test_raises_on_malformed_output(self):
        """
        Contract: if the model returns non-JSON prose, generate_journey()
        raises SchemaValidationError after exhausting retries.
        """
        mock_client = _make_mock_client(_BAD_RAW_OUTPUT)

        with pytest.raises(SchemaValidationError):
            generate_journey(
                topic="Python basics",
                level="beginner",
                client=mock_client,
            )

    def test_invalid_level_raises_valueerror(self):
        """
        Contract: passing an invalid level value raises ValueError
        before any model call is made.
        """
        mock_client = _make_mock_client(_VALID_RAW_OUTPUT)

        with pytest.raises(ValueError, match="Invalid level"):
            generate_journey(
                topic="Python basics",
                level="expert",
                client=mock_client,
            )

    def test_default_client_used_when_none_provided(self):
        """
        Contract: when no client is passed, generate_journey() creates
        a default LmStudioClient pointing at localhost:1234.
        """
        with patch.object(_journey_gen, "LmStudioClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.generate.return_value = SimpleNamespace(
                content=_VALID_RAW_OUTPUT,
                model="local-model",
                finish_reason="stop",
                tool_calls=None,
                raw={"choices": [{"message": {"content": _VALID_RAW_OUTPUT}}]},
            )
            MockClient.return_value = mock_instance

            generate_journey(topic="Test topic", level="intermediate")

            MockClient.assert_called_once_with()
            mock_instance.generate.assert_called_once()

    def test_custom_num_cards(self):
        """
        Contract: the num_cards parameter is passed through to the
        prompt template variables.
        """
        captured_messages = []

        def capture_generate(request):
            captured_messages.append(request.messages)
            return SimpleNamespace(
                content=_VALID_RAW_OUTPUT,
                model="local-model",
                finish_reason="stop",
                tool_calls=None,
                raw={"choices": [{"message": {"content": _VALID_RAW_OUTPUT}}]},
            )

        mock_client = MagicMock()
        mock_client.generate = capture_generate

        generate_journey(
            topic="Test topic",
            level="advanced",
            client=mock_client,
            num_cards=7,
        )

        assert len(captured_messages) == 1
        user_msg = captured_messages[0][1]["content"]
        assert "7" in user_msg


class TestValidateJourney:
    """Direct unit tests for the schema validation contract."""

    def test_valid_journey_passes(self):
        """A well-formed journey dict should pass validation."""
        is_valid, errors = validate_journey(_VALID_JOURNEY)
        assert is_valid
        assert errors == []

    def test_empty_cards_fails(self):
        """A journey with zero cards must fail validation."""
        bad = dict(_VALID_JOURNEY, cards=[])
        is_valid, errors = validate_journey(bad)
        assert not is_valid
        assert any("cards" in e for e in errors)

    def test_missing_required_field_fails(self):
        """A journey missing a required card field must fail."""
        bad = dict(_VALID_JOURNEY, cards=[dict(_VALID_JOURNEY["cards"][0])])
        del bad["cards"][0]["explanation"]
        is_valid, errors = validate_journey(bad)
        assert not is_valid
        assert any("explanation" in e for e in errors)

    def test_wrong_level_fails(self):
        """A journey with an invalid level enum must fail."""
        bad = dict(_VALID_JOURNEY, level="expert")
        is_valid, errors = validate_journey(bad)
        assert not is_valid
        assert any("level" in e for e in errors)
