# engines/audio-engine/assembly.py
#
# WHAT: The public audio assembly seam — synthesize speech segments and
#       silence, concatenate them into one WAV (+ optional MP3), behind a
#       single render_segments() interface.
# WHY:  P2.4 of docs/PRODUCTION_PLAN.md. Before this module, language-lab
#       imported four underscore-privates from podcast_audio, which in
#       turn imported _wav_to_mp3 from narration — the seam existed but
#       leaked its implementation. Narration, podcast rendering, and the
#       language lab now call THIS surface; WAV/PCM/MP3 mechanics are
#       internal (CONTEXT.md "Engine" boundary discipline).
# BREAKS IF DELETED: Segment parsing/silence/concat/MP3 logic scatters
#       back across three engines; cross-engine private imports return.

from __future__ import annotations

import logging
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

from model_layer.tts import TtsBackend, synthesize as tts_synthesize

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE = 22050  # Piper default
FFMPEG_PATH = "ffmpeg"

# A segment is either speech: (text, voice) or (text, voice, speed),
# or a gap: ("silence", duration_seconds).
Segment = tuple


@dataclass
class AudioResult:
    wav_bytes: bytes
    mp3_bytes: bytes
    duration_seconds: float
    sample_rate: int
    backend_used: TtsBackend


# ---------------------------------------------------------------------------
# WAV mechanics (implementation detail — not part of the seam)
# ---------------------------------------------------------------------------

def _make_wav_header(data_size: int, sample_rate: int = DEFAULT_SAMPLE_RATE) -> bytes:
    riff = b"RIFF" + struct.pack("<I", 36 + data_size) + b"WAVE"
    fmt = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate,
                                sample_rate * 2, 2, 16)
    return riff + fmt + b"data" + struct.pack("<I", data_size)


def generate_silence(duration_seconds: float, sample_rate: int = DEFAULT_SAMPLE_RATE) -> bytes:
    """Raw PCM silence (16-bit mono)."""
    return b"\x00" * (int(duration_seconds * sample_rate) * 2)


def _parse_wav_to_pcm(wav_bytes: bytes) -> tuple[bytes, int]:
    if len(wav_bytes) < 44:
        raise ValueError(f"Invalid WAV data: too short ({len(wav_bytes)} bytes)")
    # "WAVE" lives at bytes 8..11; comparing past offset 12 would reject
    # every real file (audit defect #3).
    if wav_bytes[:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
        raise ValueError("Invalid WAV format")
    sample_rate = struct.unpack("<I", wav_bytes[24:28])[0]
    offset = 12
    while offset < len(wav_bytes):
        chunk_id = wav_bytes[offset:offset + 4]
        chunk_size = struct.unpack("<I", wav_bytes[offset + 4:offset + 8])[0]
        if chunk_id == b"data":
            return wav_bytes[offset + 8:offset + 8 + chunk_size], sample_rate
        offset += 8 + chunk_size
    raise ValueError("WAV data chunk not found")


def concatenate(pcm_chunks: list[bytes], sample_rates: list[int]) -> tuple[bytes, int]:
    if not pcm_chunks:
        return b"", DEFAULT_SAMPLE_RATE
    rate = sample_rates[0] if sample_rates else DEFAULT_SAMPLE_RATE
    pcm = b"".join(pcm_chunks)
    return _make_wav_header(len(pcm), rate) + pcm, rate


def wav_to_mp3(wav_bytes: bytes) -> bytes:
    try:
        result = subprocess.run(
            [FFMPEG_PATH, "-i", "pipe:0", "-ab", "192k",
             "-ar", "22050", "-ac", "1", "-f", "mp3", "pipe:1"],
            input=wav_bytes,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"ffmpeg conversion failed: {e.stderr.decode() if e.stderr else 'Unknown error'}"
        ) from e
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found in PATH. Install ffmpeg or use WAV-only output.")


# ---------------------------------------------------------------------------
# The seam
# ---------------------------------------------------------------------------

def synthesize(
    text: str,
    voice: str,
    speed: float = 1.0,
    backend: Optional[TtsBackend] = None,
) -> tuple[bytes, int]:
    """One TTS call; returns (pcm_bytes, actual_sample_rate).

    backend=None lets model-layer apply its default (Piper today);
    callers with an explicit selection pass it through unchanged."""
    return _parse_wav_to_pcm(
        tts_synthesize(text, voice=voice, backend=backend, speed=speed)
    )


def render_segments(
    segments: list[Segment],
    *,
    include_mp3: bool = True,
    output_path: str | None = None,
    basename: str = "audio",
) -> AudioResult:
    """
    Contract: render an ordered list of speech/silence segments into a
    single audio artifact.

    Args:
        segments: (text, voice) or (text, voice, speed) for speech;
            ("silence", seconds) for gaps.
        include_mp3: attempt MP3 conversion; failure degrades to
            WAV-only with a warning rather than failing the render.
        output_path: directory to write `<basename>.wav` / `.mp3` into.
        basename: filename stem for written files.

    Returns:
        AudioResult with concatenated WAV, best-effort MP3, duration.

    Raises:
        ValueError: empty segment list or malformed WAV from backend.
        RuntimeError: TTS synthesis failure propagates to the caller.
    """
    if not segments:
        raise ValueError("No segments to render")

    pcm_chunks: list[bytes] = []
    rates: list[int] = []
    speech_count = 0

    for seg in segments:
        kind = seg[0]
        if isinstance(kind, str) and kind == "silence":
            duration = float(seg[1])
            rate = rates[-1] if rates else DEFAULT_SAMPLE_RATE
            pcm_chunks.append(generate_silence(duration, rate))
            rates.append(rate)
            continue
        text, voice = seg[0], seg[1]
        speed = float(seg[2]) if len(seg) > 2 else 1.0
        backend = seg[3] if len(seg) > 3 else None
        pcm, rate = synthesize(text, voice=voice, speed=speed, backend=backend)
        pcm_chunks.append(pcm)
        rates.append(rate)
        speech_count += 1

    wav_bytes, rate = concatenate(pcm_chunks, rates)
    duration = (len(wav_bytes) - 44) // 2 / rate

    mp3_bytes = b""
    if include_mp3:
        try:
            mp3_bytes = wav_to_mp3(wav_bytes)
        except RuntimeError as e:
            logger.warning("MP3 conversion failed, continuing WAV-only: %s", e)

    if output_path:
        out_dir = Path(output_path)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{basename}.wav").write_bytes(wav_bytes)
        if mp3_bytes:
            (out_dir / f"{basename}.mp3").write_bytes(mp3_bytes)

    return AudioResult(
        wav_bytes=wav_bytes,
        mp3_bytes=mp3_bytes,
        duration_seconds=duration,
        sample_rate=rate,
        backend_used=TtsBackend.PIPER,
    )
