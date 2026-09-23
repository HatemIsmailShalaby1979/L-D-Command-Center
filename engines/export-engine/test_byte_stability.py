# engines/export-engine/test_byte_stability.py
#
# WHAT: Byte-stability tests — exporting the SAME artifact twice must
#       produce IDENTICAL bytes for every binary format.
# WHY:  Exit criterion E4 (deterministic exports). Timestamps embedded by
#       fpdf2 / python-docx / python-pptx / openpyxl are pinned in each
#       adapter; these tests fail if any formatter regresses to
#       wall-clock metadata.
# BREAKS IF DELETED: Non-determinism in exports would go unnoticed until
#       caching/dedup/hash features break downstream.

from __future__ import annotations

import pytest

from engines.export_engine.export import export

_SIMPLE_JOURNEY = {
    "topic": "Determinism",
    "level": "advanced",
    "cards": [
        {"id": "c1", "title": "T1", "content": "C1",
         "question": "Q1?", "options": ["a", "b"],
         "correct_option": "a", "explanation": "E1"},
        {"id": "c2", "title": "T2", "content": "C2",
         "question": "Q2?", "options": ["x", "y"],
         "correct_option": "y", "explanation": "E2"},
    ],
}

_SIMPLE_RESUME = {
    "contact": {"name": "Stable Person", "email": "s@p.io"},
    "summary": "Summary.",
    "experience": [{"title": "Eng", "company": "Co",
                    "dates": "2020-2023", "description": "Did work"}],
    "education": [{"degree": "BS", "school": "S", "dates": "2016-2020"}],
    "skills": ["A", "B"],
    "projects": [{"name": "P", "description": "D", "tech": ["t"]}],
}


def test_journey_text_stable():
    assert export(_SIMPLE_JOURNEY, format="text") == export(_SIMPLE_JOURNEY, format="text")


def test_resume_text_stable():
    assert export(_SIMPLE_RESUME, format="text") == export(_SIMPLE_RESUME, format="text")


@pytest.mark.parametrize("fmt", ["pdf", "pptx", "xlsx"])
def test_journey_binary_formats_byte_identical(fmt):
    first = export(_SIMPLE_JOURNEY, format=fmt)
    second = export(_SIMPLE_JOURNEY, format=fmt)
    assert isinstance(first, bytes) and isinstance(second, bytes)
    assert first == second


@pytest.mark.parametrize("fmt", ["pdf", "docx"])
def test_resume_binary_formats_byte_identical(fmt):
    first = export(_SIMPLE_RESUME, format=fmt)
    second = export(_SIMPLE_RESUME, format=fmt)
    assert isinstance(first, bytes) and isinstance(second, bytes)
    assert first == second
