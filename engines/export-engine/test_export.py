# engines/export-engine/test_export.py
#
# WHAT: Tests for the export-engine plain-text and PDF export.
# WHY:  Ensures export functions produce correct, deterministic output
#       for both Journey and Resume dicts. Tests are pure (no model, no
#       I/O except writing to in-memory BytesIO for PDF/DOCX).
# BREAKS IF DELETED: No regression protection for the export contract;
#       broken plain-text, PDF, or DOCX output would go undetected.

from __future__ import annotations

import sys
from io import BytesIO

import pytest

from engines.export_engine import export as _export_mod

export_to_plain_text = _export_mod.export_to_plain_text
export_to_pdf = _export_mod.export_to_pdf
export_resume_to_plain_text = _export_mod.export_resume_to_plain_text
export_resume_to_pdf = _export_mod.export_resume_to_pdf
export_resume_to_docx = _export_mod.export_resume_to_docx
export = _export_mod.export
_detect_type = _export_mod._detect_type


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SIMPLE_JOURNEY = {
    "topic": "Python Basics",
    "level": "beginner",
    "cards": [
        {
            "id": "card-1",
            "title": "What is Python?",
            "content": "Python is a high-level programming language.",
            "question": "What type of language is Python?",
            "options": ["Low-level", "High-level", "Assembly", "Machine code"],
            "correct_option": "High-level",
            "explanation": "Python abstracts away memory management.",
        }
    ],
}

_MULTI_CARD_JOURNEY = {
    "topic": "Networking",
    "level": "intermediate",
    "cards": [
        {
            "id": "c1",
            "title": "OSI Model",
            "content": "The OSI model has 7 layers.",
            "question": "How many layers in OSI?",
            "options": ["3", "5", "7", "10"],
            "correct_option": "7",
            "explanation": "Physical, Data Link, Network, Transport, Session, Presentation, Application.",
        },
        {
            "id": "c2",
            "title": "TCP/IP",
            "content": "TCP is a connection-oriented protocol.",
            "question": "What kind of protocol is TCP?",
            "options": ["Connectionless", "Connection-oriented", "Best-effort", "Unreliable"],
            "correct_option": "Connection-oriented",
            "explanation": "TCP establishes a reliable connection before data transfer.",
        },
    ],
}

_SIMPLE_RESUME = {
    "contact": {
        "name": "John Smith",
        "email": "john@example.com",
        "phone": "+1-555-1234",
        "location": "New York, NY",
        "linkedin": "https://linkedin.com/in/johnsmith",
        "github": "https://github.com/johnsmith",
    },
    "summary": "Experienced software engineer with 5+ years in Python and machine learning.",
    "experience": [
        {
            "title": "Software Engineer",
            "company": "Tech Corp",
            "dates": "2020-2023",
            "description": "- Led development of ML pipeline\n- Improved model accuracy by 15%",
        },
        {
            "title": "Junior Developer",
            "company": "Startup Inc",
            "dates": "2018-2020",
            "description": "- Built REST APIs with Flask\n- Integrated payment systems",
        },
    ],
    "education": [
        {
            "degree": "B.S. Computer Science",
            "school": "State University",
            "dates": "2014-2018",
        }
    ],
    "skills": ["Python", "Machine Learning", "Flask", "PostgreSQL", "Docker"],
    "projects": [
        {
            "name": "ML Pipeline",
            "description": "Automated data processing pipeline",
            "tech": ["Python", "TensorFlow", "Airflow"],
        },
        {
            "name": "Inventory System",
            "description": "Full-stack inventory management",
            "tech": ["React", "Node.js", "PostgreSQL"],
        },
    ],
}


# ---------------------------------------------------------------------------
# Type detection tests
# ---------------------------------------------------------------------------

class TestDetectType:
    """Tests for _detect_type() function."""

    def test_detects_journey(self):
        assert _detect_type(_SIMPLE_JOURNEY) == "journey"

    def test_detects_resume(self):
        assert _detect_type(_SIMPLE_RESUME) == "resume"

    def test_detects_unknown(self):
        assert _detect_type({"foo": "bar"}) == "unknown"


