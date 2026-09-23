# engines/audio-engine/test_mic.py
#
# WHAT: Contract tests for the microphone capture seam — device
#       enumeration, level callbacks, silence autostop, push-stop, and
#       the typed never-crash error taxonomy.
# WHY:  E.T.'s voice depends on this seam; a crash here kills the
#       conversation feature entirely. Every failure must degrade to
#       typing mode with actionable copy (owner directive: never
#       crash). Tests run headless with a FAKE sounddevice — no
#       microphone or PortAudio needed.
# BREAKS IF DELETED: A regression turns "no mic plugged in" into a
#       traceback instead of a friendly sentence.

from __future__ import annotations

import types

import numpy as np
import pytest

import engines.audio_engine.mic as mic


class FakeSdModule(types.SimpleNamespace):
    """Doubles the sounddevice module surface mic.py touches."""

    def __init__(self, devices, default_index=0, fail_open=False,
                 stream_blocks=None):
        super().__init__(
            query_devices=lambda: devices,
            InputStream=lambda **kw: FakeStream(fail_open,
                                                stream_blocks),
        )
        self.default = types.SimpleNamespace(device=(default_index,
                                                     -1))


class FakeStream:
    def __init__(self, fail_open, blocks):
        self.fail_open = fail_open
        self.blocks = list(blocks) if blocks else []
        self.closed = False

    def __enter__(self):
        if self.fail_open:
            raise PermissionError("device in use")
        return self

    def __exit__(self, *exc):
        self.closed = True
        return False

    def read(self, blocksize):
        if self.blocks:
            block = self.blocks.pop(0)
        else:
            block = np.zeros((blocksize, 1), dtype="float32")
        return block, False


def _install(monkeypatch, **kw):
    fake = FakeSdModule(**kw)
    monkeypatch.setattr(mic, "_sd", lambda: fake)
    return fake


DEVICES = [
    {"name": "Microphone (Test Mic)", "max_input_channels": 2,
     "default_samplerate": 44100},
    {"name": "Speakers", "max_input_channels": 0,
     "default_samplerate": 48000},
    {"name": "Line In", "max_input_channels": 2,
     "default_samplerate": 48000},
]


class TestDeviceEnumeration:
    def test_lists_only_input_devices(self, monkeypatch):
        _install(monkeypatch, devices=DEVICES, default_index=0)
        devices = mic.list_input_devices()
        assert [d.name for d in devices] == ["Microphone (Test Mic)",
                                             "Line In"]
        assert devices[0].index == 0
        assert devices[1].channels == 2

    def test_no_mic_returns_empty_list_not_error(self, monkeypatch):
        _install(monkeypatch, devices=[])
        assert mic.list_input_devices() == []

    def test_default_input_device_resolved(self, monkeypatch):
        _install(monkeypatch, devices=DEVICES, default_index=0)
        default = mic.default_input_device()
        assert default is not None and default.name == \
            "Microphone (Test Mic)"

    def test_missing_sounddevice_is_typed_error_with_copy(
            self, monkeypatch):
        # Go through the REAL _sd lazy-import path: uninstalling the
        # module makes the import fail inside _sd itself.
        import builtins
        real_import = builtins.__import__

        def blocked_import(name, *a, **kw):
            if name == "sounddevice":
                raise ImportError("no PortAudio")
            return real_import(name, *a, **kw)
        monkeypatch.setattr(builtins, "__import__", blocked_import)
        with pytest.raises(mic.NoMicrophoneError, match="type to E.T."):
            mic._sd()


class TestCapture:
    def test_speech_then_silence_autostops(self, monkeypatch):
        # 0.5s loud -> 2s silence => stops by "silence"
        loud = np.full((mic.blocksize if hasattr(mic, "blocksize")
                        else 1600, 1), 0.3, dtype="float32")
        quiet = np.zeros((1600, 1), dtype="float32")
        blocks = [loud] * 5 + [quiet] * 40
        _install(monkeypatch, devices=DEVICES, default_index=0,
                 stream_blocks=blocks)
        result = mic.capture_speech(max_seconds=10)
        assert result.stopped_by == "silence"
        assert result.duration_seconds > 1
        assert result.wav_bytes[:4] == b"RIFF"

    def test_push_to_stop_ends_immediately(self, monkeypatch):
        loud = np.full((1600, 1), 0.3, dtype="float32")
        _install(monkeypatch, devices=DEVICES, default_index=0,
                 stream_blocks=[loud] * 1000)
        stop_after = {"n": 0}

        def should_stop():
            stop_after["n"] += 1
            return stop_after["n"] > 3
        result = mic.capture_speech(max_seconds=30,
                                   should_stop=should_stop,
                                   silence_autostop=False)
        assert result.stopped_by == "push"

    def test_level_callback_receives_normalized_values(
            self, monkeypatch):
        loud = np.full((1600, 1), 0.2, dtype="float32")
        _install(monkeypatch, devices=DEVICES, default_index=0,
                 stream_blocks=[loud] * 3 + [np.zeros((1600, 1),
                                                      "float32")] * 50)
        levels = []
        result = mic.capture_speech(max_seconds=5,
                                    on_level=levels.append,
                                    silence_autostop=True)
        assert levels and any(v > 0.9 for v in levels)  # 0.2 RMS ~ full
        assert result.peak_level > 0

    def test_busy_device_is_typed_error_with_copy(self, monkeypatch):
        _install(monkeypatch, devices=DEVICES, default_index=0,
                 fail_open=True)
        with pytest.raises(mic.DeviceBusyError, match="busy"):
            mic.capture_speech(max_seconds=2)

    def test_no_devices_raises_friendly(self, monkeypatch):
        _install(monkeypatch, devices=[])
        with pytest.raises(mic.NoMicrophoneError,
                           match="type to E.T."):
            mic.capture_speech(max_seconds=2)

    def test_unknown_device_index_raises_friendly(self, monkeypatch):
        _install(monkeypatch, devices=DEVICES, default_index=0)
        with pytest.raises(mic.NoMicrophoneError, match="no longer"):
            mic.capture_speech(device=99, max_seconds=2)

    def test_level_callback_failure_never_kills_capture(
            self, monkeypatch):
        loud = np.full((1600, 1), 0.3, dtype="float32")

        def bad_callback(value):
            raise RuntimeError("UI exploded")
        _install(monkeypatch, devices=DEVICES, default_index=0,
                 stream_blocks=[loud] * 4 + [np.zeros((1600, 1),
                                                      "float32")] * 50)
        result = mic.capture_speech(max_seconds=5,
                                    on_level=bad_callback)
        assert result.wav_bytes[:4] == b"RIFF"  # survived the UI


class TestWavOutput:
    def test_output_is_16k_mono_pcm16_wav(self, monkeypatch):
        import soundfile as sf
        loud = np.full((1600, 1), 0.25, dtype="float32")
        _install(monkeypatch, devices=DEVICES, default_index=0,
                 stream_blocks=[loud] * 3 + [np.zeros((1600, 1),
                                                      "float32")] * 50)
        result = mic.capture_speech(max_seconds=4)
        import io
        data, rate = sf.read(io.BytesIO(result.wav_bytes),
                             dtype="float32")
        assert rate == mic.SAMPLE_RATE
        assert data.ndim == 1 or data.shape[1] == 1
        assert float(np.abs(data).max()) > 0.1  # the loud part is there
