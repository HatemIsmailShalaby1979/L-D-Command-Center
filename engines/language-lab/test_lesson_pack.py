# engines/language-lab/test_lesson_pack.py
#
# WHAT: Contract tests for whole-lesson pack generation (P7.2).
# WHY:  The flagship artifact must survive the Guardrail Loop — schema +
#       semantic validation with feedback retry — before any renderer or
#       grader touches it. These tests prove generation, retry recovery,
#       typed failure, and every validator rejection branch against a
#       scripted client; LM Studio never required.
# BREAKS IF DELETED: Malformed packs could flow into P7.3 graders and
#       the P7.4 renderer unguarded.

from __future__ import annotations

import json

import pytest

from engines.language_lab.lesson_pack import (
    EVALUATION_TYPES,
    LESSON_PACK_SCHEMA,
    generate_lesson_pack,
    validate_lesson_pack,
)
from model_layer.client import ModelResponse
from model_layer.prompts import PromptRegistry
from model_layer.schema import SchemaValidationError, _validate_object


# ---------------------------------------------------------------------------
# Fixtures: a known-good pack + scripted clients
# ---------------------------------------------------------------------------

def good_pack() -> dict:
    # Sized to the engine defaults (6 dialogue / 6 vocab / 3 grammar /
    # 5 eval) so scripted generation tests validate first try.
    return {
        "topic": "Ordering coffee",
        "target_language": "es",
        "known_language": "en",
        "level": "beginner",
        "dialogue": [
            {"speaker": "Ana", "content": "Buenos dias! Un cafe con leche, por favor."},
            {"speaker": "Luis", "content": "Claro. Algo mas?"},
            {"speaker": "Ana", "content": "Un croissant, por favor."},
            {"speaker": "Luis", "content": "Son cuatro euros."},
            {"speaker": "Ana", "content": "Aqui tiene. Gracias!"},
            {"speaker": "Luis", "content": "Hasta luego!"},
        ],
        "vocab_cards": [
            {"term": "el cafe", "reading": "el ka-FE", "translation": "coffee",
             "example": "Un cafe con leche, por favor."},
            {"term": "la cuenta", "reading": "la KWEN-ta", "translation": "the bill",
             "example": "La cuenta, por favor."},
            {"term": "el croissant", "reading": "el krwa-SAN", "translation": "croissant",
             "example": "Un croissant, por favor."},
            {"term": "gracias", "reading": "GRA-syas", "translation": "thanks",
             "example": "Muchas gracias!"},
            {"term": "por favor", "reading": "por fa-VOR", "translation": "please",
             "example": "Un cafe, por favor."},
            {"term": "la leche", "reading": "la LE-che", "translation": "milk",
             "example": "Con leche, por favor."},
        ],
        "grammar_cards": [
            {"point": "tener expressions", "explanation": "Use tener for hunger/thirst.",
             "drills": [
                 {"prompt": "Yo ___ sed.", "answer": "tengo"},
                 {"prompt": "___ hambre?", "answer": "Tienes"},
             ]},
            {"point": "por favor politeness", "explanation": "Softens any request.",
             "drills": [
                 {"prompt": "Un cafe, ___.", "answer": "por favor"},
                 {"prompt": "___ la cuenta.", "answer": "La cuenta, por favor"},
             ]},
            {"point": "present tense -ar", "explanation": "Hablar: hablo, hablas, habla.",
             "drills": [
                 {"prompt": "Yo ___ espanol.", "answer": "hablo"},
                 {"prompt": "Tu ___ ingles.", "answer": "hablas"},
             ]},
        ],
        "evaluation": [
            {"type": "multiple_choice", "question": "What does 'la cuenta' mean?",
             "options": ["the bill", "the coffee", "the window"], "correct_index": 0},
            {"type": "fill_in_blank", "sentence_with_blank": "Un cafe ___ leche, por favor.",
             "answer": "con"},
            {"type": "translation", "prompt": "See you later!", "answer": "Hasta luego!"},
            {"type": "transformation", "prompt": "Yo soy alto.",
             "answer": "Ella es alta."},
            {"type": "multiple_choice", "question": "Which is polite?",
             "options": ["Dame", "Por favor", "Oye"], "correct_index": 1},
        ],
    }


def good_part1() -> dict:
    """The dialogue+vocabulary half (what the part-1 call returns)."""
    pack = good_pack()
    return {"dialogue": pack["dialogue"],
            "vocab_cards": pack["vocab_cards"]}


def good_part2() -> dict:
    """The grammar+evaluation half (what the part-2 call returns)."""
    pack = good_pack()
    return {"grammar_cards": pack["grammar_cards"],
            "evaluation": pack["evaluation"]}


class ScriptedClient:
    """LmStudioClient stand-in returning queued responses in order."""

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


@pytest.fixture
def client():
    return ScriptedClient(good_part1(), good_part2())


# ---------------------------------------------------------------------------
# Generation through the Pipeline (two calls: dialogue+vocab, then
# grammar+evaluation — assembled and re-validated as one pack)
# ---------------------------------------------------------------------------