# ---------------------------------------------------------------------------
# Plain-text tests
# ---------------------------------------------------------------------------

class TestExportPlainText:
    """Tests for export_to_plain_text()."""

    def test_returns_string(self):
        result = export_to_plain_text(_SIMPLE_JOURNEY)
        assert isinstance(result, str)

    def test_includes_topic_and_level(self):
        result = export_to_plain_text(_SIMPLE_JOURNEY)
        assert "PYTHON BASICS" in result.upper()
        assert "BEGINNER" in result

    def test_includes_all_cards(self):
        result = export_to_plain_text(_MULTI_CARD_JOURNEY)
        assert "OSI MODEL" in result.upper()
        assert "TCP/IP" in result.upper()
        assert "Card 1" in result
        assert "Card 2" in result

    def test_includes_questions_and_options(self):
        result = export_to_plain_text(_SIMPLE_JOURNEY)
        assert "What type of language is Python?" in result
        assert "A) Low-level" in result
        assert "B) High-level" in result
        assert "C) Assembly" in result
        assert "D) Machine code" in result

    def test_includes_correct_and_explanation(self):
        result = export_to_plain_text(_SIMPLE_JOURNEY)
        assert "Correct: High-level" in result
        assert "Explanation: Python abstracts away memory management." in result

    def test_missing_topic_raises(self):
        bad = dict(_SIMPLE_JOURNEY)
        del bad["topic"]
        with pytest.raises(ValueError, match="topic"):
            export_to_plain_text(bad)

    def test_missing_cards_raises(self):
        bad = dict(_SIMPLE_JOURNEY, cards=[])
        with pytest.raises(ValueError, match="at least one card"):
            export_to_plain_text(bad)

    def test_multi_card_separator(self):
        result = export_to_plain_text(_MULTI_CARD_JOURNEY)
        assert "---" in result
        # Should have two separators (one after each card)
        assert result.count("---") >= 2


# ---------------------------------------------------------------------------
# Resume plain-text tests
# ---------------------------------------------------------------------------

class TestExportResumePlainText:
    """Tests for export_resume_to_plain_text()."""

    def test_returns_string(self):
        result = export_resume_to_plain_text(_SIMPLE_RESUME)
        assert isinstance(result, str)

    def test_includes_name(self):
        result = export_resume_to_plain_text(_SIMPLE_RESUME)
        assert "JOHN SMITH" in result.upper()

    def test_includes_contact_info(self):
        result = export_resume_to_plain_text(_SIMPLE_RESUME)
        assert "john@example.com" in result
        assert "+1-555-1234" in result
        assert "New York, NY" in result

    def test_includes_summary(self):
        result = export_resume_to_plain_text(_SIMPLE_RESUME)
        assert "SUMMARY" in result
        assert "software engineer" in result.lower()

    def test_includes_experience(self):
        result = export_resume_to_plain_text(_SIMPLE_RESUME)
        assert "EXPERIENCE" in result
        assert "Software Engineer" in result
        assert "Tech Corp" in result
        assert "Junior Developer" in result
        assert "Startup Inc" in result

    def test_includes_education(self):
        result = export_resume_to_plain_text(_SIMPLE_RESUME)
        assert "EDUCATION" in result
        assert "B.S. Computer Science" in result
        assert "State University" in result

    def test_includes_skills(self):
        result = export_resume_to_plain_text(_SIMPLE_RESUME)
        assert "SKILLS" in result
        assert "Python" in result
        assert "Machine Learning" in result

    def test_includes_projects(self):
        result = export_resume_to_plain_text(_SIMPLE_RESUME)
        assert "PROJECTS" in result
        assert "ML Pipeline" in result
        assert "Inventory System" in result
        assert "TensorFlow" in result

    def test_missing_name_raises(self):
        bad = dict(_SIMPLE_RESUME)
        bad["contact"] = {"email": "test@test.com"}
        with pytest.raises(ValueError, match="contact.name"):
            export_resume_to_plain_text(bad)

    def test_missing_experience_raises(self):
        bad = dict(_SIMPLE_RESUME)
        bad["experience"] = []
        with pytest.raises(ValueError, match="experience"):
            export_resume_to_plain_text(bad)


