# engines/language-lab/test_srs.py
#
# WHAT: Contract tests for SM-2 scheduling and SrsStore persistence.
# WHY:  Scheduling is arithmetic — every rule (ladder, ease adjustment,
#       lapse reset, floor) must be pinned or reviews silently drift.
#       Storage roundtrips prove progress survives restarts.
# BREAKS IF DELETED: Interval math regressions would starve or flood
#       the learner's review queue unnoticed.

from __future__ import annotations

from datetime import date

import pytest

from engines.language_lab.srs import (
    CardState,
    SrsStore,
    new_card,
    quality_from_correct,
    review,
)
from storage.persistence import Storage

TODAY = date(2026, 8, 25)


class TestSm2Core:
    def test_new_card_is_due_immediately(self):
        state = new_card()
        assert state.is_due(TODAY) and state.due is None

    def test_first_recall_one_day(self):
        state = review(new_card(), 5, today=TODAY)
        assert (state.repetitions, state.interval_days) == (1, 1)
        assert state.due == "2026-08-26"

    def test_second_recall_six_days(self):
        state = review(new_card(), 5, today=TODAY)
        state = review(state, 5, today=TODAY)
        assert (state.repetitions, state.interval_days) == (2, 6)

    def test_third_recalls_multiply_by_ease(self):
        state = review(review(review(new_card(), 5, today=TODAY), 4,
                              today=TODAY), 4, today=TODAY)
        # interval ladder: 1 -> 6 -> round(6 * ease); q=4 keeps ease 2.5
        assert state.interval_days == round(6 * state.ease)

    def test_ease_adjusts_by_quality(self):
        perfect = review(new_card(), 5, today=TODAY)
        assert perfect.ease == pytest.approx(2.6)      # +0.1
        ok = review(new_card(), 4, today=TODAY)
        assert ok.ease == pytest.approx(2.5)           # delta 0
        hard = review(new_card(), 3, today=TODAY)
        assert hard.ease == pytest.approx(2.36)        # -0.14

    def test_ease_floors_at_1_3(self):
        state = new_card()
        for _ in range(12):
            state = review(state, 3, today=TODAY)
            state = review(state, 0, today=TODAY)  # lapse: no ease change...
            state = review(state, 3, today=TODAY)  # recall: -0.14 each cycle
        assert state.ease >= 1.3

    def test_lapse_resets_schedule_and_counts(self):
        grown = review(review(new_card(), 5, today=TODAY), 5, today=TODAY)
        lapsed = review(grown, 2, today=TODAY)
        assert (lapsed.repetitions, lapsed.interval_days) == (0, 1)
        assert lapsed.lapses == 1
        assert lapsed.due == "2026-08-26"
        # and the ladder restarts from one day after recovery
        recovered = review(lapsed, 5, today=TODAY)
        assert recovered.interval_days == 1

    @pytest.mark.parametrize("bad", [-1, 6, 2.5, True, "3", None])
    def test_invalid_quality_rejected(self, bad):
        with pytest.raises(ValueError, match="quality"):
            review(new_card(), bad, today=TODAY)

    def test_quality_from_correct_mapping(self):
        assert quality_from_correct(True) == 5
        assert quality_from_correct(False) == 2


class TestCardStateRoundtrip:
    def test_to_from_dict_preserves_fields(self):
        state = review(new_card(), 4, today=TODAY)
        assert CardState.from_dict(state.to_dict()) == state

    def test_from_dict_ignores_unknown_keys(self):
        raw = {"ease": 2.5, "interval_days": 1, "repetitions": 1,
               "due": "2026-08-26", "future_field": "x"}
        state = CardState.from_dict(raw)
        assert not hasattr(state, "future_field")


@pytest.fixture
def store(tmp_path):
    return SrsStore(Storage(root=tmp_path))


class TestSrsStore:
    def test_unknown_card_returns_none(self, store):
        assert store.get("ghost") is None

    def test_review_persists_across_instances(self, tmp_path):
        SrsStore(Storage(root=tmp_path)).review("card-1", 5, today=TODAY)
        again = SrsStore(Storage(root=tmp_path)).get("card-1")
        assert again is not None and again.repetitions == 1

    def test_due_cards_includes_new_and_overdue_excludes_future(self, store):
        store.review("a", 5, today=TODAY)                    # due tomorrow
        store.review("b", 2, today=date(2026, 7, 1))         # long overdue
        store.review("c", 5, today=date(2026, 9, 15))        # future-dated
        due = store.due_cards(today=TODAY)
        assert due == ["b"]                                  # a: tomorrow; c: later

    def test_due_cards_sorted_for_stable_ordering(self, store):
        for cid in ("z", "m", "a"):
            store.review(cid, 2, today=date(2026, 7, 1))
        assert store.due_cards(today=TODAY) == ["a", "m", "z"]

    def test_forget_removes_card(self, store):
        store.review("card-1", 5, today=TODAY)
        store.forget("card-1")
        assert store.get("card-1") is None

    def test_all_states_roundtrip(self, store):
        store.review("k1", 5, today=TODAY)
        states = store.all_states()
        assert set(states) == {"k1"}
        assert isinstance(states["k1"], CardState)
