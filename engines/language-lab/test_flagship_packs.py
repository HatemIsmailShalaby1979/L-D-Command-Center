# engines/language-lab/test_flagship_packs.py
#
# WHAT: Contract tests for the curated flagship-pack catalog.
# WHY:  The 30 packs (10 per focus language) are the app's marketing
#       artifacts (PROFIT_PLAN §6 Days 31-60) — the topic keys must be
#       stable across releases so shared links and community posts keep
#       working, and every prompt must be generation-ready (non-empty,
#       topic-shaped) so the batch generator never ships a broken demo.
# BREAKS IF DELETED: A renamed topic key silently breaks every shared
#       pack link; a hollow prompt ships a broken marketing artifact.

from __future__ import annotations

from engines.language_lab.flagship_packs import (
    FLAGSHIP_PACKS, FOCUS_LANGUAGES, flagship_topics_index,
    packs_for_language,
)


class TestCatalog:
    def test_three_focus_languages(self):
        assert FOCUS_LANGUAGES == ("es", "ja", "de")

    def test_ten_topics_per_focus_language(self):
        for lang in FOCUS_LANGUAGES:
            assert len(FLAGSHIP_PACKS[lang]) == 10, lang

    def test_keys_unique_and_stable(self):
        for lang in FOCUS_LANGUAGES:
            keys = [t.key for t in FLAGSHIP_PACKS[lang]]
            assert len(keys) == len(set(keys)), lang

    def test_every_topic_is_generation_ready(self):
        for lang in FOCUS_LANGUAGES:
            for topic in FLAGSHIP_PACKS[lang]:
                assert topic.title.strip()
                assert len(topic.prompt) >= 20, topic.key
                assert topic.pitch.strip()

    def test_localized_notes_override_where_relevant(self):
        de = {t.key: t for t in FLAGSHIP_PACKS["de"]}
        assert "Anmeldung" in de["banking-paperwork"].pitch
        ja = {t.key: t for t in FLAGSHIP_PACKS["ja"]}
        assert "keigo" in ja["first-week-work"].pitch

    def test_unknown_language_returns_empty(self):
        assert packs_for_language("xx") == ()
        assert packs_for_language("") == ()

    def test_index_covers_all_thirty(self):
        rows = flagship_topics_index()
        assert len(rows) == 30
        assert {"language", "key", "title", "prompt", "pitch"} == \
            set(rows[0].keys())