# ---------------------------------------------------------------------------
# PDF tests
# ---------------------------------------------------------------------------

class TestExportPdf:
    """Tests for export_to_pdf()."""

    def test_returns_bytes(self):
        result = export_to_pdf(_SIMPLE_JOURNEY)
        assert isinstance(result, bytes)

    def test_valid_pdf_header_and_trailer(self):
        result = export_to_pdf(_SIMPLE_JOURNEY)
        assert result[:4] == b"%PDF"
        assert b"%%EOF" in result

    def test_pdf_has_content_stream(self):
        result = export_to_pdf(_SIMPLE_JOURNEY)
        # A valid PDF should have stream/endstream markers
        assert b"stream" in result
        assert b"endstream" in result

    def test_pdf_multiple_pages_for_multi_card(self):
        """A multi-card journey should produce a PDF with multiple pages."""
        result = export_to_pdf(_MULTI_CARD_JOURNEY)
        # Count page objects to verify multi-page
        page_count = result.count(b"/Type /Page")
        assert page_count >= 2

    def test_pdf_non_empty(self):
        result = export_to_pdf(_SIMPLE_JOURNEY)
        assert len(result) > 500  # A minimal valid PDF is typically >500 bytes

    def test_missing_topic_raises(self):
        bad = dict(_SIMPLE_JOURNEY)
        del bad["topic"]
        with pytest.raises(ValueError, match="topic"):
            export_to_pdf(bad)

    def test_missing_cards_raises(self):
        bad = dict(_SIMPLE_JOURNEY, cards=[])
        with pytest.raises(ValueError, match="at least one card"):
            export_to_pdf(bad)

    def test_can_write_to_file(self, tmp_path):
        """Verify the PDF bytes can be written to disk."""
        pdf_bytes = export_to_pdf(_SIMPLE_JOURNEY)
        filepath = tmp_path / "test.pdf"
        filepath.write_bytes(pdf_bytes)
        assert filepath.exists()
        assert filepath.stat().st_size > 500


# ---------------------------------------------------------------------------
# Resume PDF tests
# ---------------------------------------------------------------------------

class TestExportResumePdf:
    """Tests for export_resume_to_pdf()."""

    def test_returns_bytes(self):
        result = export_resume_to_pdf(_SIMPLE_RESUME)
        assert isinstance(result, bytes)

    def test_valid_pdf_header(self):
        result = export_resume_to_pdf(_SIMPLE_RESUME)
        assert result[:4] == b"%PDF"

    def test_pdf_non_empty(self):
        result = export_resume_to_pdf(_SIMPLE_RESUME)
        assert len(result) > 500

    def test_missing_name_raises(self):
        bad = dict(_SIMPLE_RESUME)
        bad["contact"] = {}
        with pytest.raises(ValueError, match="contact.name"):
            export_resume_to_pdf(bad)

    def test_missing_experience_raises(self):
        bad = dict(_SIMPLE_RESUME)
        bad["experience"] = []
        with pytest.raises(ValueError, match="experience"):
            export_resume_to_pdf(bad)


# ---------------------------------------------------------------------------
# Resume DOCX tests
# ---------------------------------------------------------------------------

class TestExportResumeDocx:
    """Tests for export_resume_to_docx()."""

    def test_returns_bytes(self):
        result = export_resume_to_docx(_SIMPLE_RESUME)
        assert isinstance(result, bytes)

    def test_valid_docx_archive(self):
        """DOCX is a ZIP archive — check for ZIP magic bytes."""
        result = export_resume_to_docx(_SIMPLE_RESUME)
        assert result[:4] == b"PK\x03\x04"  # ZIP magic bytes

    def test_docx_non_empty(self):
        result = export_resume_to_docx(_SIMPLE_RESUME)
        assert len(result) > 1000  # A DOCX is typically larger than a minimal ZIP

    def test_missing_name_raises(self):
        bad = dict(_SIMPLE_RESUME)
        bad["contact"] = {}
        with pytest.raises(ValueError, match="contact.name"):
            export_resume_to_docx(bad)

    def test_missing_experience_raises(self):
        bad = dict(_SIMPLE_RESUME)
        bad["experience"] = []
        with pytest.raises(ValueError, match="experience"):
            export_resume_to_docx(bad)


