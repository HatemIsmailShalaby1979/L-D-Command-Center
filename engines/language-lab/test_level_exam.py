# engines/language-lab/test_level_exam.py
#
# WHAT: Contract tests for the level-exam and placement engines —
#       validation, deterministic grading, rubric fallback, result
#       assembly, recommendations, and banding honesty.
# WHY:  The owner demanded ONE inclusive final test per level with
#       full evaluations and recommendations — and "no errors, no
#       bugs". These tests pin every count, every weight, and the
#       pass threshold with fakes (no LM, no audio, no mic).
# BREAKS IF DELETED: A silent count regression ships broken exams to
#       real learners mid-test — the worst possible moment to fail.

from __future__ import annotations

import json

import pytest

from engines.language_lab.level_exam import (
    PASS_THRESHOLD, SECTION_WEIGHTS, build_exam_result,
    generate_level_exam, grade_objective_sections, grade_speaking_repeat,
    judge_answer, validate_level_exam,
)
from engines.language_lab.placement import (
    generate_placement_quiz, grade_placement, validate_placement_quiz,
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


def _mc(question="Q?", correct_index=0):
    return {"question": question,
            "options": ["a", "b", "c", "d"],
            "correct_index": correct_index}


def _valid_exam():
    return {
        "level": "a1", "language": "Spanish",
        "vocabulary": [_mc(f"v{i}", i % 4) for i in range(8)],
        "grammar": (
            [{"type": "mc", **_mc(f"g{i}", i % 4),
              "grammar_point": "x"} for i in range(6)]
            + [{"type": "fill",
                "sentence_with_blank": f"___ fill {i}",
                "answer": f"word{i}", "grammar_point": "y"}
               for i in range(4)]),
        "reading": {
            "passage": " ".join(f"word{i}" for i in range(70)),
            "questions": [_mc(f"r{i}", i % 4) for i in range(5)]},
        "writing": {"prompt": "Write about your day.",
                     "min_words": 60},
        "listening": {
            "script": [{"speaker": "Ana" if i % 2 == 0 else "Luis",
                        "content": f"line {i}"}
                       for i in range(6)],
            "questions": [_mc(f"l{i}", i % 4) for i in range(5)]},
        "speaking": [
            {"type": "repeat", "text": "Hello there my friend."},
            {"type": "describe", "situation": "Describe your home.",
             "target_phrases": ["es groß"]},
            {"type": "respond", "prompt": "Answer: weekends?"}],
    }


class TestValidation:
    def test_valid_exam_passes(self):
        ok, errors = validate_level_exam(_valid_exam())
        assert ok, errors

    def test_wrong_item_counts_rejected(self):
        exam = _valid_exam()
        exam["vocabulary"] = exam["vocabulary"][:6]
        ok, errors = validate_level_exam(exam)
        assert not ok and any("8" in e for e in errors)

    def test_grammar_mix_enforced(self):
        exam = _valid_exam()
        exam["grammar"] = [{"type": "mc", **_mc(), "grammar_point": "x"}
                           for _ in range(10)]
        ok, errors = validate_level_exam(exam)
        assert not ok and any("6 'mc' + 4 'fill'" in e for e in errors)

    def test_listening_needs_two_distinct_speakers(self):
        exam = _valid_exam()
        for turn in exam["listening"]["script"]:
            turn["speaker"] = "Ana"
        ok, errors = validate_level_exam(exam)
        assert not ok and any("2 distinct" in e for e in errors)

    def test_speaking_task_order_enforced(self):
        exam = _valid_exam()
        exam["speaking"][0] = {"type": "describe",
                               "situation": "x"}
        ok, errors = validate_level_exam(exam)
        assert not ok and any("repeat" in e for e in errors)

    def test_short_reading_passage_rejected(self):
        exam = _valid_exam()
        exam["reading"]["passage"] = "too short"
        ok, errors = validate_level_exam(exam)
        assert not ok and any("passage" in e for e in errors)

    def test_generation_uses_pipeline_and_validates(self):
        client = FakeLm("garbage first",
                        json.dumps(_valid_exam()))
        exam = generate_level_exam("es", "a1", client=client)
        assert len(exam["vocabulary"]) == 8
        assert len(client.requests) == 2  # feedback retry fired

    def test_bad_level_rejected_early(self):
        with pytest.raises(ValueError, match="a1, a2"):
            generate_level_exam("es", "c2", client=FakeLm())


class TestObjectiveGrading:
    def test_perfect_answers_score_100(self):
        exam = _valid_exam()
        answers = {
            "vocabulary": [i % 4 for i in range(8)],
            "grammar": {"mc": [i % 4 for i in range(6)],
                        "fill": [f"word{i}" for i in range(4)]},
            "reading": [i % 4 for i in range(5)],
            "listening": [i % 4 for i in range(5)],
        }
        result = grade_objective_sections(exam, answers)
        for name in ("vocabulary", "grammar", "reading", "listening"):
            assert result[name]["pct"] == 100, name

    def test_empty_answers_score_zero(self):
        result = grade_objective_sections(_valid_exam(), {})
        for name in ("vocabulary", "grammar", "reading", "listening"):
            assert result[name]["pct"] == 0

    def test_fill_answers_forgive_tiny_typos(self):
        exam = _valid_exam()
        # all MC wrong (fixture correct = i%4, so choose (i%4+1)%4),
        # fills: case/space variants forgiven, one genuinely wrong
        answers = {"grammar": {
            "mc": [(i + 1) % 4 for i in range(6)],
            "fill": ["Word0", "word1 ", "different", "word3"]}}
        result = grade_objective_sections(exam, answers)
        assert result["grammar"]["correct"] == 3  # 2 exact + 1 forgiven
        assert result["grammar"]["pct"] == 30


class TestJudging:
    def test_judge_validates_scores_and_band(self):
        payload = json.dumps({"grammar": 4, "vocabulary": 3,
                              "structure": 4, "register": 5,
                              "feedback": "Good control of tense.",
                              "band_estimate": "a2"})
        judged = judge_answer("Write about food.",
                              "Ich esse gern Pizza.",
                              language="de", level="a2",
                              client=FakeLm(payload))
        assert judged["band_estimate"] == "a2"

    def test_judge_failure_degrades_to_neutral_not_crash(self):
        judged = judge_answer("task", "answer", language="de",
                              level="a1",
                              client=FakeLm(ConnectionError("down"),
                                            ConnectionError("down")))
        assert judged["grammar"] == 3  # neutral, counted kindly
        assert "not against you" in judged["feedback"]

    def test_repeat_similarity(self):
        assert grade_speaking_repeat(
            "Ich trinke gern Kaffee",
            "ich trinke gern kaffee!") > 0.9
        assert grade_speaking_repeat("Guten Morgen", "bye") < 0.2
        assert grade_speaking_repeat("", "x") == 0.0


class TestResultAssembly:
    def _result(self, **over):
        exam = _valid_exam()
        objective = over.get("objective", {
            "vocabulary": {"correct": 8, "total": 8, "pct": 100},
            "grammar": {"correct": 10, "total": 10, "pct": 100},
            "reading": {"correct": 5, "total": 5, "pct": 100},
            "listening": {"correct": 5, "total": 5, "pct": 100}})
        writing = over.get("writing", {
            "grammar": 5, "vocabulary": 5, "structure": 5,
            "register": 5, "feedback": "Superb.",
            "band_estimate": "b1"})
        speaking = over.get("speaking", [
            {"score": 1.0}, {"score": 1.0, "band": "b1"},
            {"score": 1.0, "band": "b1"}])
        return build_exam_result(exam, objective, writing, speaking,
                                 language="es",
                                 level=over.get("level", "a1"))

    def test_perfect_exam_passes_with_verdict(self):
        result = self._result(level="a1")
        assert result["overall"] == 100
        assert result["passed"]
        assert "demolished" in result["verdict_line"]

    def test_weights_sum_to_100(self):
        assert sum(SECTION_WEIGHTS.values()) == 100
        assert PASS_THRESHOLD == 70

    def test_weak_sections_get_slot_recommendations(self):
        result = self._result(
            objective={"vocabulary": {"correct": 2, "total": 8,
                                      "pct": 25},
                       "grammar": {"correct": 5, "total": 10,
                                   "pct": 50},
                       "reading": {"correct": 5, "total": 5, "pct": 100},
                       "listening": {"correct": 5, "total": 5,
                                     "pct": 100}},
            level="b1")
        tips = " ".join(result["recommendations"])
        assert "Vocabulary" in tips or "vocabulary" in tips
        assert "library lesson" in tips

    def test_fail_verdict_is_warm_not_punishing(self):
        result = self._result(
            objective={"vocabulary": {"correct": 0, "total": 8, "pct": 0},
                       "grammar": {"correct": 0, "total": 10, "pct": 0},
                       "reading": {"correct": 1, "total": 5, "pct": 20},
                       "listening": {"correct": 1, "total": 5, "pct": 20}},
            writing={"grammar": 2, "vocabulary": 2, "structure": 2,
                     "register": 2, "feedback": "Keep going.",
                     "band_estimate": "a1"},
            speaking=[{"score": 0.3}, {"score": 0.3}, {"score": 0.3}],
            level="b2")
        assert not result["passed"]
        assert "fine" in result["verdict_line"]


class TestPlacement:
    def _quiz(self):
        return {"items": [
            {"question": f"q{i}", "options": ["a", "b", "c", "d"],
             "correct_index": 0,
             "band": "a1" if i < 4 else ("a2" if i < 8 else "b1")}
            for i in range(12)]}

    def test_quiz_validation_enforces_bands(self):
        quiz = {"items": self._quiz()["items"]}
        quiz["items"][5]["band"] = "b1"  # breaks escalation
        ok, errors = validate_placement_quiz(quiz)
        assert not ok

    def test_all_correct_places_b1(self):
        result = grade_placement(self._quiz(), [0] * 12)
        assert result["band"] == "b1"
        assert result["recommended_first_slot"] == "b1-people_friends"

    def test_zero_correct_places_a1_kindly(self):
        result = grade_placement(self._quiz(), [1] * 12)
        assert result["band"] == "a1"
        assert "blank page" in result["rationale"]

    def test_a2_clearing_places_a2(self):
        # 4 a1 + 3 a2 correct, 0 b1 -> a2
        answers = [0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1]
        result = grade_placement(self._quiz(), answers)
        assert result["band"] == "a2"
        assert "home" in result["rationale"]

    def test_generation_through_pipeline(self):
        # three band blocks (a1, a2, b1), each a 4-item chunk
        def _block(band):
            return json.dumps({"items": [
                {"question": f"q{band}{i}",
                 "options": ["a", "b", "c", "d"],
                 "correct_index": 0} for i in range(4)]})
        client = FakeLm(_block("a1"), _block("a2"), _block("b1"))
        quiz = generate_placement_quiz("de", client=client)
        assert len(quiz["items"]) == 12
        assert [i["band"] for i in quiz["items"]] == \
            ["a1"] * 4 + ["a2"] * 4 + ["b1"] * 4
