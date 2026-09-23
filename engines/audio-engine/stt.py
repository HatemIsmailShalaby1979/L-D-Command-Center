# engines/audio-engine/stt.py
#
# WHAT: The speech-to-text engine — faster-whisper, one lazy singleton,
#       one-time model download with progress, typed unavailability.
# WHY:  Project E.T.: the user speaks, E.T. listens. Whisper runs
#       fully offline on CPU (small footprint via int8 quantization)
#       — the same local-first privacy promise as the LLM and TTS.
#       Model choice is RAM-aware (tiny-int8 on low-RAM machines,
#       small-int8 otherwise) and downloads once into models/stt
#       exactly like Piper voices (runtime-provisioned, never bundled).
#       A missing/unloadable STT engine degrades E.T. to typing mode
#       with one honest status line — voice is an enhancement, never
#       a gate (owner directive: never crash, never block).
# BREAKS IF DELETED: E.T. cannot hear; speaking drills and the exam
#       speaking section have no input path.

from __future__ import annotations

import io
import logging
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "TranscriptResult", "SegmentResult", "SttUnavailableError",
    "SttDownloadError", "transcriber", "transcribe", "stt_ready",
    "ensure_stt_model", "STT_MODELS_DIR", "RAM_SMALL_GB",
]

# Where the Whisper weights live (mirrors models/tts for Piper).
STT_MODELS_DIR = Path(__file__).resolve().parent.parent / "models" \
    / "stt"

# tiny-int8: ~40 MB after download, runs on 4 GB machines.
# small-int8: ~460 MB, better accents; needs the breathing room.
RAM_SMALL_GB = 8
MODEL_TINY = "tiny"
MODEL_SMALL = "small"


class SttUnavailableError(Exception):
    """E.T.'s ears are not available. Copy is human: typing mode is
    always offered, nothing else in the app is affected."""


class SttDownloadError(SttUnavailableError):
    """The model download failed — offline or disk issues."""


@dataclass(frozen=True)
class SegmentResult:
    text: str
    avg_logprob: float
    no_speech_prob: float


@dataclass(frozen=True)
class TranscriptResult:
    """What E.T. heard. `clarity` normalizes avg_logprob (roughly
    -1.0..0 in practice) into a friendly 0..1 — used for the honest
    accent story and the beginner-kindness re-ask floor, never as a
    fake 'accent score'."""
    text: str
    language: str
    segments: tuple[SegmentResult, ...] = ()
    clarity: float = 0.0
    wpm: float = 0.0
    source: str = "whisper"


def _ram_gb() -> float:
    try:
        import psutil  # noqa: PLC0415
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:  # noqa: BLE001 — os fallback
        import os
        if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names:
            size = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
            return size / (1024 ** 3)
        return 16.0  # optimistic default: pick small-int8


def _model_name() -> str:
    return MODEL_TINY if _ram_gb() < RAM_SMALL_GB else MODEL_SMALL


def _model_dir() -> Path:
    return Path(str(STT_MODELS_DIR)) / _model_name()


def stt_ready() -> bool:
    """True when the model directory exists (download already done)."""
    return _model_dir().exists() and any(_model_dir().iterdir())


def _download_progress_hook(report: Optional[Callable[[float], None]],
                            so_far: list, total_list: list):
    def hook(block_count: int, block_size: int, total: int):
        so_far.append(block_count * block_size)
        if total > 0:
            total_list.append(total)
        if report is not None and total_list and total_list[-1]:
            try:
                report(min(1.0, so_far[-1] / total_list[-1]))
            except Exception:  # noqa: BLE001 — UI callback, non-fatal
                pass
    return hook


def ensure_stt_model(on_progress: Optional[Callable[[float], None]] = None
                     ) -> Path:
    """Contract: make sure the Whisper weights exist locally, downloading
    once if needed. Returns the model directory. Raises
    SttDownloadError with actionable copy on failure.

    faster-whisper downloads from the HuggingFace Hub itself; we only
    PRE-CHECK disk space and report readiness — the actual fetch
    happens on first transcriber() load. This function therefore (a)
    reports the need for a download honestly, (b) reserves nothing,
    and (c) never blocks: callers run it on a worker thread with the
    progress callback wired to the status line.
    """
    name = _model_name()
    directory = _model_dir()
    if directory.exists() and any(directory.exists() and p.is_file()
                                  for p in directory.rglob("*")
                                  if directory.exists()):
        return directory
    free_mb = _free_disk_mb(STT_MODELS_DIR)
    needed_mb = 400 if name == MODEL_SMALL else 80
    if free_mb is not None and free_mb < needed_mb:
        raise SttDownloadError(
            f"Not enough disk space for the speech model (~{needed_mb} "
            f"MB needed, {free_mb} MB free). Free some space and try "
            "again — typing to E.T. works meanwhile.")
    STT_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if on_progress is not None:
        on_progress(0.05)  # "starting download" signal
    logger.info("STT model %s will download on first use (~%d MB)",
                name, needed_mb)
    return directory


