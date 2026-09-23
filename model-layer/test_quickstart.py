# model-layer/test_quickstart.py
#
# WHAT: Contract tests for the tiny-model quick-start (PROFIT_PLAN §8,
#       risk #1).
# WHY:  The first-run hint is the top of the funnel: if it names a model
#       that does not fit the machine, or returns nothing at all, a new
#       install never generates its first pack.
# BREAKS IF DELETED: Silent regressions in the one piece of copy that
#       decides whether a new user gets running at all.

from __future__ import annotations

import pytest

from model_layer.quickstart import (
    QUICKSTART_MODELS, LM_STUDIO_SEARCH_URL, quickstart_hint,
    recommended_models,
)


class TestCatalog:
    def test_every_entry_is_instruct_tuned_and_sized(self):
        for model in QUICKSTART_MODELS:
            assert "instruct" in model["search"] or model["search"].endswith("-it")
            assert 3 <= model["params_b"] <= 12  # small-model policy
            assert model["min_ram_gb"] >= 4
            assert model["why"]

    def test_exactly_one_recommended_default(self):
        flags = [m["recommended"] for m in QUICKSTART_MODELS]
        assert flags.count(True) == 1

    def test_search_terms_are_lowercase_hub_friendly(self):
        for model in QUICKSTART_MODELS:
            assert model["search"] == model["search"].lower().strip()
            assert " " not in model["search"]


class TestRecommendations:
    def test_recommended_pick_comes_first(self):
        assert recommended_models()[0]["recommended"] is True

    def test_ram_filter_drops_models_that_will_not_fit(self):
        picks = recommended_models(ram_gb=8)
        assert all(m["min_ram_gb"] <= 8 for m in picks)
        assert len(picks) < len(QUICKSTART_MODELS)

    def test_tiny_machine_still_gets_a_concrete_pick(self):
        picks = recommended_models(ram_gb=1)
        assert len(picks) == 1
        assert picks[0]["params_b"] == min(m["params_b"]
                                           for m in QUICKSTART_MODELS)

    def test_no_filter_returns_whole_catalog(self):
        assert len(recommended_models()) == len(QUICKSTART_MODELS)

    def test_output_is_deterministic(self):
        assert recommended_models(ram_gb=16) == recommended_models(ram_gb=16)


class TestQuickstartHint:
    def test_hint_names_a_searchable_model_and_lm_studio(self):
        hint = quickstart_hint([])
        assert "LM Studio" in hint
        assert "qwen2.5-7b-instruct" in hint
        assert LM_STUDIO_SEARCH_URL in hint

    def test_hint_lists_alternatives(self):
        hint = quickstart_hint(None)
        assert "Alternatives:" in hint

    def test_hint_is_short_when_a_model_is_loaded(self):
        hint = quickstart_hint(["some-model"])
        assert "some-model" in hint
        assert len(hint.splitlines()) == 1

    def test_hint_respects_ram_when_known(self):
        hint = quickstart_hint([], ram_gb=4)
        assert "qwen2.5-3b-instruct" in hint
        assert "9b" not in hint

    @pytest.mark.parametrize("ram", [4, 8, 16, 64])
    def test_hint_never_empty(self, ram):
        assert quickstart_hint([], ram_gb=ram).strip()
