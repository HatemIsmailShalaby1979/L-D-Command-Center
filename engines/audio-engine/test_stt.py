# engines/audio-engine/test_stt.py
#
# WHAT: Contract tests for the speech-to-text seam — RAM-aware model
#       choice, clarity/WPM math, empty-audio kindness, and the typed
#       unavailable/download errors that keep E.T. typing-friendly.
# WHY:  E.T.'s entire evaluation path depends on honest transcription
#       quality signals; a crash here kills voice conversations.
#       All tests use FAKE models — no Whisper weights are downloaded.
# BREAKS IF DELETED: A regression turns "no STT model" into a crash
#       instead of typing mode.

from __future__ import annotations

import io
from types import SimpleNamespace as SN

import numpy as np
import pytest
import soundfile as sf

import engines.audio_engine.stt as stt


def wav_bytes(samples, rate=16000):
    buffer = io.BytesIO()
    sf.write(buffer, np.asarray(samples, dtype="float32"), rate,
             format="WAV", subtype="PCM_16")
    return buffer.getvalue()


class FakeSegment:
    def __init__(self, text, avg_logprob=-0.2, no_speech_prob=0.05):
        self.text = text
        self.avg_logprob = avg_logprob
        self.no_speech_prob = no_speech_prob


class FakeModel:
    def __init__(self, segments, info=None):
        self.segments = segments
        self.info = info or SN(language="de", duration=2.0)

    def transcribe(self, samples, language=None, beam_size=None):
        return iter(self.segments), self.info


@pytest.fixture(autouse=True)
def reset_singleton(monkeypatch):
    monkeypatch.setattr(stt, "_TRANSCRIBER", None)
    monkeypatch.setattr(stt, "_TRANSCRIBER_MODEL", None)


class TestModelChoice:
    def test_small_ram_uses_tiny(self, monkeypatch):
        monkeypatch.setattr(stt, "_ram_gb", lambda: 4.0)
        assert stt._model_name() == stt.MODEL_TINY

    def test_big_ram_uses_small(self, monkeypatch):
        monkeypatch.setattr(stt, "_ram_gb", lambda: 32.0)
        assert stt._model_name() == stt.MODEL_SMALL

    def test_model_dir_lives_under_models_stt(self):
        assert stt.STT_MODELS_DIR.name == "stt"
        assert stt.STT_MODELS_DIR.parent.name == "models"


class TestTranscription:
    def test_clear_speech_gets_text_and_clarity(self):
        samples = np.full(16000 * 2, 0.2, "float32")
        model = FakeModel([
            FakeSegment("Guten Morgen!", avg_logprob=-0.2),
            FakeSegment("Wie geht es dir?", avg_logprob=-0.4),
        ])
        result = stt.transcribe(wav_bytes(samples), "de", model=model)
        assert result.text == "Guten Morgen! Wie geht es dir?"
        assert 0.5 < result.clarity < 1.0
        assert result.language == "de"
        assert result.wpm > 0

    def test_empty_wav_returns_empty_not_error(self):
        result = stt.transcribe(b"", "de")
        assert result.text == ""
        assert result.clarity == 0.0

    def test_silence_returns_empty(self):
        result = stt.transcribe(wav_bytes(np.zeros(16000, "float32")),
                               "de")
        assert result.text == ""  # no model call even needed

    def test_garbage_audio_returns_empty(self):
        result = stt.transcribe(b"not a wav at all", "de",
                                model=FakeModel([]))
        assert result.text == ""

    def test_high_no_speech_segments_excluded_from_clarity(self):
        samples = np.full(16000 * 2, 0.2, "float32")
        model = FakeModel([
            FakeSegment("real words", avg_logprob=-0.1,
                        no_speech_prob=0.01),
            FakeSegment("[hum]", avg_logprob=-0.9,
                        no_speech_prob=0.9),   # filtered from clarity
        ])
        result = stt.transcribe(wav_bytes(samples), "de", model=model)
        assert result.clarity > 0.8

    def test_engine_failure_is_typed_error_with_copy(self):
        class Exploding:
            def transcribe(self, *a, **kw):
                raise RuntimeError("onnx crashed")
        samples = np.full(16000, 0.2, "float32")
        with pytest.raises(stt.SttUnavailableError,
                           match="type"):
            stt.transcribe(wav_bytes(samples), "de",
                           model=Exploding())

    def test_missing_faster_whisper_is_typed_error(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def blocked(name, *a, **kw):
            if name == "faster_whisper":
                raise ImportError("not installed")
            return real_import(name, *a, **kw)
        monkeypatch.setattr(builtins, "__import__", blocked)
        with pytest.raises(stt.SttUnavailableError,
                           match="type to him"):
            stt.transcriber()

    def test_resamples_44100_input(self):
        # mic.py always captures 16k, but injected audio at other rates
        # (e.g. user imports a file) must still work.
        samples = np.full(44100 * 2, 0.2, "float32")
        model = FakeModel([FakeSegment("hello")])
        result = stt.transcribe(wav_bytes(samples, rate=44100), "en",
                                model=model)
        assert result.text == "hello"


class TestClarityMath:
    def test_logprob_neg_02_is_high_clarity(self):
        assert stt._clarity(-0.2) == pytest.approx(0.8)

    def test_clarity_clamped(self):
        assert stt._clarity(-5.0) == 0.0
        assert stt._clarity(0.5) == 1.0


class TestDiskGuard:
    def test_low_disk_is_typed_error_with_copy(self, monkeypatch, tmp_path):
        monkeypatch.setattr(stt, "STT_MODELS_DIR", tmp_path / "stt")
        monkeypatch.setattr(stt, "_free_disk_mb", lambda p: 10)
        with pytest.raises(stt.SttDownloadError, match="disk space"):
            stt.ensure_stt_model()

    def test_ready_when_model_dir_populated(self, monkeypatch, tmp_path):
        directory = (tmp_path / "stt" / stt._model_name())
        directory.mkdir(parents=True)
        (directory / "model.bin").write_bytes(b"x")
        monkeypatch.setattr(stt, "STT_MODELS_DIR", tmp_path / "stt")
        assert stt.stt_ready() is True
