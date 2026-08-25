# engines/test_integration.py
#
# WHAT: Integration test for the full journey pipeline:
#       topic+level → generation → rendering → export (text + PDF).
# WHY:  Ensures the three engines (journey-core, renderer, export-engine)
#       work together end-to-end. A single Journey object flows through
#       all stages without regeneration at each step.
# BREAKS IF DELETED: No end-to-end verification that the pipeline
#       contract holds between engines; regressions in the data flow
#       between stages would go undetected.

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Path setup
_ROOT = Path(__file__).resolve().parent.parent

from engines.export_engine import export as _exp
from engines.journey_core import generator as _gen
from engines.journey_core import renderer as _rend

# Also import schema for validation
from model_layer import schema as _schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_RAW_JOURNEY = (
    '{"topic": "Python Basics", "level": "beginner", '
    '"cards": ['
    '{"id": "c1", "title": "What is Python?", '
    '"content": "Python is a high-level language.", '
    '"question": "What type is Python?", '
    '"options": ["Low-level", "High-level", "Assembly", "Machine code"], '
    '"correct_option": "High-level", '
    '"explanation": "Python abstracts memory management."},'
    '{"id": "c2", "title": "Variables", '
    '"content": "Variables store data.", '
    '"question": "What do variables do?", '
    '"options": ["Compile", "Store data", "Run loops", "Connect DB"], '
    '"correct_option": "Store data", '
    '"explanation": "Variables hold references to values."}'
    ']}'
)

_MOCK_JOURNEY = {
    "topic": "Python Basics",
    "level": "beginner",
    "cards": [
        {
            "id": "c1",
            "title": "What is Python?",
            "content": "Python is a high-level language.",
            "question": "What type is Python?",
            "options": ["Low-level", "High-level", "Assembly", "Machine code"],
            "correct_option": "High-level",
            "explanation": "Python abstracts memory management.",
        },
        {
            "id": "c2",
            "title": "Variables",
            "content": "Variables store data.",
            "question": "What do variables do?",
            "options": ["Compile", "Store data", "Run loops", "Connect DB"],
            "correct_option": "Store data",
            "explanation": "Variables hold references to values.",
        },
    ],
}


def _make_mock_client(raw: str = _MOCK_RAW_JOURNEY) -> MagicMock:
    client = MagicMock()
    client.generate.return_value = SimpleNamespace(
        content=raw,
        model="local-model",
        finish_reason="stop",
        tool_calls=None,
        raw={"choices": [{"message": {"content": raw}}]},
    )
    client.is_available.return_value = True
    return client


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestFullPipelineMocked:
    """
    Full pipeline test using a mocked LM Studio client.
    Validates: generate → validate → render → export text → export PDF.
    All stages share the SAME Journey dict.
    """

    def test_full_pipeline(self, tmp_path: Path):
        """
        Contract: given topic+level, the full pipeline produces:
          1. A validated Journey dict
          2. An HTML string from the renderer
          3. A plain-text string from the export engine
          4. PDF bytes from the export engine
        All outputs derive from the SAME Journey object.
        """
        # Step 1: Generate (mocked)
        mock_client = _make_mock_client()
        journey = _gen.generate_journey(
            topic="Python Basics",
            level="beginner",
            client=mock_client,
            num_cards=2,
        )

        # Validate journey is schema-compliant
        is_valid, errors = _schema.validate_journey(journey)
        assert is_valid, f"Generated journey failed validation: {errors}"
        assert journey["topic"] == "Python Basics"
        assert journey["level"] == "beginner"
        assert len(journey["cards"]) == 2

        # Step 2: Render to HTML
        html = _rend.JourneyRenderer().render(journey)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "Python Basics" in html
        assert "What is Python?" in html
        assert "handleAnswer" in html  # JS interactivity

        # Step 3: Export to plain text
        text = _exp.export_to_plain_text(journey)
        assert "PYTHON BASICS" in text
        assert "What type is Python?" in text
        assert "Low-level" in text
        assert "Explanation: Python abstracts" in text

        # Step 4: Export to PDF
        pdf_bytes = _exp.export_to_pdf(journey)
        assert pdf_bytes[:4] == b"%PDF"
        assert b"%%EOF" in pdf_bytes

        # Step 5: Write outputs to disk
        html_path = tmp_path / "journey.html"
        text_path = tmp_path / "journey.txt"
        pdf_path = tmp_path / "journey.pdf"

        html_path.write_text(html, encoding="utf-8")
        _exp.export_to_text_file(journey, str(text_path))
        _exp.export_to_pdf_file(journey, str(pdf_path))

        assert html_path.exists()
        assert text_path.exists()
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 500  # reasonable PDF size


@pytest.mark.live
class TestFullPipelineLive:
    """
    Live integration test that actually calls LM Studio.
    Skips if LM Studio is unreachable.
    """

    def test_live_pipeline(self, tmp_path: Path):
        """
        Contract: if LM Studio is running, the full pipeline works
        end-to-end with a real model call.
        """
        client = _gen.LmStudioClient()
        if not client.is_available():
            import pytest
            pytest.skip("LM Studio is not running at localhost:1234")

        # Generate with real model
        journey = _gen.generate_journey(
            topic="Git basics",
            level="beginner",
            client=client,
            num_cards=2,
            model="qwen2.5-7b-instruct-uncensored",
        )

        # Validate
        is_valid, errors = _schema.validate_journey(journey)
        assert is_valid, f"Live generation failed validation: {errors}"

        # Render
        html = _rend.JourneyRenderer().render(journey)
        assert "<!DOCTYPE html>" in html

        # Export
        text = _exp.export_to_plain_text(journey)
        assert "GIT BASICS" in text.upper() or "GIT BASICS" in text

        pdf_bytes = _exp.export_to_pdf(journey)
        assert pdf_bytes[:4] == b"%PDF"

        # Write to disk
        (tmp_path / "live_journey.html").write_text(html)
        _exp.export_to_text_file(journey, str(tmp_path / "live_journey.txt"))
        _exp.export_to_pdf_file(journey, str(tmp_path / "live_journey.pdf"))

        assert (tmp_path / "live_journey.pdf").stat().st_size > 500
