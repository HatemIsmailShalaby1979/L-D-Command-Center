# engines/audio-engine/narration.py
#
# WHAT: Text-to-speech narration function that synthesizes text into audio
#       files (WAV + MP3) using the model-layer TTS client.
# WHY:  Provides a simple, unified interface for audio generation across
#       engines — takes any text (Journey cards, Resume summaries, or
#       arbitrary text) and produces audiobook-quality audio.
# BREAKS IF DELETED: Audio generation capability is lost; export-engine and
#       language-lab can't produce audio output.
#
# Backend selection strategy:
#   - Kokoro-82M is preferred when the language is known and supported
#     (English, Spanish, French, German, etc.) — it produces higher-quality
#     narration with better prosody.
#   - Piper is used as fallback for unsupported languages or when Kokoro
#     models aren't available.
#   - The user can override this by explicitly passing a backend.
#
# Audio output:
#   - WAV is written first (lossless, preserves all TTS output)
#   - MP3 is generated from WAV using ffmpeg (available in environment)
#   - Both formats are returned as bytes; optional file paths can be provided

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Add model-layer to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "model-layer"))

from tts import TtsBackend, synthesize


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Languages supported by Kokoro-82M (higher quality)
KOKORO_SUPPORTED_LANGUAGES = {
    "en", "english",
    "es", "spanish",
    "fr", "french",
    "de", "german",
    "it", "italian",
    "pt", "portuguese",
    "ru", "russian",
    "ja", "japanese",
    "zh", "chinese",
}

# Default voice mappings by language
DEFAULT_VOICES = {
    "en": "af_heart",  # Kokoro American English female
    "es": "bf_emma",   # Kokoro British English female (closest available)
    "fr": "bf_emma",   # Kokoro British English female (closest available)
    "de": "bm_george", # Kokoro British English male (closest available)
    "it": "bf_emma",   # Kokoro British English female (closest available)
    "pt": "bf_emma",   # Kokoro British English female (closest available)
    "ru": "bm_george", # Kokoro British English male (closest available)
    "ja": "bf_emma",   # Kokoro British English female (closest available)
    "zh": "bf_emma",   # Kokoro British English female (closest available)
}

DEFAULT_PIPER_VOICE = "en_US-lessac-medium"
DEFAULT_SAMPLE_RATE = 22050  # Hz (Piper default)
FFMPEG_PATH = "ffmpeg"  # Should be in PATH


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class NarrationResult:
    """Result of narration synthesis."""
    wav_bytes: bytes
    mp3_bytes: bytes
    sample_rate: int
    backend_used: TtsBackend
    voice_used: str


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _detect_language(text: str) -> str:
    """
    Detect the language of the input text.

    This is a simple heuristic based on character patterns. For production
    use, consider using a language detection library like langdetect.

    Returns:
        Language code (e.g., 'en', 'es', 'fr') or 'en' as fallback.
    """
    # Simple heuristic: check for common patterns
    # This is a placeholder — real implementation would use a library

    # Count character ranges
    latin_extended = sum(1 for c in text if 'Ā' <= c <= 'ſ')
    cyrillic = sum(1 for c in text if 'Ѐ' <= c <= 'ӿ')
    cjk = sum(1 for c in text if '一' <= c <= '鿿')
    arabic = sum(1 for c in text if '؀' <= c <= 'ۿ')
    hindi = sum(1 for c in text if 'ऀ' <= c <= 'ॿ')

    total = len(text.replace(' ', ''))
    if total == 0:
        return "en"

    ratios = {
        "cjk": cjk / total,
        "arabic": arabic / total,
        "hindi": hindi / total,
        "cyrillic": cyrillic / total,
        "latin_extended": latin_extended / total,
    }

    # Simple detection rules
    if ratios["cjk"] > 0.1:
        return "zh"
    elif ratios["arabic"] > 0.1:
        return "ar"
    elif ratios["hindi"] > 0.1:
        return "hi"
    elif ratios["cyrillic"] > 0.1:
        return "ru"
    elif ratios["latin_extended"] > 0.3:
        return "en"  # Default to English for mixed text
    else:
        return "en"  # Default to English


def _select_backend(text: str, backend: Optional[TtsBackend] = None) -> tuple[TtsBackend, str]:
    """
    Select the appropriate TTS backend and voice based on language.

    Args:
        text: Input text to narrate.
        backend: Optional explicit backend override.

    Returns:
        Tuple of (backend, voice) to use.
    """
    if backend:
        # User explicitly specified backend
        if backend == TtsBackend.KOKORO:
            lang = _detect_language(text)
            voice = DEFAULT_VOICES.get(lang, "af_heart")
            return backend, voice
        else:
            return backend, DEFAULT_PIPER_VOICE

    # Auto-select: prefer Kokoro for supported languages
    lang = _detect_language(text)

    if lang in KOKORO_SUPPORTED_LANGUAGES:
        voice = DEFAULT_VOICES.get(lang, "af_heart")
        return TtsBackend.KOKORO, voice
    else:
        # Fallback to Piper
        return TtsBackend.PIPER, DEFAULT_PIPER_VOICE