def _free_disk_mb(path: Path) -> Optional[int]:
    try:
        import shutil
        return shutil.disk_usage(str(path)).free // (1024 * 1024)
    except Exception:  # noqa: BLE001
        return None


def transcriber(*, model: Optional[str] = None,
                download_root: Optional[Path] = None):
    """Contract: the process-wide Whisper singleton. Lazy import — a
    missing faster-whisper install raises SttUnavailableError with
    typing-mode copy, never a crash. Model choice: explicit arg >
    RAM-aware default. Loads in ~5-25 s on first call (download on the
    very first ever); callers surface 'E.T. is waking his ears…'."""
    global _TRANSCRIBER, _TRANSCRIBER_MODEL
    try:
        from faster_whisper import WhisperModel  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 — wheel varies by platform
        raise SttUnavailableError(
            "E.T.'s ears (speech recognition) are not installed on "
            "this machine. You can still type to him — conversations "
            "work exactly the same.") from exc
    name = model or _model_name()
    root = Path(download_root) if download_root else STT_MODELS_DIR
    key = (name, str(root))
    if _TRANSCRIBER is None or _TRANSCRIBER_MODEL != key:
        logger.info("Loading Whisper %s (int8, CPU) from %s", name, root)
        try:
            _TRANSCRIBER = WhisperModel(name, device="cpu",
                                        compute_type="int8",
                                        download_root=str(root))
        except Exception as exc:  # noqa: BLE001 — network/disk errors
            raise SttDownloadError(
                f"E.T. could not fetch his speech model ({exc}). "
                "Check your connection and press his ear once more — "
                "typing works right now.") from exc
        _TRANSCRIBER_MODEL = key
    return _TRANSCRIBER


_TRANSCRIBER: Any = None
_TRANSCRIBER_MODEL: Optional[tuple] = None


def _clarity(avg_logprob: float) -> float:
    """avg_logprob (~ -1.0..0) -> friendly 0..1. -0.2 -> 0.8: clear;
    -0.8 -> 0.2: rough. Clamped; used for the re-ask floor (0.35)."""
    return max(0.0, min(1.0, 1.0 + avg_logprob))


def transcribe(wav_bytes: bytes, language: str,
               *, model: Any = None) -> TranscriptResult:
    """Contract: WAV bytes in, what-was-said out. Empty/garbled audio
    returns an EMPTY result (text='') — the conversation engine turns
    that into E.T. politely asking to repeat, not an error.

    Args:
        wav_bytes: 16 kHz mono PCM16 WAV (mic.py's universal format).
        language: target ISO-639-1 code — pinned so E.T. never answers
            the user in the wrong language.
        model: injectable transcriber (tests pass a fake).
    """
    import numpy as np
    import soundfile as sf

    if not wav_bytes:
        return TranscriptResult(text="", language=language)
    try:
        samples, rate = sf.read(io.BytesIO(wav_bytes), dtype="float32")
    except Exception as exc:  # noqa: BLE001 — corrupt audio is data
        logger.warning("Unreadable audio: %s", exc)
        return TranscriptResult(text="", language=language)
    if samples.ndim > 1:
        samples = samples[:, 0]
    if rate != 16000:
        # Resample by linear interpolation to 16 kHz (mic.py captures
        # 16k natively; this path serves injected/imported audio).
        import math
        out_len = int(len(samples) * 16000 / rate)
        if out_len == 0:
            return TranscriptResult(text="", language=language)
        positions = np.linspace(0.0, len(samples) - 1, out_len)
        low = positions.astype("int64")
        high = np.minimum(low + 1, len(samples) - 1)
        frac = (positions - low).astype("float32")
        samples = (samples[low] * (1 - frac) + samples[high] * frac
                   ).astype("float32")
    if float(np.abs(samples).max(initial=0.0)) < 1e-4:
        return TranscriptResult(text="", language=language)

    engine = model if model is not None else transcriber()
    try:
        raw_segments, info = engine.transcribe(samples, language=language,
                                               beam_size=1)
        segments = tuple(
            SegmentResult(text=(s.text or "").strip(),
                          avg_logprob=float(s.avg_logprob),
                          no_speech_prob=float(s.no_speech_prob))
            for s in raw_segments)
    except Exception as exc:  # noqa: BLE001 — engine failure is data
        logger.warning("Transcription failed: %s", exc)
        raise SttUnavailableError(
            "E.T. could not process that recording. Try again, or type "
            f"your answer — he hears text perfectly. ({exc})") from exc

    text = " ".join(s.text for s in segments).strip()
    active = [s for s in segments
              if s.text and s.no_speech_prob < 0.6]
    clarity = (_clarity(sum(s.avg_logprob for s in active) / len(active))
               if active else 0.0)
    duration = len(samples) / 16000.0
    words = len(text.split())
    wpm = round(words / duration * 60.0, 1) if duration > 0.5 else 0.0
    logger.info("Transcribed %d chars, clarity %.2f, %.0f wpm",
                len(text), clarity, wpm)
    return TranscriptResult(text=text, language=language,
                            segments=segments, clarity=clarity, wpm=wpm)
