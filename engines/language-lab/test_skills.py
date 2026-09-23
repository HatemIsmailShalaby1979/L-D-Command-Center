# engines/language-lab/test_skills.py
#
# WHAT: Contract tests for the Skills Arena engine — reading packs,
#       writing evaluation, document text extraction.
# WHY:  The Arena practices on the USER'S OWN material; a crash on a
#       weird PDF or a five-word writing submission must degrade to
#       a friendly message, never a traceback. Validation counts and
#       the preserve-their-voice rule are pinned with fakes.
# BREAKS IF DELETED: Broken imports surface as dead panels; the
#       corrected-version promise silently rots.

from __future__ import annotations

import json

import pytest

from engines.language_lab.skills import (
    evaluate_writing, extract_document_text, generate_reading_pack,
)
from model_layer.client import ModelResponse
from model_layer.pipeline import DEFAULT_MODEL


class FakeLm:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return ModelResponse(content=outcome, model=DEFAULT_MODEL,
                             finish_reason="stop", tool_calls=None,
                             raw={})


LONG_TEXT = " ".join(f"word{i}" for i in range(80))


def _reading_pack_json():
    return json.dumps({
        "title": "A day at the market",
        "cleaned_text": LONG_TEXT,
        "glossary": [{"term": "t", "translation": "x"}
                     for _ in range(6)],
        "questions": [
            {"question": f"q{i}", "options": ["a", "b", "c", "d"],
             "correct_index": i % 4} for i in range(4)],
    })


def _writing_json():
    return json.dumps({
        "grammar": 4, "vocabulary": 3, "structure": 4, "register": 5,
        "strength": "Your opening hooks the reader.",
        "corrected_text": "Yesterday I went to the market with joy.",
        "highlights": [{"wrong": "I go", "right": "I went",
                         "why": "past tense"},
                        {"wrong": "with joyness", "right": "with joy",
                         "why": "word choice"}],
        "next_step": "Write three more past-tense sentences."})


class TestExtraction:
    def test_txt_roundtrip(self, tmp_path):
        path = tmp_path / "note.txt"
        path.write_text("Hello world content here.", encoding="utf-8")
        assert extract_document_text(str(path)) == \
            "Hello world content here."

    def test_unreadable_returns_empty_never_raises(self, tmp_path):
        path = tmp_path / "broken.pdf"
        path.write_bytes(b"not really a pdf")
        assert extract_document_text(str(path)) == ""

    def test_unsupported_type_returns_empty(self, tmp_path):
        path = tmp_path / "image.png"
        path.write_bytes(b"pngdata")
        assert extract_document_text(str(path)) == ""


class TestReadingPacks:
    def test_valid_pack_generated(self):
        pack = generate_reading_pack(LONG_TEXT, "de", "b1",
                                     client=FakeLm(_reading_pack_json()))
        assert len(pack["questions"]) == 4
        assert 5 <= len(pack["glossary"]) <= 8

    def test_short_text_rejected_friendly(self):
        with pytest.raises(ValueError, match="too short"):
            generate_reading_pack("tiny text", "de", "b1",
                                  client=FakeLm())

    def test_invalid_pack_retries_then_fails(self):
        bad = json.dumps({"title": "x", "cleaned_text": "y",
                          "glossary": [], "questions": []})
        client = FakeLm(bad, bad, bad, bad)
        from model_layer.schema import SchemaValidationError
        with pytest.raises(SchemaValidationError):
            generate_reading_pack(LONG_TEXT, "de", "b1", client=client)


class TestWritingEvaluation:
    def test_valid_evaluation_with_correction(self):
        text = " ".join(f"word{i}" for i in range(15))
        result = evaluate_writing("Describe your city.", text,
                                  "es", "a2",
                                  client=FakeLm(_writing_json()))
        assert result["corrected_text"]
        assert result["highlights"][0]["right"] == "I went"
        assert len(result["highlights"]) == 2

    def test_short_writing_rejected_friendly(self):
        with pytest.raises(ValueError, match="Write a little more"):
            evaluate_writing("task", "too short", "es", "a2",
                             client=FakeLm())

    def test_highlights_count_enforced(self):
        payload = json.loads(_writing_json())
        payload["highlights"] = [{"wrong": "a", "right": "b",
                                    "why": "c"}]  # only 1 -> invalid
        client = FakeLm(json.dumps(payload),
                        json.dumps(payload),
                        json.dumps(payload),
                        json.dumps(payload))
        from model_layer.schema import SchemaValidationError
        with pytest.raises(SchemaValidationError):
            evaluate_writing("task", " ".join(["word"] * 12),
                             "es", "a2", client=client)