def _wav_to_mp3(wav_bytes: bytes) -> bytes:
    """
    Convert WAV audio bytes to MP3 using ffmpeg.

    Args:
        wav_bytes: WAV audio data.

    Returns:
        MP3 audio bytes.

    Raises:
        RuntimeError: If ffmpeg conversion fails.
    """
    import io

    # Write WAV to temp buffer
    wav_buffer = io.BytesIO(wav_bytes)

    # Create MP3 buffer
    mp3_buffer = io.BytesIO()

    try:
        # Use ffmpeg to convert WAV to MP3
        result = subprocess.run(
            [
                FFMPEG_PATH,
                "-i", "pipe:0",  # Read from stdin
                "-ab", "192k",   # 192kbps bitrate
                "-ar", "22050",  # Sample rate
                "-ac", "1",      # Mono
                "-f", "mp3",
                "pipe:1"         # Write to stdout
            ],
            stdin=wav_buffer,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"ffmpeg conversion failed: {e.stderr.decode() if e.stderr else 'Unknown error'}"
        ) from e
    except FileNotFoundError:
        raise RuntimeError(
            "ffmpeg not found in PATH. Install ffmpeg or use WAV-only output."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def narrate(
    text: str,
    *,
    backend: Optional[TtsBackend] = None,
    voice: Optional[str] = None,
    output_path: Optional[str] = None,
    include_mp3: bool = True,
    speed: float = 1.0,
) -> NarrationResult:
    """
    Synthesize text to audiobook audio (WAV + optional MP3).

    This is the main entry point for audio generation. It automatically
    selects the best backend based on the text's language.

    Args:
        text: The text to synthesize (can be a Journey card, Resume summary,
              or any arbitrary text).
        backend: Optional explicit backend override (TtsBackend.PIPER or
                 TtsBackend.KOKORO). If None, auto-selects based on language.
        voice: Optional explicit voice override. If None, uses the default
               voice for the selected backend and language.
        output_path: Optional directory path to save audio files. If provided,
                     WAV and MP3 files are written to this directory.
        include_mp3: Whether to generate MP3 in addition to WAV (default True).
        speed: Speech speed multiplier (0.5 to 2.0, default 1.0).

    Returns:
        NarrationResult containing WAV and MP3 bytes, sample rate, and
        the backend/voice actually used.

    Raises:
        ValueError: If text is empty.
        RuntimeError: If TTS synthesis or conversion fails.
    """
    if not text or not text.strip():
        raise ValueError("Text must be non-empty")

    # Select backend and voice
    selected_backend, selected_voice = _select_backend(text, backend)

    # Override voice if explicitly provided
    if voice:
        selected_voice = voice

    # Synthesize audio
    wav_bytes = synthesize(
        text,
        voice=selected_voice,
        backend=selected_backend,
        speed=speed,
    )

    # Generate MP3 if requested
    mp3_bytes = b""
    if include_mp3:
        try:
            mp3_bytes = _wav_to_mp3(wav_bytes)
        except RuntimeError as e:
            # Log warning but continue with WAV-only
            print(f"Warning: MP3 conversion failed: {e}")
            mp3_bytes = b""

    # Write to files if output_path provided
    if output_path:
        out_dir = Path(output_path)
        out_dir.mkdir(parents=True, exist_ok=True)

        wav_path = out_dir / "narration.wav"
        wav_path.write_bytes(wav_bytes)

        if mp3_bytes:
            mp3_path = out_dir / "narration.mp3"
            mp3_path.write_bytes(mp3_bytes)

    return NarrationResult(
        wav_bytes=wav_bytes,
        mp3_bytes=mp3_bytes,
        sample_rate=DEFAULT_SAMPLE_RATE,
        backend_used=selected_backend,
        voice_used=selected_voice,
    )


def narrate_journey_card(
    card: dict,
    *,
    include_mp3: bool = True,
    output_path: Optional[str] = None,
) -> NarrationResult:
    """
    Convenience function to narrate a Journey card.

    Args:
        card: Journey card dict with 'title' and 'content' fields.
        include_mp3: Whether to generate MP3 (default True).
        output_path: Optional directory to save audio files.

    Returns:
        NarrationResult with the synthesized audio.
    """
    # Combine title and content for narration
    text = f"{card.get('title', '')}. {card.get('content', '')}"
    return narrate(text, include_mp3=include_mp3, output_path=output_path)


def narrate_resume_summary(
    resume: dict,
    *,
    include_mp3: bool = True,
    output_path: Optional[str] = None,
) -> NarrationResult:
    """
    Convenience function to narrate a Resume's summary section.

    Args:
        resume: Resume dict with 'contact' and 'summary' fields.
        include_mp3: Whether to generate MP3 (default True).
        output_path: Optional directory to save audio files.

    Returns:
        NarrationResult with the synthesized audio.
    """
    name = resume.get("contact", {}).get("name", "Candidate")
    summary = resume.get("summary", "")
    text = f"Resume for {name}. {summary}"
    return narrate(text, include_mp3=include_mp3, output_path=output_path)
