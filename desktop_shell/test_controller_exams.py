# desktop-shell/test_controller_exams.py
#
# WHAT: Contract tests for the exam + placement controller seam.
# WHY:  Exams are the emotional peak of the product — a crash or a
#       lost result mid-exam is unforgivable. These pin: generation
#       gating (1 per level free), full submit grading with result
#       persistence, curriculum bookkeeping on pass, placement flow,
#       and friendly errors — all with fakes.
# BREAKS IF DELETED: Exam regressions surface as lost results for
#       real users who just spent 30 minutes proving themselves.

from __future__ import annotations

import json

import pytest

from desktop_shell.controller import ShellController
from model_layer.client import ModelResponse
from model_layer.pipeline import DEFAULT_MODEL
from storage.persistence import Storage


@pytest.fixture
def storage(tmp_path):
    return Storage(root=tmp_path)


class OkClient:
    def is_available(self):
        return True


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


def _mc(question="Q?", correct_index=0):
    return {"question": question, "options": ["a", "b", "c", "d"],
            "correct_index": correct_index}


EXAM = {
    "level": "a1", "language": "Spanish",
    "vocabulary": [_mc(f"v{i}", i % 4) for i in range(8)],
    "grammar": (
        [{"type": "mc", **_mc(f"g{i}", i % 4),
          "grammar_point": "x"} for i in range(6)]
        + [{"type": "fill", "sentence_with_blank": "___ here",
            "answer": f"w{i}", "grammar_point": "y"}
           for i in range(4)]),
    "reading": {"passage": " ".join(f"w{i}" for i in range(70)),
                 "questions": [_mc(f"r{i}", i % 4)
                                for i in range(5)]},
    "writing": {"prompt": "Write about your day.", "min_words": 60},
    "listening": {
        "script": [{"speaker": "Ana" if i % 2 == 0 else "Luis",
                    "content": f"line {i}"} for i in range(6)],
        "questions": [_mc(f"l{i}", i % 4) for i in range(5)]},
    "speaking": [
        {"type": "repeat", "text": "Hola buenos dias"},
        {"type": "describe", "situation": "Describe your home.",
         "target_phrases": ["x"]},
        {"type": "respond", "prompt": "Weekends?"}],
}

JUDGE = json.dumps({"grammar": 4, "vocabulary": 4, "structure": 4,
                    "register": 4, "feedback": "Solid.",
                    "band_estimate": "a2"})


