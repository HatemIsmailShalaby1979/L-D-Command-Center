# engines/audio-engine/test_et_voices.py
#
# WHAT: Contract tests for the E.T. voice machinery — persona voice
#       pairs per language and the pitch-shift differentiation
#       fallback for single-voice languages.
# WHY:  Mr. and Mrs. E.T. must sound reliably different. A language
#       with one Piper voice must still give the female persona a
#       distinct sound (pitch shift), and the pair table must never
#       silently break lesson/podcast rendering.
# BREAKS IF DELETED: Persona voices drift into "both aliens sound
#       identical" — the conversation illusion collapses.

from __future__ import annotations

import struct

import pytest

from engines.audio_engine.assembly import pitch_shift
from engines.audio_engine.voice_catalog import et_voice_pair


class TestEtVoicePairs:
    def test_english_has_real_male_female_pair(self):
        male, female, real = et_voice_pair("en")
        assert real is True
        assert male != female

    def test_german_has_real_pair(self):
        male, female, real = et_voice_pair("de")
        assert real is True
        assert "thorsten" in male

    def test_unpaired_language_falls_back_honestly(self):
        # e.g. Japanese: one voice, real_pair=False -> caller shifts
        male, female, real = et_voice_pair("ja")
        assert real is False
        assert male == female

    def test_unknown_language_uses_default_voice(self):
        male, female, real = et_voice_pair("xx")
        assert male  # never empty — conversation always has a voice

    def test_every_pair_entry_has_male_and_female(self):
        from engines.audio_engine.voice_catalog import (
            PIPER_LANGUAGE_VOICE_PAIRS,
        )
        for lang, pair in PIPER_LANGUAGE_VOICE_PAIRS.items():
            assert len(pair) == 2, lang
            assert all(isinstance(v, str) and v for v in pair), lang


def _tone_wav(freq=440.0, seconds=0.5, rate=22050):
    """A real WAV: header + 16-bit sine."""
    count = int(rate * seconds)
    samples = [int(12000 * __import__("math").sin(
        2 * 3.14159 * freq * i / rate)) for i in range(count)]
    pcm = struct.pack(f"<{count}h", *samples)
    riff = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
    fmt = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate,
                                rate * 2, 2, 16)
    return riff + fmt + b"data" + struct.pack("<I", len(pcm)) + pcm


class TestPitchShift:
    def test_zero_shift_returns_input_unchanged(self):
        wav = _tone_wav()
        assert pitch_shift(wav, 0.0) == wav

    def test_shift_changes_bytes_but_keeps_wav_shape(self):
        wav = _tone_wav()
        shifted = pitch_shift(wav, -3.0)
        assert shifted[:4] == b"RIFF"
        assert shifted != wav

    def test_shift_is_clamped(self):
        wav = _tone_wav()
        wild = pitch_shift(wav, -50.0)
        mild = pitch_shift(wav, -5.0)
        assert wild == mild  # clamped to the same safe ceiling

    def test_upward_shift_shortens_sample_count(self):
        # positive semitones = faster playback of same content
        wav = _tone_wav()
        up = pitch_shift(wav, 3.0)
        assert len(up) < len(wav)

    def test_round_trip_keeps_duration_shape(self):
        wav = _tone_wav()
        down = pitch_shift(wav, -2.0)
        back = pitch_shift(down, 2.0)
        assert abs(len(back) - len(wav)) <= 44 + 4  # ~same length
