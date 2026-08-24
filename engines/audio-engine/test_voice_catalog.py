# engines/audio-engine/test_voice_catalog.py
#
# WHAT: Contract tests for the Voice Catalog — the single (language, role)
#       -> voice resolution point.
# WHY:  Every consumer (narration, podcast rendering, bilingual pairs)
#       resolves voices only through this module (CONTEXT.md), so these
#       tests pin fallback policy, speaker distinctness, and backend
#       routing for all of them at once.
# BREAKS IF DELETED: Voice resolution and English-fallback behavior are
#       unprotected across every audio consumer.

from __future__ import annotations

import logging

import pytest

from engines.audio_engine.voice_catalog import (
    FALLBACK_LANGUAGE,
    KOKORO_LANGUAGE_VOICES,
    PIPER_LANGUAGE_VOICES,
    PIPER_SPEAKER_POOL,
    has_language,
    narrator_voice,
    pair_voices,
    speaker_pool,
    speaker_voices,
)
from model_layer.tts import TtsBackend


class TestNarratorVoice:
    def test_english_piper_default(self):
        assert narrator_voice("en") == "en_US-lessac-medium"

    def test_piper_resolves_each_supported_language(self):
        for lang, voice in PIPER_LANGUAGE_VOICES.items():
            assert narrator_voice(lang) == voice

    def test_unknown_language_falls_back_to_english(self, caplog):
        with caplog.at_level(logging.WARNING):
            voice = narrator_voice("xx")
        assert voice == PIPER_LANGUAGE_VOICES[FALLBACK_LANGUAGE]
        assert "falling back" in caplog.text

    def test_explicit_kokoro_backend_routes_to_kokoro_table(self):
        assert narrator_voice("en", backend=TtsBackend.KOKORO) == "af_heart"

    def test_auto_backend_is_piper_while_kokoro_unimplemented(self):
        from model_layer.tts import KOKORO_IMPLEMENTED
        if not KOKORO_IMPLEMENTED:
            assert narrator_voice("en") == PIPER_LANGUAGE_VOICES["en"]


class TestPairVoices:
    def test_bilingual_pair_gets_two_language_voices(self):
        target, known = pair_voices("es", "en")
        assert target == "es_ES-carlos-medium"
        assert known == "en_US-lessac-medium"

    def test_pair_falls_back_per_side(self):
        target, known = pair_voices("zz", "en")
        assert target == PIPER_LANGUAGE_VOICES["en"]
        assert known == PIPER_LANGUAGE_VOICES["en"]

    def test_same_language_pair_returns_two_entries(self):
        a, b = pair_voices("en", "en")
        assert a == b  # same voice id is correct when languages match


class TestSpeakerVoices:
    def test_pool_is_distinct(self):
        pool = speaker_pool()
        assert len(pool) == len(set(pool))
        assert pool == PIPER_SPEAKER_POOL

    def test_count_within_pool_all_distinct(self):
        voices = speaker_voices(5)
        assert len(voices) == 5
        assert len(set(voices)) == 5

    def test_count_beyond_pool_stays_distinct(self):
        voices = speaker_voices(7)
        assert len(voices) == 7
        assert len(set(voices)) == 7
        assert voices[5].endswith("-6") and voices[6].endswith("-7")

    def test_zero_speakers_empty(self):
        assert speaker_voices(0) == []

    def test_lead_voice_matches_content_language(self):
        voices = speaker_voices(2, language="es")
        assert voices[0] == PIPER_LANGUAGE_VOICES["es"]
        assert voices[1] in PIPER_SPEAKER_POOL


class TestHasLanguage:
    def test_supported_and_unsupported(self):
        assert has_language("es") is True
        assert has_language("xx") is False

    @pytest.mark.parametrize("bad", ["", None])
    def test_blank_queries_use_fallback(self, bad):
        assert has_language(bad) is True  # en always exists
