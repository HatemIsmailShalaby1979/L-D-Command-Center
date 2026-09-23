# engines/audio-engine/mic.py
#
# WHAT: The microphone capture engine — the single seam every voice
#       feature (E.T. conversations, speaking drills, level-exam
#       speaking section) records through.
# WHY:  Project E.T. (2026-09-06 owner directive): interactive LIVE
#       audio conversation with the user's default system mic,
#       autodetected. sounddevice (PortAudio) gives device enumeration
#       + blocking capture; soundfile writes the WAV bytes E.T.'s
#       transcriber consumes. Capture runs on a worker thread with a
#       live level callback so the UI can pulse without freezing —
#       the app's never-freeze contract applies to audio too.
#       Typed errors carry actionable copy: a missing mic degrades
#       E.T. to typing mode, never a crash (CONSTITUTION-style
#       honesty: failures-as-data).
# BREAKS IF DELETED: No voice input path exists anywhere in the app;
#       E.T. becomes keyboard-only; the speaking skill is unmeasurable.

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "AudioDevice", "MicrophoneError", "NoMicrophoneError",
    "DeviceBusyError", "CaptureResult", "list_input_devices",
    "default_input_device", "capture_speech",
    "SPEECH_LEVEL", "SPEECH_MIN_SECONDS", "SILENCE_STOP_SECONDS",
    "SAMPLE_RATE",
]

# Target speech format: 16 kHz mono float32 — what faster-whisper
# consumes without resampling; PortAudio handles the device-side rate.
SAMPLE_RATE = 16000
CHANNELS = 1

# Silence-autostop tuning: after SPEECH_MIN_SECONDS of actual speech,
# SILENCE_STOP_SECONDS below the level floor ends capture. Generous by
# design — a hesitant learner must never be cut off mid-thought.
SPEECH_LEVEL = 0.025          # RMS floor that counts as speech
SPEECH_MIN_SECONDS = 0.8      # speech must start within this window…
SILENCE_STOP_SECONDS = 1.6    # …then this much silence stops capture
MIN_FREE_DISK_MB = 100        # sanity floor before long captures


class MicrophoneError(Exception):
    """Base: every mic failure carries an actionable user sentence."""


class NoMicrophoneError(MicrophoneError):
    def __init__(self, message: str = ""):
        super().__init__(
            message or "No microphone was found on this machine. "
            "Connect one — or type to E.T. instead; the conversation "
            "never stops.")


class DeviceBusyError(MicrophoneError):
    def __init__(self, device: object = None, message: str = ""):
        self.device = device
        super().__init__(
            message or f"Microphone {device!r} is busy — another app "
            "is using it. Close it, or pick a different input in "
            "E.T.'s mic menu.")


@dataclass(frozen=True)
class AudioDevice:
    """One enumerable input device (index is PortAudio's)."""
    index: int
    name: str
    channels: int
    default_sample_rate: int


@dataclass(frozen=True)
class CaptureResult:
    """One finished recording. wav_bytes is 16-bit PCM mono 16 kHz —
    the app's universal speech artifact (STT input, drill save,
    session persistence)."""
    wav_bytes: bytes
    duration_seconds: float
    peak_level: float
    stopped_by: str          # "push" | "silence" | "timeout"
    device: str = ""


def _sd():
    """Import sounddevice lazily so headless test runs never need
    PortAudio; a missing install degrades to a typed error."""
    try:
        import sounddevice  # noqa: PLC0415 — deliberate lazy import
    except Exception as exc:  # noqa: BLE001 — install issues vary by OS
        raise NoMicrophoneError(
            f"Audio support is not installed ({exc}). Install it and "
            "restart — or type to E.T.; nothing is lost.") from exc
    return sounddevice


def list_input_devices() -> list[AudioDevice]:
    """Contract: every input device PortAudio can open, in system
    order. Empty list = no microphone at all (E.T. goes typing-only)."""
    sd = _sd()
    devices: list[AudioDevice] = []
    try:
        for index, raw in enumerate(sd.query_devices()):
            if not isinstance(raw, dict):
                continue
            if int(raw.get("max_input_channels") or 0) <= 0:
                continue
            devices.append(AudioDevice(
                index=index,
                name=str(raw.get("name") or f"Input {index}"),
                channels=int(raw.get("max_input_channels") or 1),
                default_sample_rate=int(raw.get("default_samplerate")
                                        or SAMPLE_RATE),
            ))
    except Exception as exc:  # noqa: BLE001 — driver weirdness is data
        logger.warning("Device enumeration failed: %s", exc)
        return []
    logger.info("Found %d input device(s)", len(devices))
    return devices


def default_input_device() -> Optional[AudioDevice]:
    """The system default input, if PortAudio reports one."""
    sd = _sd()
    try:
        index = sd.default.device[0]
    except Exception:  # noqa: BLE001 — no default configured
        return None
    if index is None or index < 0:
        return None
    for device in list_input_devices():
        if device.index == int(index):
            return device
    return None


def _rms(block) -> float:
    """RMS of one capture block, normalized 0-1 for the level callback.
    float32 samples expected; other dtypes are coerced."""
    try:
        import numpy as np
        arr = np.asarray(block, dtype="float32")
        if arr.ndim > 1:
            arr = arr[:, 0]
        return float(np.sqrt((arr * arr).mean())) if arr.size else 0.0
    except Exception:  # noqa: BLE001 — numpy is a hard dep of stt anyway
        return 0.0


