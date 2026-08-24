# engines/language-lab/test_graders.py
#
# WHAT: Contract tests for P7.3 grading — deterministic graders, judge
#       fallback, pack fidelity audit.
# WHY:  Grading is a correctness surface: a deterministic grader that
#       marks right answers wrong (or vice versa), or a judge verdict
#       that silently passes malformed output, breaks the flagship's
#       trust contract. Every rule and every rejection branch is proven
#       here against scripted clients; LM Studio never required.
# BREAKS IF DELETED: Learner scores become untrustworthy; pack errors
#       reach learners unaudited.

from __future__ import annotations

import json

import pytest

from engines.language_lab.graders import (
    accepted_answers,
    grade_drill,
    grade_deterministic,
    grade_fill_in_blank,
    grade_item,
    grade_multiple_choice,
    judge_grade,
    normalize_answer,
    validate_judge_verdict,
    validate_pack_verdict,
    verify_lesson_pack,
)
from model_layer.client import ModelResponse
from model_layer.prompts import PromptRegistry
from model_layer.schema import SchemaValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def mc_item(**over):
    item = {"type": "multiple_choice", "question": "Q?",
            "options": ["a", "b", "c"], "correct_index": 1}
    item.update(over)
    return item


def blank_item(**over):
    item = {"type": "fill_in_blank", "sentence_with_blank": "Yo ___ alto.",
            "answer": "soy"}
    item.update(over)
    return item


def translation_item(**over):
    item = {"type": "translation", "prompt": "I am tall.",
            "answer": "Soy alto"}
    item.update(over)
    return item


class ScriptedClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        body = self.responses.pop(0)
        if isinstance(body, Exception):
            raise body
        content = body if isinstance(body, str) else json.dumps(body)
        return ModelResponse(content=content, model=request.model,
                             finish_reason="stop", tool_calls=None, raw={})


def good_pack():
    return {
        "topic": "Ordering coffee",
        "target_language": "es",
        "known_language": "en",
        "level": "beginner",
        "vocab_cards": [
            {"term": "el cafe", "reading": "el ka-FE", "translation": "coffee",
             "example": "Un cafe, por favor."},
            {"term": "la leche", "reading": "la LE-che", "translation": "milk",
             "example": "Con leche."},
        ],
        "grammar_cards": [
            {"point": "ser vs estar",
             "explanation": "ser = permanent; estar = temporary.",
             "drills": [{"prompt": "Yo ___ alto.", "answer": "soy"}]},
        ],
        "dialogue": [],
        "evaluation": [],
    }


# ---------------------------------------------------------------------------
# Normalization + answer keys
# ---------------------------------------------------------------------------

class TestNormalization:
    @pytest.mark.parametrize("raw,expected", [
        ("  Soy  Alto! ", "soy alto"),
        ("¿Hasta luego?", "hasta luego"),   # edge punctuation stripped both sides
        ("¡Soy alto!", "soy alto"),
        ("'la cuenta.'", "la cuenta"),
        ("SOY", "soy"),
        ("tengo\nhambre", "tengo hambre"),
    ])
    def test_normalize(self, raw, expected):
        assert normalize_answer(raw) == expected

    @pytest.mark.parametrize("key,expected", [
        ("soy", ["soy"]),
        ("soy / estoy", ["soy", "estoy"]),
        ("el;la", ["el", "la"]),
        (" / ", []),
        (None, []),
        (5, []),
    ])
    def test_accepted_answers(self, key, expected):
        assert accepted_answers(key) == expected


# ---------------------------------------------------------------------------
# Deterministic graders
# ---------------------------------------------------------------------------

class TestDeterministicGraders:
    def test_mc_correct_and_incorrect(self):
        assert grade_multiple_choice(mc_item(), 1).correct
        result = grade_multiple_choice(mc_item(), 0)
        assert not result.correct and result.method == "deterministic"

    def test_mc_rejects_bool_and_strings_without_crash(self):
        for bad in (True, "1", None):
            result = grade_multiple_choice(mc_item(), bad)
            assert not result.correct

    def test_mc_index_out_of_range_is_wrong_not_error(self):
        assert not grade_multiple_choice(mc_item(), 99).correct

    def test_fill_in_blank_exact_case_punct(self):
        assert grade_fill_in_blank(blank_item(), "  SOY! ").correct

    def test_fill_in_blank_alternatives(self):
        item = blank_item(answer="soy / estoy")
        assert grade_fill_in_blank(item, "Estoy").correct

    def test_fill_in_blank_accent_fold_counts_but_says_so(self):
        item = blank_item(answer="café")
        result = grade_fill_in_blank(item, "cafe")
        assert result.correct and result.detail == "correct ignoring accents"

    def test_fill_in_blank_wrong_reports_expected_key(self):
        result = grade_fill_in_blank(blank_item(answer="soy"), "estoy")
        assert not result.correct and "soy" in result.detail

    def test_drill_shares_fill_in_blank_path(self):
        drill = {"prompt": "___ hambre?", "answer": "Tienes"}
        assert grade_drill(drill, " tienes.").correct
        assert not grade_drill(drill, "tengo").correct

    def test_translation_exact_passes_deterministically(self):
        result = grade_deterministic(translation_item(), "¡soy alto!")
        assert result is not None and result.correct

    def test_translation_free_variant_needs_the_judge(self):
        assert grade_deterministic(
            translation_item(), "yo soy una persona alta") is None

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="telepathy"):
            grade_deterministic({"type": "telepathy"}, "x")


