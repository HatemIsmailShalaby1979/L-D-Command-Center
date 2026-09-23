# engines/export-engine/test_export_integration.py
#
# WHAT: Integration tests for the honest unified export() dispatcher —
#       routing, file writing, and the no-generation contract.
# WHY:  P4.2: export must never generate. The old suite covered four
#       audio-regeneration paths; those are gone by design, replaced by
#       tests that pin the ValueError pointing callers at explicit
#       engine composition (CONTEXT.md "Export").
# BREAKS IF DELETED: Dispatcher routing and the determinism contract are
#       unprotected.

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from engines.export_engine.export import _detect_type, export


_SIMPLE_JOURNEY = {
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
        }
    ],
}

_SIMPLE_RESUME = {
    "contact": {"name": "Jane Doe", "email": "jane@example.com"},
    "summary": "Engineer.",
    "experience": [{"title": "Dev", "company": "Corp",
                    "dates": "2020-2023", "description": "Built things"}],
    "education": [{"degree": "BS", "school": "Uni", "dates": "2016-2020"}],
    "skills": ["Python"],
    "projects": [{"name": "Proj", "description": "A project", "tech": ["Py"]}],
}


class TestDetectType:
    def test_journey(self):
        assert _detect_type(_SIMPLE_JOURNEY) == "journey"

    def test_resume(self):
        assert _detect_type(_SIMPLE_RESUME) == "resume"

    def test_narration(self):
        assert _detect_type({"text": "hello"}) == "narration"

    def test_unknown(self):
        assert _detect_type({"foo": 1}) == "unknown"


class TestDispatchJourney:
    @pytest.mark.parametrize("fmt,magic", [
        ("text", None),
        ("pdf", b"%PDF"),
        ("pptx", b"PK\x03\x04"),
        ("xlsx", b"PK\x03\x04"),
    ])
    def test_supported_formats_render(self, fmt, magic):
        result = export(_SIMPLE_JOURNEY, format=fmt)
        if fmt == "text":
            assert isinstance(result, str) and "PYTHON BASICS" in result
        else:
            assert isinstance(result, bytes)
            assert result[:len(magic)] == magic

    def test_unsupported_format_raises_keyerror(self):
        with pytest.raises(KeyError):
            export(_SIMPLE_JOURNEY, format="docx")


class TestDispatchResume:
    @pytest.mark.parametrize("fmt,magic", [
        ("text", None),
        ("pdf", b"%PDF"),
        ("docx", b"PK\x03\x04"),
    ])
    def test_supported_formats_render(self, fmt, magic):
        result = export(_SIMPLE_RESUME, format=fmt)
        if fmt == "text":
            assert isinstance(result, str) and "JANE DOE" in result
        else:
            assert isinstance(result, bytes)
            assert result[:len(magic)] == magic

    def test_unsupported_format_raises_keyerror(self):
        with pytest.raises(KeyError):
            export(_SIMPLE_RESUME, format="xlsx")


class TestNoGenerationContract:
    """P4.2: these content kinds would require calling the model."""

    @pytest.mark.parametrize("kind,content", [
        ("podcast", {"topic": "t", "host_name": "h"}),
        ("bilingual", {"target_language": "es", "known_language": "en"}),
        ("immersion", {"topic": "t", "target_language": "es", "segments": []}),
    ])
    def test_audio_generation_kinds_are_rejected(self, kind, content):
        with pytest.raises(ValueError, match="never generates|deterministic"):
            export(content, format="wav")

    def test_error_points_at_engine_composition(self):
        with pytest.raises(ValueError, match="generate_podcast_script"):
            export({"topic": "t", "host_name": "h"}, format="mp3")

    def test_narration_exports_existing_text_to_wav(self):
        """Narration IS deterministic (text-in -> audio-out)."""
        from engines.audio_engine.assembly import DEFAULT_SAMPLE_RATE, _make_wav_header
        wav = _make_wav_header(4) + b"\x00\x00\x00\x00"
        with patch("engines.audio_engine.assembly.tts_synthesize",
                   return_value=wav):
            result = export({"text": "hello"}, format="wav")
        assert result.startswith(b"RIFF")

    def test_unknown_content_raises_valueerror(self):
        with pytest.raises(ValueError, match="Cannot detect"):
            export({"foo": 1}, format="text")


class TestFileWriting:
    @pytest.mark.parametrize("fmt,suffix", [
        ("text", ".txt"), ("pdf", ".pdf"),
        ("pptx", ".pptx"), ("xlsx", ".xlsx"),
    ])
    def test_journey_written_to_path(self, tmp_path, fmt, suffix):
        out = tmp_path / f"journey{suffix}"
        returned = export(_SIMPLE_JOURNEY, format=fmt, filepath=str(out))
        assert returned == str(out)
        assert out.stat().st_size > 0

    def test_resume_docx_written_to_path(self, tmp_path):
        out = tmp_path / "resume.docx"
        export(_SIMPLE_RESUME, format="docx", filepath=str(out))
        assert out.read_bytes()[:2] == b"PK"

    def test_creates_missing_parent_dirs(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "j.txt"
        export(_SIMPLE_JOURNEY, format="text", filepath=str(out))
        assert out.exists()
