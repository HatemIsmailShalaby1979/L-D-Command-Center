# engines/language-lab/test_cefr.py
#
# WHAT: Contract tests for the CEFR curriculum skeleton and the
#       library (catalog) store.
# WHY:  The library is the owner's core demand: a ready catalogue per
#       language, A1 to C1, pushing the user along a journey. These
#       tests pin: 5 levels + honest C2 badge, 6 deterministic slots
#       per level, stable keys, everyday-life breadth, progress
#       math, and the next-lesson pointer — all with ZERO LLM calls.
# BREAKS IF DELETED: A catalog change silently breaks every saved
#       progress record and marketing link (slot keys are forever).

from __future__ import annotations

import pytest

from engines.language_lab.catalog_store import CatalogStore
from engines.language_lab.cefr import (
    C2, LANGUAGES, LEVELS, TOPIC_DOMAINS, VERIFIED_LANGUAGES,
    catalog_index, level_focus, lesson_slots, slot_for,
)
from storage.persistence import Storage


@pytest.fixture
def storage(tmp_path):
    return Storage(root=tmp_path)


@pytest.fixture
def store(storage):
    return CatalogStore(storage)


class TestCefrSkeleton:
    def test_five_levels_then_locked_c2(self):
        assert LEVELS == ("a1", "a2", "b1", "b2", "c1")
        assert C2["locked"] is True
        assert "coming soon" in C2["title"].lower()

    def test_six_slots_per_level_with_stable_keys(self):
        for level in LEVELS:
            slots = lesson_slots(level)
            assert len(slots) == 6, level
            keys = [s.key for s in slots]
            assert len(set(keys)) == 6
            assert keys == [s.key for s in lesson_slots(level)]  # stable
        assert slot_for("b1-services_authorities") is not None
        assert slot_for("nonsense") is None

    def test_unknown_level_rejected(self):
        with pytest.raises(ValueError, match="Level"):
            lesson_slots("c3")

    def test_everyday_breadth_all_ten_domains_covered(self):
        seen = set()
        for level in LEVELS:
            for slot in lesson_slots(level):
                seen.add(slot.domain)
        assert seen == set(TOPIC_DOMAINS)  # every domain, every lang

    def test_titles_are_concrete_not_generic(self):
        for level in LEVELS:
            for slot in lesson_slots(level):
                # "Lesson 1" style laziness is banned: each title must
                # say something a learner would recognize from life
                assert len(slot.title) >= 15, slot.key
                assert not slot.title.lower().startswith("lesson")

    def test_topic_prompt_mentions_focus_and_grammar(self):
        slot = lesson_slots("b1")[0]
        prompt = slot.topic_prompt()
        assert slot.cefr_grammar in prompt
        assert "everyday" in prompt

    def test_catalog_index_renders_for_any_language_instantly(self):
        for language in ("en", "es", "ja", "de", "xx"):
            rows = catalog_index(language)
            kinds = [r["kind"] for r in rows]
            assert kinds.count("level") == 6  # a1..c1 + c2 badge
            assert kinds.count("slot") == 30
            c2_row = [r for r in rows if r.get("level") == "c2"][0]
            assert c2_row["locked"] is True

    def test_level_info_carries_the_humanized_lines(self):
        from engines.language_lab.cefr import LEVEL_INFO
        for level in LEVELS:
            assert LEVEL_INFO[level]["line"]  # the humor is mandatory

    def test_verified_and_full_language_rosters(self):
        assert set(VERIFIED_LANGUAGES) <= set(LANGUAGES)
        assert len(LANGUAGES) == 15


class TestCatalogStore:
    def test_todo_by_default(self, store):
        status = store.slot_status("es", "a1-people_friends")
        assert status == {"status": "todo", "score": None,
                          "pack_name": None}

    def test_generated_then_done_lifecycle(self, store):
        store.mark_generated("es", "a1-people_friends", "pack.json")
        assert store.slot_status(
            "es", "a1-people_friends")["status"] == "generated"
        store.mark_done("es", "a1-people_friends", 85)
        status = store.slot_status("es", "a1-people_friends")
        assert status["status"] == "done"
        assert status["score"] == 85

    def test_regeneration_never_downgrades_done(self, store):
        store.mark_done("es", "a1-people_friends", 90)
        store.mark_generated("es", "a1-people_friends", "new.json")
        status = store.slot_status("es", "a1-people_friends")
        assert status["status"] == "done"
        assert status["score"] == 90

    def test_level_progress_and_stats(self, store):
        assert store.level_progress("es", "a1") == 0
        store.mark_done("es", "a1-people_friends", 70)
        store.mark_done("es", "a1-food_dining", 80)
        # 2 of 6 slots done
        assert store.level_progress("es", "a1") == 33
        stats = store.stats("es")
        assert stats == {"total": 30, "done": 2, "generated": 2,
                         "language": "es"}

    def test_next_lesson_points_at_first_todo_in_ladder_order(
            self, store):
        nxt = store.next_lesson("es")
        assert nxt["key"] == "a1-people_friends"
        store.mark_done("es", "a1-people_friends", 100)
        nxt = store.next_lesson("es")
        assert nxt["key"] == "a1-food_dining"

    def test_next_lesson_prefers_generated_over_deeper_todo(
            self, store):
        # a generated-but-not-done slot wins over later todo ones
        store.mark_generated("es", "b1-work_school", "pack.json")
        nxt = store.next_lesson("es")
        assert nxt["key"] == "a1-people_friends"  # ladder order first

    def test_full_curriculum_returns_none(self, store):
        from engines.language_lab.cefr import LEVELS, lesson_slots
        for level in LEVELS:
            for slot in lesson_slots(level):
                store.mark_done("de", slot.key, 100)
        assert store.next_lesson("de") is None

    def test_catalog_index_merges_progress(self, store):
        store.mark_done("es", "a1-people_friends", 100)
        rows = store.catalog_index("es")
        done = [r for r in rows
                if r.get("key") == "a1-people_friends"][0]
        assert done["status"] == "done" and done["score"] == 100
        a1 = [r for r in rows
              if r.get("kind") == "level" and r.get("level") == "a1"][0]
        assert a1["progress"] == 17  # 1/6 rounds to 17

    def test_persistence_across_restart(self, storage, store):
        store.mark_done("es", "a1-people_friends", 75)
        revived = CatalogStore(storage)
        assert revived.slot_status(
            "es", "a1-people_friends")["score"] == 75

    def test_reset_slot(self, store):
        store.mark_done("es", "a1-people_friends", 75)
        store.reset_slot("es", "a1-people_friends")
        assert store.slot_status(
            "es", "a1-people_friends")["status"] == "todo"