# ---------------------------------------------------------------------------
# Unified export dispatcher tests
# ---------------------------------------------------------------------------

class TestExportDispatcher:
    """Tests for the unified export() function."""

    def test_export_journey_text(self):
        result = export(_SIMPLE_JOURNEY, format="text")
        assert isinstance(result, str)
        assert "PYTHON BASICS" in result.upper()

    def test_export_journey_pdf(self):
        result = export(_SIMPLE_JOURNEY, format="pdf")
        assert isinstance(result, bytes)
        assert result[:4] == b"%PDF"

    def test_export_resume_text(self):
        result = export(_SIMPLE_RESUME, format="text")
        assert isinstance(result, str)
        assert "JOHN SMITH" in result.upper()

    def test_export_resume_pdf(self):
        result = export(_SIMPLE_RESUME, format="pdf")
        assert isinstance(result, bytes)
        assert result[:4] == b"%PDF"

    def test_export_resume_docx(self):
        result = export(_SIMPLE_RESUME, format="docx")
        assert isinstance(result, bytes)
        assert result[:4] == b"PK\x03\x04"

    def test_journey_unsupported_format_raises(self):
        with pytest.raises(KeyError, match="docx"):
            export(_SIMPLE_JOURNEY, format="docx")

    def test_unknown_content_raises(self):
        with pytest.raises(ValueError, match="Cannot detect"):
            export({"foo": "bar"}, format="text")

    def test_export_to_file_journey(self, tmp_path):
        filepath = str(tmp_path / "journey.txt")
        result = export(_SIMPLE_JOURNEY, format="text", filepath=filepath)
        assert result == filepath
        assert tmp_path.joinpath("journey.txt").exists()

    def test_export_to_file_resume_pdf(self, tmp_path):
        filepath = str(tmp_path / "resume.pdf")
        result = export(_SIMPLE_RESUME, format="pdf", filepath=filepath)
        assert result == filepath
        assert tmp_path.joinpath("resume.pdf").exists()

    def test_export_to_file_resume_docx(self, tmp_path):
        filepath = str(tmp_path / "resume.docx")
        result = export(_SIMPLE_RESUME, format="docx", filepath=filepath)
        assert result == filepath
        assert tmp_path.joinpath("resume.docx").exists()


# ---------------------------------------------------------------------------
# Manual verification step
# ---------------------------------------------------------------------------

def test_manual_verification():
    """
    Contract: Manual verification step for resume export.

    To verify manually:
    1. Test resume export functions:
       python -c "
       from engines.export_engine.export import export
       resume = {
           'contact': {'name': 'Test User', 'email': 'test@example.com'},
           'summary': 'Test summary',
           'experience': [{'title': 'Engineer', 'company': 'Test', 'dates': '2020-2023', 'description': 'Worked on stuff'}],
           'education': [{'degree': 'BS', 'school': 'University', 'dates': '2016-2020'}],
           'skills': ['Python', 'JavaScript'],
           'projects': [{'name': 'Project', 'description': 'A project', 'tech': ['Python']}]
       }
       # Export to text
       text = export(resume, format='text')
       print('TEXT export OK:', len(text), 'chars')
       # Export to PDF
       pdf = export(resume, format='pdf')
       print('PDF export OK:', len(pdf), 'bytes')
       # Export to DOCX
       docx = export(resume, format='docx')
       print('DOCX export OK:', len(docx), 'bytes')
       "

    2. Verify file writing:
       python -c "
       from engines.export_engine.export import export
       resume = { /* same as above */ }
       export(resume, format='pdf', filepath='/tmp/resume.pdf')
       export(resume, format='docx', filepath='/tmp/resume.docx')
       print('Files written to /tmp/')
       "
    """
    # Placeholder for documentation
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