class TestGenerateLessonPack:
    def test_returns_validated_pack(self, client):
        pack = generate_lesson_pack(
            "Ordering coffee", "es", "en", "beginner", client=client)
        assert pack["topic"] == "Ordering coffee"
        assert len(pack["dialogue"]) == 6
        assert {s["speaker"] for s in pack["dialogue"]} == {"Ana", "Luis"}
        assert len(pack["vocab_cards"]) == 6
        assert len(pack["grammar_cards"]) == 3
        assert len(pack["evaluation"]) == 5
        ok, errors = validate_lesson_pack(pack)
        assert ok and not errors

    def test_two_sequential_calls_with_grounding(self):
        client = ScriptedClient(good_part1(), good_part2())
        generate_lesson_pack("Ordering coffee", "es", "en", "beginner",
                             client=client)
        assert len(client.requests) == 2
        # part 2 receives part 1's vocab terms as grounding context
        part2_user = client.requests[1].messages[-1]["content"]
        assert "el cafe" in part2_user and "la cuenta" in part2_user

    def test_forwards_language_level_counts_to_template(self, client):
        generate_lesson_pack("Tapas", "es", "en", "intermediate",
                             client=client)
        part1_user = client.requests[0].messages[-1]["content"]
        for fragment in ("Tapas", "Target language: es",
                         "Known language: en", "intermediate"):
            assert fragment in part1_user, fragment
        assert "exactly 6 cards" in part1_user  # default num_vocab
        part2_user = client.requests[1].messages[-1]["content"]
        assert "exactly 3 cards" in part2_user  # default num_grammar

    def test_retry_recovers_from_garbage(self):
        client = ScriptedClient("no json here at all", good_part1(),
                                good_part2())
        pack = generate_lesson_pack("Ordering coffee", "es", "en",
                                    "beginner", client=client)
        assert pack["vocab_cards"]
        retry_user = client.requests[1].messages[-1]["content"]
        assert "validation errors" in retry_user  # feedback loop fired

    def test_invalid_after_all_attempts_raises_typed_error(self):
        client = ScriptedClient("garbage", "still garbage", "garbage again")
        with pytest.raises(SchemaValidationError):
            generate_lesson_pack("Ordering coffee", "es", "en",
                                 "beginner", client=client)

    @pytest.mark.parametrize("kwargs", [
        {"topic": "   ", "target_language": "es", "known_language": "en"},
        {"topic": "t", "target_language": "", "known_language": "en"},
        {"topic": "t", "target_language": "es", "known_language": ""},
    ])
    def test_empty_inputs_raise_valueerror(self, kwargs):
        with pytest.raises(ValueError):
            generate_lesson_pack(client=ScriptedClient(), level="beginner", **kwargs)

    def test_request_parameters_match_structured_content_profile(self, client):
        generate_lesson_pack("Ordering coffee", "es", "en", "beginner", client=client)
        # two sequential calls (dialogue+vocab, then grammar+eval),
        # each with headroom for reasoning inside 8192-ctx servers
        assert len(client.requests) == 2
        for request in client.requests:
            assert request.max_tokens == 4096 and request.temperature == 0.3
        # 2026-09-07: split from one 8192 call — reasoning models
        # spiral deliberating over full packs (measured live: 4000+
        # thinking tokens, zero content); halves complete reliably.


# ---------------------------------------------------------------------------
# Validator guardrails
# ---------------------------------------------------------------------------

def _keep_only_first_speaker(pack):
    first = pack["dialogue"][0]["speaker"]
    pack["dialogue"] = [s for s in pack["dialogue"] if s["speaker"] == first]


def _make_all_one_speaker(pack):
    for seg in pack["dialogue"]:
        seg["speaker"] = pack["dialogue"][0]["speaker"]


class TestValidateLessonPack:
    def test_good_pack_passes(self):
        ok, errors = validate_lesson_pack(good_pack())
        assert ok and not errors

    def test_schema_engine_is_the_declared_source_of_truth(self):
        # The validator must be schema-driven: schema errors alone would
        # already reject a broken pack (drift guard, mirrors P1.4 fix).
        broken = good_pack()
        del broken["vocab_cards"]
        assert _validate_object(broken, LESSON_PACK_SCHEMA, "$")

    def test_non_dict_rejected(self):
        ok, errors = validate_lesson_pack(["list"])
        assert not ok and "JSON object" in errors[0]

    @pytest.mark.parametrize("mutate,fragment", [
        (lambda p: p.pop("vocab_cards"), "missing required field"),
        (lambda p: p.update(level="expert"), "not in enum"),
        (_keep_only_first_speaker, "exactly two distinct speakers"),
        (_make_all_one_speaker, "exactly two distinct speakers"),
        (lambda p: p["dialogue"][0].update(extra="field"), "unexpected field"),
        (lambda p: p["grammar_cards"][0]["drills"].pop(), "minimum is 2"),
        (lambda p: p["evaluation"].append({"type": "telepathy"}), "not in enum"),
    ])
    def test_mutations_fail_with_expected_fragment(self, mutate, fragment):
        pack = good_pack()
        mutate(pack)
        ok, errors = validate_lesson_pack(pack)
        assert not ok, f"expected rejection mentioning {fragment!r}"
        assert any(fragment in e for e in errors), errors