class TestLevelExamFlow:
    def test_start_generates_saves_and_meters(self, storage):
        controller = ShellController(
            client=FakeLm(json.dumps(EXAM)), storage=storage)
        res = controller.level_exam_start("es", "a1")
        assert res.ok, res.detail
        assert res.payload["saved_as"] == "es-a1-exam.json"
        exams = controller.list_saved("level_exams")
        assert res.payload["saved_as"] in exams.payload

    def test_second_attempt_same_level_needs_pro(self, storage):
        controller = ShellController(
            client=FakeLm(json.dumps(EXAM), json.dumps(EXAM)),
            storage=storage)
        assert controller.level_exam_start("es", "a1").ok
        blocked = controller.level_exam_start("es", "a1")
        assert not blocked and blocked.error_kind == "license"
        assert "Pro" in blocked.detail

    def test_different_levels_each_get_one_shot(self, storage):
        controller = ShellController(
            client=FakeLm(json.dumps(EXAM), json.dumps(EXAM)),
            storage=storage)
        assert controller.level_exam_start("es", "a1").ok
        assert controller.level_exam_start("es", "a2").ok

    def test_pro_key_allows_retakes(self, storage):
        from storage.licensing import issue_license
        controller = ShellController(
            client=FakeLm(*[json.dumps(EXAM)] * 3), storage=storage)
        controller.activate_license(issue_license("pro", licensee="A"))
        for _ in range(3):
            assert controller.level_exam_start("es", "b1").ok

    def test_bad_level_friendly(self, storage):
        controller = ShellController(client=OkClient(), storage=storage)
        res = controller.level_exam_start("es", "c2")
        assert not res and res.error_kind == "input"

    def test_submit_grades_and_persists_result(self, storage):
        controller = ShellController(
            client=FakeLm(JUDGE, JUDGE, JUDGE), storage=storage)
        answers = {
            "vocabulary": [i % 4 for i in range(8)],
            "grammar": {"mc": [i % 4 for i in range(6)],
                        "fill": [f"w{i}" for i in range(4)]},
            "reading": [i % 4 for i in range(5)],
            "listening": [i % 4 for i in range(5)],
        }
        speaking = [{"transcript": "hola buenos dias"},
                    {"transcript": "mi casa es grande"},
                    {"transcript": "me gusta descansar"}]
        res = controller.level_exam_submit(
            "es", "a1", EXAM, answers, "Mi dia fue bueno.",
            speaking)
        assert res.ok, res.detail
        result = res.payload
        assert result["passed"] is True
        assert result["overall"] >= 90
        assert result["recommendations"]
        saved = controller.level_exam_results("es")
        assert saved.ok and len(saved.payload) == 1

    def test_pass_marks_curriculum_slots_done(self, storage):
        # writing judge + 2 free-speaking judges (repeat is STT-scored)
        controller = ShellController(
            client=FakeLm(JUDGE, JUDGE, JUDGE), storage=storage)
        answers = {"vocabulary": [i % 4 for i in range(8)],
                   "grammar": {"mc": [i % 4 for i in range(6)],
                               "fill": [f"w{i}" for i in range(4)]},
                   "reading": [i % 4 for i in range(5)],
                   "listening": [i % 4 for i in range(5)]}
        speaking = [{"transcript": "hola buenos dias"},
                    {"transcript": "mi casa"},
                    {"transcript": "descanso"}]
        res = controller.level_exam_submit("es", "a1", EXAM, answers,
                                           "Mi dia fue bueno.",
                                           speaking)
        assert res.ok and res.payload["passed"]
        catalog = controller.curriculum_catalog("es")
        statuses = [r.get("status") for r in catalog.payload
                    if r.get("kind") == "slot"
                    and r.get("level") == "a1"]
        assert "done" in statuses

    def test_empty_writing_is_neutral_not_fatal(self, storage):
        controller = ShellController(
            client=FakeLm(JUDGE, JUDGE, JUDGE), storage=storage)
        res = controller.level_exam_submit(
            "es", "a1", EXAM,
            {"vocabulary": [0] * 8,
             "grammar": {"mc": [0] * 6, "fill": ["x"] * 4},
             "reading": [0] * 5, "listening": [0] * 5},
            "", [])
        assert res.ok
        assert "no answer submitted" in \
            res.payload["sections"]["writing"]["feedback"]


class TestPlacementFlow:
    QUIZ = {"items": [
        {"question": f"q{i}", "options": ["a", "b", "c", "d"],
         "correct_index": 0,
         "band": "a1" if i < 4 else ("a2" if i < 8 else "b1")}
        for i in range(12)]}

    def test_start_saves_quiz_never_gated(self, storage):
        # 20 quizzes x 3 band blocks each; placement is never gated
        def _block():
            return json.dumps({"items": [
                {"question": "q", "options": ["a", "b", "c", "d"],
                 "correct_index": 0} for _ in range(4)]})
        controller = ShellController(
            client=FakeLm(*[_block() for _ in range(60)]),
            storage=storage)
        for _ in range(20):  # would exhaust any quota if gated
            assert controller.placement_start("de").ok
        saved = controller.list_saved("placement")
        assert saved.ok

    def test_grade_persists_and_points_to_library(self, storage):
        def _block():
            return json.dumps({"items": [
                {"question": "q", "options": ["a", "b", "c", "d"],
                 "correct_index": 0} for _ in range(4)]})
        controller = ShellController(
            client=FakeLm(*[_block() for _ in range(3)]),
            storage=storage)
        controller.placement_start("de")
        res = controller.placement_grade("de", [0] * 12)
        assert res.ok and res.payload["band"] == "b1"
        assert res.payload["recommended_first_slot"] == \
            "b1-people_friends"
        last = controller.placement_last("de")
        assert last.ok and last.payload["band"] == "b1"

    def test_grade_without_quiz_is_friendly(self, storage):
        controller = ShellController(client=OkClient(), storage=storage)
        res = controller.placement_grade("fr", [0] * 12)
        assert not res and res.error_kind == "input"
        assert "Start the placement quiz" in res.detail
