# desktop-shell/test_controller_curriculum.py
#
# WHAT: Contract tests for the curriculum library controller seam.
# WHY:  Generation must auto-register, quota-gate BEFORE the expensive
#       LLM call, and persist progress; browsing must be instant and
#       never gated. These prove the library behaves like a library.
# BREAKS IF DELETED: Progress and packs drift apart — the library lies
#       about what the user has.

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


PACK = {
    "topic": "meeting people", "target_language": "es",
    "known_language": "en", "level": "a1",
    "dialogue": [{"speaker": "A", "content": "Hola"},
                  {"speaker": "B", "content": "¿Qué tal?"}],
    "vocab_cards": [{"term": "hola", "reading": "hola",
                     "translation": "hello",
                     "example": "Hola, me llamo Ana."}],
    "grammar_cards": [{"point": "ser", "explanation": "to be",
                        "drills": [{"prompt": "Yo ___ Ana.",
                                     "answer": "soy"},
                                    {"prompt": "x", "answer": "y"}]}],
    "evaluation": [{"type": "translation", "prompt": "hello",
                    "answer": "hola"}],
}


class TestBrowsing:
    def test_catalog_is_instant_and_ungated(self, storage):
        controller = ShellController(client=OkClient(), storage=storage)
        res = controller.curriculum_catalog("ja")
        assert res.ok
        kinds = [r["kind"] for r in res.payload]
        assert kinds.count("slot") == 30
        assert kinds.count("level") == 6  # a1..c1 + locked c2

    def test_unknown_language_still_renders(self, storage):
        controller = ShellController(client=OkClient(), storage=storage)
        assert controller.curriculum_catalog("xx").ok

    def test_next_lesson_is_a_ladder_pointer(self, storage):
        controller = ShellController(client=OkClient(), storage=storage)
        res = controller.curriculum_next_lesson("es")
        assert res.ok and res.payload["key"] == "a1-people_friends"


class TestGeneration:
    def test_generate_slot_produces_pack_html_and_registers(
            self, storage, monkeypatch):
        import engines.language_lab.lesson_pack as lp
        monkeypatch.setattr(lp, "generate_lesson_pack",
                            lambda topic, target, known, level, **kw:
                            dict(PACK, topic=topic))
        controller = ShellController(client=OkClient(), storage=storage)
        res = controller.curriculum_generate_slot("es",
                                                  "a1-people_friends")
        assert res.ok, res.detail
        assert res.payload["pack"] == "es-a1-people-friends.json"
        assert res.payload["quota"]["used"] == 1
        # registered in the library
        catalog = controller.curriculum_catalog("es")
        slot = [r for r in catalog.payload
                if r.get("key") == "a1-people_friends"][0]
        assert slot["status"] == "generated"
        # html exists in exports
        exports = controller.list_saved("exports")
        assert "es-a1-people-friends.html" in exports.payload

    def test_unknown_slot_is_friendly_input_error(self, storage):
        controller = ShellController(client=OkClient(), storage=storage)
        res = controller.curriculum_generate_slot("es", "nonsense")
        assert not res and res.error_kind == "input"
        assert "library" in res.detail

    def test_generate_gate_before_llm(self, storage, monkeypatch):
        controller = ShellController(client=FakeLm(), storage=storage)
        for _ in range(3):
            controller.licenses.consume("lesson_pack")
        calls = {"n": 0}

        def should_not_run(**kw):
            calls["n"] += 1
            raise RuntimeError("LLM must not run when gated")
        import engines.language_lab.lesson_pack as lp
        monkeypatch.setattr(lp, "generate_lesson_pack",
                            should_not_run)
        res = controller.curriculum_generate_slot("es",
                                                  "a1-people_friends")
        assert res.error_kind == "license"
        assert calls["n"] == 0

    def test_mark_done_updates_progress_and_next(self, storage):
        controller = ShellController(client=OkClient(), storage=storage)
        res = controller.curriculum_mark_done("es",
                                               "a1-people_friends", 88)
        assert res.ok
        assert res.payload["progress"] == 17
        assert res.payload["next"]["key"] == "a1-food_dining"

    def test_mark_done_rejects_unknown_slot(self, storage):
        controller = ShellController(client=OkClient(), storage=storage)
        res = controller.curriculum_mark_done("es", "fake", 50)
        assert not res and res.error_kind == "input"


class TestQuotaInterplay:
    def test_pro_key_generates_past_free_cap(self, storage, monkeypatch):
        from storage.licensing import issue_license
        import engines.language_lab.lesson_pack as lp
        monkeypatch.setattr(lp, "generate_lesson_pack",
                            lambda topic, target, known, level, **kw:
                            dict(PACK, topic=topic))
        controller = ShellController(client=OkClient(), storage=storage)
        controller.activate_license(issue_license("pro", licensee="A"))
        slots = ["a1-people_friends", "a1-food_dining",
                 "a1-transport_travel", "a1-shopping_money"]
        for slot in slots:
            assert controller.curriculum_generate_slot(
                "es", slot).ok