# ---------------------------------------------------------------------------
# Judge fallback
# ---------------------------------------------------------------------------

class TestJudgeVerdict:
    JUDGE_VARS = {
        "target_language": "es", "known_language": "en", "level": "beginner",
        "item": "{}", "answer": '"algo"',
    }
    VERIFY_VARS = {
        "topic": "t", "target_language": "es", "known_language": "en",
        "level": "beginner", "claims": "V0. [x]",
    }

    @pytest.mark.parametrize("name,variables", [
        ("lesson_judge", JUDGE_VARS),
        ("lesson_verify", VERIFY_VARS),
    ])
    def test_templates_registered(self, name, variables):
        system, user, _ = PromptRegistry().render(name, dict(variables))
        assert system and user

    def test_validate_accepts_wellformed(self):
        ok, errors = validate_judge_verdict(
            {"passed": True, "correct_answer": "soy", "issues": []})
        assert ok and not errors

    @pytest.mark.parametrize("payload,fragment", [
        ({"passed": 1}, "'passed' must be a boolean"),
        ({"passed": True, "correct_answer": "  "}, "non-empty string"),
        ({"passed": True, "issues": "many"}, "'issues' must be a list"),
        ({"passed": True, "issues": [7]}, "must be a string"),
        ("nope", "JSON object"),
    ])
    def test_validate_rejects_malformed(self, payload, fragment):
        ok, errors = validate_judge_verdict(payload)
        assert not ok and any(fragment in e for e in errors)

    def test_judge_pass_carries_canonical_answer(self):
        client = ScriptedClient({"passed": True, "correct_answer": "soy alto",
                                 "issues": []})
        result = judge_grade(translation_item(), "yo soy alto",
                             target_language="es", client=client)
        assert result.correct and result.method == "judge"
        assert "canonical" in result.detail

    def test_judge_fail_lists_issues(self):
        client = ScriptedClient({"passed": False, "issues": ["wrong verb"]})
        result = judge_grade(translation_item(), "estoy alto",
                             target_language="es", client=client)
        assert not result.correct and "wrong verb" in result.detail

    def test_judge_prompt_contains_item_and_answer_verbatim(self):
        client = ScriptedClient({"passed": True, "issues": []})
        judge_grade(translation_item(), "soy alto",
                    target_language="es", level="advanced", client=client)
        user = client.requests[0].messages[-1]["content"]
        assert '"prompt"' in user and '"soy alto"' in user
        assert "advanced" in user

    def test_malformed_judge_output_raises_typed_error(self):
        client = ScriptedClient("prose, not JSON")
        with pytest.raises(SchemaValidationError):
            judge_grade(translation_item(), "x", target_language="es",
                        client=client)


class TestGradeItemDispatch:
    def test_deterministic_hit_never_calls_the_model(self):
        client = ScriptedClient()
        result = grade_item(mc_item(), 1, client=client)
        assert result.correct and result.method == "deterministic"
        assert client.requests == []

    def test_deterministic_miss_also_skips_the_model(self):
        client = ScriptedClient()
        assert not grade_item(mc_item(), 0, client=client).correct
        assert client.requests == []

    def test_free_form_falls_through_to_judge(self):
        client = ScriptedClient({"passed": True, "correct_answer": "x",
                                 "issues": []})
        result = grade_item(translation_item(), "me llamo alto",
                            target_language="es", client=client)
        assert result.method == "judge" and len(client.requests) == 1

    def test_free_form_without_client_raises_not_fails_silently(self):
        with pytest.raises(ValueError, match="no judge"):
            grade_item(translation_item(), "me llamo alto")


# ---------------------------------------------------------------------------
# Pack fidelity audit
# ---------------------------------------------------------------------------

class TestVerifyLessonPack:
    def test_all_claims_ok(self):
        pack = good_pack()
        client = ScriptedClient({"passed": True, "issues": []})
        artifact = verify_lesson_pack(pack, client=client)
        assert artifact["passed"] is True
        assert [c["id"] for c in artifact["claims"]] == ["V0", "V1", "G0"]
        assert all(c["ok"] for c in artifact["claims"])
        user = client.requests[0].messages[-1]["content"]
        for fragment in ("V0.", "G0.", "el cafe", "ser vs estar", "beginner"):
            assert fragment in user, fragment

    def test_flagged_claim_flips_overall_verdict(self):
        client = ScriptedClient({"passed": True, "issues": [
            {"claim": "V1", "problem": "leche means milk, not bread"}]})
        artifact = verify_lesson_pack(good_pack(), client=client)
        assert artifact["passed"] is False
        flagged = [c for c in artifact["claims"] if not c["ok"]]
        assert [c["id"] for c in flagged] == ["V1"]
        assert "milk" in flagged[0]["problem"]

    def test_overall_never_contradicts_its_own_rows(self):
        client = ScriptedClient({"passed": True, "issues": []})
        artifact = verify_lesson_pack(good_pack(), client=client)
        assert artifact["passed"] == all(c["ok"] for c in artifact["claims"])

    def test_malformed_audit_raises_typed_error(self):
        client = ScriptedClient({"passed": True, "issues": [{"nope": 1}]})
        with pytest.raises(SchemaValidationError):
            verify_lesson_pack(good_pack(), client=client)

    def test_pack_verdict_validator_rejections(self):
        ok, errors = validate_pack_verdict({"passed": "yes"})
        assert not ok and "'passed' must be a boolean" in errors