def _to_wav_pcm16(samples) -> bytes:
    """float32 samples -> 16-bit PCM mono 16 kHz WAV bytes."""
    import io

    import numpy as np
    import soundfile as sf
    arr = np.asarray(samples, dtype="float32")
    if arr.ndim > 1:
        arr = arr[:, 0]
    clipped = np.clip(arr, -1.0, 1.0)
    buffer = io.BytesIO()
    sf.write(buffer, clipped, SAMPLE_RATE, format="WAV",
             subtype="PCM_16")
    return buffer.getvalue()


def capture_speech(
    *,
    device: Optional[int] = None,
    max_seconds: float = 90.0,
    silence_autostop: bool = True,
    on_level: Optional[Callable[[float], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    blocksize: int = 1600,
) -> CaptureResult:
    """Contract: record until the caller says stop (push-to-talk via
    `should_stop`), silence autostop fires, or max_seconds elapses.

    Runs on the CALLER's thread (controller wraps it in run_async) so
    the UI thread never blocks. `on_level(0.0-1.0)` fires ~10x/second
    with the current RMS for the record-pulse UI. `should_stop` is
    polled between blocks — the Stop button sets a flag and capture
    ends cleanly within ~100 ms.

    Args:
        device: PortAudio input index; None = system default.
        max_seconds: hard ceiling for one utterance.
        silence_autostop: end capture after SILENCE_STOP_SECONDS of
            quiet, once speech has started (SPEECH_MIN_SECONDS).
        on_level: live RMS callback (already UI-safe numbers).
        should_stop: caller-controlled stop flag/predicate.
        blocksize: samples per read (100 ms at 16 kHz).

    Raises:
        NoMicrophoneError: no input device exists at all.
        DeviceBusyError: the chosen device cannot be opened.
    """
    sd = _sd()
    devices = list_input_devices()
    if not devices:
        raise NoMicrophoneError()
    chosen_index = device
    if chosen_index is None:
        default = default_input_device()
        chosen_index = default.index if default else devices[0].index
        device_name = default.name if default else devices[0].name
    else:
        match = [d for d in devices if d.index == int(chosen_index)]
        if not match:
            raise NoMicrophoneError(
                f"That microphone (input {chosen_index}) is no longer "
                "connected. Pick another one in E.T.'s mic menu.")
        device_name = match[0].name

    blocks: list = []
    max_blocks = int(max_seconds * SAMPLE_RATE / blocksize)
    speech_started_at: Optional[float] = None
    last_speech_at: Optional[float] = None
    peak = 0.0
    stopped_by = "timeout"
    # Silence timing runs on SAMPLE COUNTS, not wall time: capture speed
    # varies with machine load, but 1.6s of samples is 1.6s of silence
    # everywhere (and fake-stream tests need no sleep tricks).
    seconds_per_block = blocksize / SAMPLE_RATE

    class _CtxStream:
        """Wrap the raw stream so BOTH constructor and __enter__
        failures become DeviceBusyError (PortAudio opens lazily on
        enter on some drivers)."""
        def __init__(self, raw):
            self._raw = raw

        def __enter__(self):
            try:
                self._handle = self._raw.__enter__()
            except Exception as exc:  # noqa: BLE001
                raise DeviceBusyError(device=chosen_index) from exc
            return self

        def __exit__(self, *exc):
            return self._raw.__exit__(*exc)

        def read(self, blocksize):
            return self._raw.read(blocksize)

    try:
        raw_stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32",
            blocksize=blocksize, device=int(chosen_index))
    except Exception as exc:  # noqa: BLE001 — PortAudio error shapes vary
        raise DeviceBusyError(device=chosen_index) from exc

    with _CtxStream(raw_stream) as stream:
        speech_seconds = 0.0     # total samples seen, in seconds
        silence_seconds = 0.0    # seconds since last speech block
        for _ in range(max_blocks):
            if should_stop is not None and should_stop():
                stopped_by = "push"
                break
            block, _ = stream.read(blocksize)
            level = _rms(block)
            peak = max(peak, level)
            if on_level is not None:
                try:
                    on_level(min(1.0, level / 0.15))
                except Exception:  # noqa: BLE001 — UI callback must not kill audio
                    logger.debug("on_level callback failed", exc_info=True)
            blocks.append(block)
            elapsed = speech_seconds + silence_seconds
            if level >= SPEECH_LEVEL:
                speech_seconds += seconds_per_block
                silence_seconds = 0.0
                speech_started_at = True
            else:
                silence_seconds += seconds_per_block
            if (silence_autostop
                    and speech_started_at
                    and silence_seconds >= SILENCE_STOP_SECONDS):
                # Real speech happened, then a full silence window:
                # the utterance is over. Hesitation mid-sentence never
                # trips this — SPEECH_LEVEL is a whisper-low floor.
                stopped_by = "silence"
                break
            if elapsed >= max_seconds:
                stopped_by = "timeout"
                break

    duration = round(sum(len(b) for b in blocks) / SAMPLE_RATE, 2)
    if blocks and hasattr(blocks[0], "tobytes"):
        samples = b"".join(b.tobytes() for b in blocks)
    else:
        samples = b""
    wav = _to_wav_pcm16(
        __import__("numpy").frombuffer(samples, dtype="float32")
        if samples else [])
    logger.info("Captured %.1fs from %r (peak %.3f, stopped by %s)",
                duration, device_name, peak, stopped_by)
    return CaptureResult(wav_bytes=wav, duration_seconds=duration,
                         peak_level=peak, stopped_by=stopped_by,
                         device=device_name)