class TestEvaluationItemSemantics:
    def mc(self, **over):
        item = {"type": "multiple_choice", "question": "Q?",
                "options": ["a", "b", "c"], "correct_index": 1}
        item.update(over)
        return item

    def blank(self, **over):
        item = {"type": "fill_in_blank", "sentence_with_blank": "Yo ___ alto.",
                "answer": "soy"}
        item.update(over)
        return item

    def trans(self, **over):
        item = {"type": "translation", "prompt": "Hello", "answer": "Hola"}
        item.update(over)
        return item

    def _pack_with(self, items):
        pack = good_pack()
        pack["evaluation"] = items
        return pack

    def test_all_three_types_accepted(self):
        ok, errors = validate_lesson_pack(
            self._pack_with([self.mc(), self.blank(), self.trans()]))
        assert ok and not errors

    def test_correct_index_out_of_range(self):
        ok, errors = validate_lesson_pack(
            self._pack_with([self.mc(correct_index=3)]))
        assert not ok and any("out of range" in e for e in errors)

    def test_correct_index_bool_is_not_integer(self):
        ok, errors = validate_lesson_pack(
            self._pack_with([self.mc(correct_index=True)]))
        assert not ok and any("must be an integer" in e for e in errors)

    def test_fill_in_blank_requires_marker(self):
        ok, errors = validate_lesson_pack(
            self._pack_with([self.blank(sentence_with_blank="Yo soy alto.")]))
        assert not ok and any("___" in e for e in errors)

    def test_translation_missing_answer(self):
        ok, errors = validate_lesson_pack(
            self._pack_with([self.trans(answer="  ")]))
        assert not ok and any("missing answer" in e for e in errors)

    def test_errors_carry_item_index(self):
        _, errors = validate_lesson_pack(self._pack_with([self.trans(answer="")]))
        assert any(e.startswith("evaluation[0]:") for e in errors)


# ---------------------------------------------------------------------------
# Template registration
# ---------------------------------------------------------------------------

class TestTemplates:
    VARS = {
        "topic": "t", "target_language": "es", "known_language": "en",
        "level": "beginner", "difficulty": "beginner",
        "num_dialogue": 6, "num_vocab": 6,
        "num_grammar": 3, "num_eval": 5, "errors": "- x",
        "context_terms": "hola, gracias",
    }

    @pytest.mark.parametrize("name", ["lesson_pack_generate",
                                      "lesson_pack_retry",
                                      "lesson_pack_part2_generate",
                                      "lesson_pack_part1_retry",
                                      "lesson_pack_part2_retry"])
    def test_registered_and_renderable(self, name):
        system, user, _ = PromptRegistry().render(name, dict(self.VARS))
        assert system and user

    def test_generate_template_carries_part1_sections(self):
        _, user, _ = PromptRegistry().render(
            "lesson_pack_generate", dict(self.VARS))
        for section in ("dialogue", "vocab_cards"):
            assert section in user, section
        assert "grammar_cards" not in user  # part 2 lives elsewhere

    def test_part2_template_carries_part2_sections(self):
        _, user, _ = PromptRegistry().render(
            "lesson_pack_part2_generate", dict(self.VARS))
        for section in ("grammar_cards", "evaluation",
                        "listed words",
                        "multiple_choice", "fill_in_blank",
                        "translation", "transformation", "correct_index"):
            assert section in user, section

    def test_evaluation_types_are_stable_vocabulary(self):
        assert EVALUATION_TYPES == (
            "multiple_choice", "fill_in_blank", "translation",
            "transformation")


class TestPartValidators:
    def test_part1_accepts_matching_half(self):
        from engines.language_lab.lesson_pack import (
            validate_lesson_pack_part1,
        )
        ok, errors = validate_lesson_pack_part1(
            good_part1(), num_dialogue=6, num_vocab=6)
        assert ok, errors

    def test_part1_rejects_wrong_counts_and_single_speaker(self):
        from engines.language_lab.lesson_pack import (
            validate_lesson_pack_part1,
        )
        ok, errors = validate_lesson_pack_part1(
            {"dialogue": [{"speaker": "A", "content": "x"}],
             "vocab_cards": []}, num_dialogue=6, num_vocab=6)
        assert not ok and len(errors) >= 2

    def test_part2_accepts_matching_half(self):
        from engines.language_lab.lesson_pack import (
            validate_lesson_pack_part2,
        )
        ok, errors = validate_lesson_pack_part2(
            good_part2(), num_grammar=3, num_eval=5)
        assert ok, errors

    def test_part2_rejects_wrong_counts(self):
        from engines.language_lab.lesson_pack import (
            validate_lesson_pack_part2,
        )
        ok, errors = validate_lesson_pack_part2(
            {"grammar_cards": [], "evaluation": []},
            num_grammar=3, num_eval=5)
        assert not ok and len(errors) >= 2
