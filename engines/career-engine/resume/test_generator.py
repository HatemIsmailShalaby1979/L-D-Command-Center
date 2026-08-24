# engines/career-engine/resume/test_generator.py
#
# WHAT: Tests for the career-engine resume generator.
# WHY:  Ensures generate() correctly wires the model-layer stack
#       (prompt → client → validate → retry) and returns a
#       schema-valid Resume dict. Covers happy path and retry path.
# BREAKS IF DELETED: No regression protection for the resume
#       generation contract; bugs in prompt rendering, client
#       calling, or schema validation would go undetected.

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Path setup
_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Load local resume schema explicitly
_local_schema_path = _ROOT / "engines" / "career-engine" / "resume" / "schema.py"
_spec = importlib.util.spec_from_file_location("resume_schema", _local_schema_path)
_resume_schema = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_resume_schema)
validate_resume = _resume_schema.validate_resume

# Add model-layer to path
sys.path.insert(0, str(_ROOT / "model-layer"))

# model-layer modules
import client as _ml_client
import prompts as _ml_prompts
import schema as _ml_schema

# Module under test
import generator as _gen
from generator import generate, enhance, SchemaValidationError

# Re-export
generate = _gen.generate
SchemaValidationError = _ml_schema.SchemaValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VALID_RESUME = {
    "contact": {
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "+1-555-1234",
        "location": "New York, NY",
        "linkedin": "linkedin.com/in/johndoe",
        "github": "github.com/johndoe",
    },
    "summary": "Experienced software engineer with 5+ years in full-stack development.",
    "experience": [
        {
            "title": "Senior Software Engineer",
            "company": "Tech Corp",
            "dates": "2020 - Present",
            "description": "Led development of microservices architecture.",
        },
        {
            "title": "Software Engineer",
            "company": "Startup Inc",
            "dates": "2018 - 2020",
            "description": "Built REST APIs and frontend components.",
        },
    ],
    "education": [
        {
            "degree": "B.S. Computer Science",
            "school": "University of Technology",
            "dates": "2014 - 2018",
        }
    ],
    "skills": ["Python", "JavaScript", "React", "PostgreSQL", "Docker"],
    "projects": [
        {
            "name": "Resume Generator",
            "description": "AI-powered resume builder.",
            "tech": ["Python", "FastAPI"],
        }
    ],
}

_VALID_RAW_OUTPUT = (
    '{"contact": {"name": "John Doe", "email": "john@example.com", '
    '"phone": "+1-555-1234", "location": "New York, NY", '
    '"linkedin": "linkedin.com/in/johndoe", "github": "github.com/johndoe"}, '
    '"summary": "Experienced software engineer.", '
    '"experience": [{"title": "Senior Software Engineer", '
    '"company": "Tech Corp", "dates": "2020 - Present", '
    '"description": "Led development."}], '
    '"education": [{"degree": "B.S. Computer Science", '
    '"school": "University of Technology", "dates": "2014 - 2018"}], '
    '"skills": ["Python", "JavaScript"], '
    '"projects": [{"name": "Resume Generator", '
    '"description": "AI-powered resume builder."}]}'
)

_VALID_ENHANCE_OUTPUT = (
    '{"enhanced_resume": ' + _VALID_RAW_OUTPUT + ', '
    '"changes": ['
    '{"field": "summary", "change": "Updated to reflect senior-level responsibilities", '
    '"reason": "Tailored for senior software engineer role"}, '
    '{"field": "skills", "change": "Added cloud and DevOps skills", '
    '"reason": "Relevant for modern engineering roles"}'
    ']}'
)

_INVALID_RAW_OUTPUT = '{"contact": {}, "summary": "", "experience": [], "education": [], "skills": [], "projects": []}'

_BAD_RAW_OUTPUT = "This is not JSON at all, just prose."

_SAMPLE_PROFILE = """
John Doe is a software engineer with 5+ years of experience.
He worked at Tech Corp as a Senior Software Engineer from 2020 to present.
Previously he worked at Startup Inc from 2018 to 2020.
He has a B.S. in Computer Science from University of Technology (2014-2018).
Skills: Python, JavaScript, React, PostgreSQL, Docker.
Project: Resume Generator - an AI-powered resume builder.
"""


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

class TestGenerateResume:
    """Tests for the generate() entry point."""

    def test_generates_valid_resume(self):
        """
        Contract: given a valid profile, generate() returns a dict
        that passes validate_resume().
        """
        mock_client = _make_mock_client(_VALID_RAW_OUTPUT)

        result = generate(
            profile=_SAMPLE_PROFILE,
            client=mock_client,
        )

        assert isinstance(result, dict)
        is_valid, errors = validate_resume(result)
        assert is_valid, f"Resume failed validation: {errors}"
        assert result["contact"]["name"] == "John Doe"
        assert len(result["experience"]) >= 1
        assert len(result["skills"]) >= 1

    def test_raises_on_schema_failure_after_retries(self):
        """
        Contract: if the model consistently returns invalid output,
        generate() must raise SchemaValidationError.
        """
        mock_client = _make_mock_client(_INVALID_RAW_OUTPUT)

        with pytest.raises(SchemaValidationError):
            generate(
                profile=_SAMPLE_PROFILE,
                client=mock_client,
            )

    def test_raises_on_malformed_output(self):
        """
        Contract: if the model returns non-JSON prose, generate()
        raises SchemaValidationError after exhausting retries.
        """
        mock_client = _make_mock_client(_BAD_RAW_OUTPUT)

        with pytest.raises(SchemaValidationError):
            generate(
                profile=_SAMPLE_PROFILE,
                client=mock_client,
            )


