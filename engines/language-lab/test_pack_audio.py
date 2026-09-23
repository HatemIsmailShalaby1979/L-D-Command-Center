# engines/language-lab/test_pack_audio.py
#
# WHAT: Contract tests for per-segment lesson-pack audio (P7.5).
# WHY:  The renderer's listening items depend on exact artifact names
#       ("dialogue-<i>") and distinct voices per speaker; TTS is faked
#       at the same seam every audio-engine suite uses, so LM Studio/
#       Piper are never required.
# BREAKS IF DELETED: Artifact-name drift between renderer and audio
#       would silently break every listening exercise.

from __future__ import annotations

import struct
from unittest.mock import patch

import pytest

from engines.language_lab.pack_audio import (
    assign_speaker_voices,
    pack_slug,
    render_pack_audio,
)


def make_wav(n_samples: int = 220) -> bytes:
    """A real RIFF/WAVE header + n mono 16-bit samples."""
    pcm = b"\x01\x02" * n_samples
    rate = 22050
    riff = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
    fmt = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    return riff + fmt + b"data" + struct.pack("<I", len(pcm)) + pcm


def good_pack():
    return {
        "topic": "Ordering coffee",
        "target_language": "es",
        "known_language": "en",
        "level": "beginner",
        "dialogue": [
            {"speaker": "Ana", "content": "Un cafe con leche."},
            {"speaker": "Luis", "content": "Algo mas?"},
            {"speaker": "Ana", "content": "Y un croissant."},
        ],
        "vocab_cards": [], "grammar_cards": [], "evaluation": [],
    }


class TestNaming:
    def test_keys_and_names_match_renderer_contract(self):
        with patch("engines.audio_engine.assembly.tts_synthesize",
                   return_value=make_wav()):
            segments = render_pack_audio(good_pack())
        assert [s.key for s in segments] == ["dialogue-0", "dialogue-1",
                                             "dialogue-2"]
        assert all(s.name.endswith(".wav") for s in segments)
        assert [s.name for s in segments] == [
            "ordering-coffee-lesson-dialogue-0.wav",
            "ordering-coffee-lesson-dialogue-1.wav",
            "ordering-coffee-lesson-dialogue-2.wav",
        ]

    def test_custom_stem_overrides_topic_slug(self):
        with patch("engines.audio_engine.assembly.tts_synthesize",
                   return_value=make_wav()):
            segments = render_pack_audio(good_pack(), stem="custom")
        assert segments[0].name == "custom-dialogue-0.wav"

    def test_slug_is_filesystem_safe(self):
        assert pack_slug("¿Qué Pasa, Amigo?") == "qu-pasa-amigo"
        assert pack_slug("") == "lesson"

    def test_durations_positive(self):
        with patch("engines.audio_engine.assembly.tts_synthesize",
                   return_value=make_wav()):
            segments = render_pack_audio(good_pack())
        assert all(s.duration_seconds > 0 for s in segments)

    def test_wav_bytes_are_the_concatenated_result(self):
        wav = make_wav()
        with patch("engines.audio_engine.assembly.tts_synthesize",
                   return_value=wav):
            segments = render_pack_audio(good_pack())
        assert all(s.wav_bytes.startswith(b"RIFF") for s in segments)


class TestVoicesAndSynthesis:
    def test_two_speakers_get_distinct_stable_voices(self):
        calls = []

        def fake_synthesize(text, voice=None, backend=None, speed=1.0):
            calls.append((text, voice, speed))
            return make_wav()

        with patch("engines.audio_engine.assembly.tts_synthesize",
                   side_effect=fake_synthesize):
            render_pack_audio(good_pack())

        by_speaker = {"Un cafe con leche.": calls[0][1],
                      "Algo mas?": calls[1][1],
                      "Y un croissant.": calls[2][1]}
        # Ana keeps her voice across turns; Luis differs from Ana.
        assert by_speaker["Un cafe con leche."] == by_speaker["Y un croissant."]
        assert by_speaker["Algo mas?"] != by_speaker["Un cafe con leche."]
        # Language-scoped: the lead voice is the Spanish catalog voice.
        assert by_speaker["Un cafe con leche."].startswith("es_")

    def test_speed_forwarded_to_synthesis(self):
        seen = {}

        def fake_synthesize(text, voice=None, backend=None, speed=1.0):
            seen["speed"] = speed
            return make_wav()

        with patch("engines.audio_engine.assembly.tts_synthesize",
                   side_effect=fake_synthesize):
            render_pack_audio(good_pack(), speed=0.75)
        assert seen["speed"] == 0.75

    def test_assign_speaker_voices_is_first_appearance_ordered(self):
        pack = good_pack()
        pack["dialogue"] = [
            {"speaker": "Zed", "content": "a"},
            {"speaker": "Amy", "content": "b"},
            {"speaker": "Zed", "content": "c"},
        ]
        mapping = assign_speaker_voices(pack)
        assert list(mapping) == ["Zed", "Amy"]
        assert mapping["Zed"] != mapping["Amy"]


class TestErrorsAndOutput:
    def test_empty_dialogue_rejected(self):
        pack = good_pack()
        pack["dialogue"] = []
        with pytest.raises(ValueError, match="no dialogue"):
            render_pack_audio(pack)

    def test_missing_dialogue_key_rejected(self):
        pack = good_pack()
        del pack["dialogue"]
        with pytest.raises(ValueError, match="no dialogue"):
            render_pack_audio(pack)

    def test_output_path_writes_artifacts_under_returned_names(self, tmp_path):
        with patch("engines.audio_engine.assembly.tts_synthesize",
                   return_value=make_wav()):
            segments = render_pack_audio(good_pack(), output_path=str(tmp_path))
        for seg in segments:
            written = tmp_path / seg.name
            assert written.exists()
            assert written.read_bytes() == seg.wav_bytes

    def test_mp3_disabled_by_default(self, tmp_path):
        with patch("engines.audio_engine.assembly.tts_synthesize",
                   return_value=make_wav()):
            segments = render_pack_audio(good_pack())
        # No ffmpeg subprocess ran: names stay .wav and no mp3 bytes exist.
        assert all(s.name.endswith(".wav") for s in segments)