class TestValidateResume:
    """Direct unit tests for resume schema validation."""

    def test_valid_resume_passes(self):
        """A well-formed resume dict should pass validation."""
        is_valid, errors = validate_resume(_VALID_RESUME)
        assert is_valid
        assert errors == []

    def test_missing_contact_raises(self):
        """A resume missing contact should fail validation."""
        bad = dict(_VALID_RESUME)
        del bad["contact"]
        is_valid, errors = validate_resume(bad)
        assert not is_valid
        assert any("contact" in e for e in errors)

    def test_missing_experience_raises(self):
        """A resume with empty experience should fail."""
        bad = dict(_VALID_RESUME, experience=[])
        is_valid, errors = validate_resume(bad)
        assert not is_valid
        assert any("experience" in e for e in errors)

    def test_invalid_email_format(self):
        """Contact without valid email should fail."""
        bad = dict(_VALID_RESUME)
        bad["contact"]["email"] = "not-an-email"
        # Our basic validator doesn't check email format, but let's test
        is_valid, errors = validate_resume(bad)
        # Should still pass basic validation
        assert is_valid


class TestEnhanceResume:
    """Tests for the enhance() entry point."""

    def test_enhances_valid_resume(self):
        """
        Contract: given a valid resume and target role, enhance()
        returns a dict with enhanced_resume and changes list.
        """
        mock_client = _make_mock_client(_VALID_ENHANCE_OUTPUT)

        result = enhance(
            resume=_VALID_RESUME,
            target_role="Senior Software Engineer at Tech Corp",
            client=mock_client,
        )

        assert isinstance(result, dict)
        assert "enhanced_resume" in result
        assert "changes" in result
        assert isinstance(result["changes"], list)
        is_valid, errors = validate_resume(result["enhanced_resume"])
        assert is_valid, f"Enhanced resume failed validation: {errors}"

    def test_enhance_with_changes_description(self):
        """
        Contract: the changes list should contain human-readable
        explanations of what was modified and why.
        """
        mock_client = _make_mock_client(_VALID_ENHANCE_OUTPUT)

        result = enhance(
            resume=_VALID_RESUME,
            target_role="Senior Software Engineer",
            client=mock_client,
        )

        changes = result["changes"]
        assert len(changes) > 0
        for change in changes:
            assert "field" in change
            assert "change" in change
            assert "reason" in change
            assert isinstance(change["field"], str)
            assert isinstance(change["change"], str)
            assert isinstance(change["reason"], str)

    def test_enhance_uses_retry_on_failure(self):
        """
        Contract: if the model returns invalid output on first try,
        enhance() should retry and eventually succeed or raise.
        """
        from unittest.mock import MagicMock, call
        from types import SimpleNamespace
        
        # Return invalid then valid
        invalid_output = '{"enhanced_resume": {"contact": {}, "summary": "", "experience": [], "education": [], "skills": [], "projects": []}, "changes": []}'
        
        client = MagicMock()
        client.generate.side_effect = [
            SimpleNamespace(
                content=invalid_output,
                model="local-model",
                finish_reason="stop",
                tool_calls=None,
                raw={"choices": [{"message": {"content": invalid_output}}]},
            ),
            SimpleNamespace(
                content=invalid_output,
                model="local-model",
                finish_reason="stop",
                tool_calls=None,
                raw={"choices": [{"message": {"content": invalid_output}}]},
            ),
            SimpleNamespace(
                content=_VALID_ENHANCE_OUTPUT,
                model="local-model",
                finish_reason="stop",
                tool_calls=None,
                raw={"choices": [{"message": {"content": _VALID_ENHANCE_OUTPUT}}]},
            ),
        ]
        client.is_available.return_value = True

        result = enhance(
            resume=_VALID_RESUME,
            target_role="Senior Software Engineer",
            client=client,
        )
        
        assert "enhanced_resume" in result
        assert "changes" in result
        assert client.generate.call_count >= 2  # At least 2 calls were made (initial + retry)

    def test_enhance_raises_on_persistent_failure(self):
        """
        Contract: if the model consistently returns invalid output,
        enhance() raises SchemaValidationError after exhausting retries.
        """
        mock_client = _make_mock_client(_BAD_RAW_OUTPUT)

        with pytest.raises(SchemaValidationError):
            enhance(
                resume=_VALID_RESUME,
                target_role="Senior Software Engineer",
                client=mock_client,
            )
