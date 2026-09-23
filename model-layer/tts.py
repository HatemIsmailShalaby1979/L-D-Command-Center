# model-layer/tts.py
#
# WHAT: Text-to-speech client with multiple backends — Piper (default) and
#       Kokoro-82M (optional). Backend-agnostic interface: synthesize(text,
#       voice, language) -> audio bytes.
# WHY:  Provide a local, offline-first TTS capability at the model-layer tier
#       (same as LM Studio client), without depending on cloud services.
# BREAKS IF DELETED: Audio generation across export-engine, audio-engine, and
#       language-lab breaks.
#
# Licensing note (as of 2026-08):
#   - Piper (rhasspy/piper): MIT license for software; voice models are
#     individually licensed (many under Creative Commons or permissive
#     distribution). See https://github.com/rhasspy/piper
#   - Kokoro-82M (hexgrad/Kokoro): MIT license per the upstream repo.
#     Both backends are CPU-only capable.

from __future__ import annotations

import io
import wave
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TtsBackend(str, Enum):
    PIPER = "piper"
    KOKORO = "kokoro"


DEFAULT_BACKEND = TtsBackend.PIPER
DEFAULT_VOICE = "en_US-lessac-medium"  # Piper's default English voice
DEFAULT_LANGUAGE = "en"

# Single source of truth for Kokoro readiness. Flip to True only when
# _synthesize_kokoro gains a real tokenizer/phoneme encoder; until then
# every consumer (narration auto-select) must treat Kokoro as unavailable.
KOKORO_IMPLEMENTED = False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TtsConfig:
    """Configuration for TTS synthesis."""
    backend: TtsBackend = DEFAULT_BACKEND
    voice: str = DEFAULT_VOICE
    language: str = DEFAULT_LANGUAGE
    models_dir: Path = Path(__file__).parent.parent / "models" / "tts"
    speed: float = 1.0  # 0.5 = slow, 1.0 = normal, 2.0 = fast


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------

def _synthesize_piper(
    text: str,
    voice: str,
    language: str,
    models_dir: Path,
    speed: float,
) -> bytes:
    """
    Synthesize audio using the Piper backend (CPU-only, ONNX runtime).

    Piper loads voice models from a local directory. The voice parameter should
    be in the format 'language_COUNTRY-variant' (e.g., 'en_US-lessac-medium').

    Returns: WAV audio bytes (16-bit, 22050 Hz mono by default for most Piper
    voices; exact sample rate depends on the voice model).
    """
    try:
        from piper import PiperVoice, SynthesisConfig
    except ImportError as e:
        raise RuntimeError(
            "piper-tts package not installed. Run: pip install piper-tts"
        ) from e

    # Resolve model file path
    model_path = models_dir / f"{voice}.onnx"
    config_path = models_dir / f"{voice}.onnx.json"

    if not model_path.exists():
        raise FileNotFoundError(
            f"Piper voice model not found: {model_path}\n"
            f"Download voice models from https://huggingface.co/rhasspy/piper-voices"
        )

    # piper-tts >= 1.3: PiperVoice.synthesize_wav writes a complete WAV;
    # length_scale is the inverse of playback speed.
    piper_voice = PiperVoice.load(model_path, config_path)
    syn_config = SynthesisConfig(length_scale=1.0 / max(speed, 0.01))
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        piper_voice.synthesize_wav(text, wav_file, syn_config)
    return wav_buffer.getvalue()


def _synthesize_kokoro(
    text: str,
    voice: str,
    language: str,
    models_dir: Path,
    speed: float,
) -> bytes:
    """
    Synthesize audio using the Kokoro-82M backend.

    Kokoro-82M is a fixed-language TTS model. The voice parameter maps to a
    Kokoro voice ID (e.g., 'af_heart', 'af_bella', 'am_adam').

    Returns: WAV audio bytes (24000 Hz mono for Kokoro).
    """
    if not KOKORO_IMPLEMENTED:
        raise NotImplementedError(
            "Kokoro-82M backend requires additional setup (tokenizer, phoneme encoder).\n"
            "Use the Piper backend for now, or implement full Kokoro integration."
        )
    try:
        import torch
        import onnxruntime as ort
    except ImportError as e:
        raise RuntimeError(
            "Required packages not installed for Kokoro backend.\n"
            "Run: pip install torch onnxruntime"
        ) from e

    # Kokoro voice IDs — map from voice param to model file
    voice_to_model = {
        "af_heart": "kokoro-af-heart.onnx",
        "af_bella": "kokoro-af-bella.onnx",
        "am_adam": "kokoro-am-adam.onnx",
        "am_michael": "kokoro-am-michael.onnx",
        "bf_emma": "kokoro-bf-emma.onnx",
        "bm_george": "kokoro-bm-george.onnx",
    }

    model_name = voice_to_model.get(voice, "kokoro-af-heart.onnx")
    model_path = models_dir / model_name

    if not model_path.exists():
        raise FileNotFoundError(
            f"Kokoro voice model not found: {model_path}\n"
            f"Download from https://huggingface.co/Hexgrad/Kokoro-82M"
        )

    # Load ONNX model
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])

    # Tokenize and synthesize (simplified — real Kokoro uses a tokenizer)
    # For this implementation, we use the onnxruntime session directly
    # The actual tokenization would depend on the Kokoro model's requirements

    # Note: This is a placeholder for the Kokoro backend. A full implementation
    # would require the Kokoro tokenizer and phoneme encoder.
    # For now, we raise NotImplementedError and defer to Piper for production use.
    raise NotImplementedError(
        "Kokoro-82M backend requires additional setup (tokenizer, phoneme encoder).\n"
        "Use the Piper backend for now, or implement full Kokoro integration."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def synthesize(
    text: str,
    voice: Optional[str] = None,
    language: Optional[str] = None,
    backend: Optional[TtsBackend] = None,
    models_dir: Optional[Path] = None,
    speed: float = 1.0,
) -> bytes:
    """
    Synthesize text to audio bytes using the configured TTS backend.

    Args:
        text: The text to synthesize (must be non-empty).
        voice: Voice identifier (e.g., 'en_US-lessac-medium' for Piper).
               Defaults to DEFAULT_VOICE.
        language: Language code (e.g., 'en', 'es'). Used for validation.
        backend: TtsBackend enum value. Defaults to DEFAULT_BACKEND (Piper).
        models_dir: Directory containing voice model files.
        speed: Speech speed multiplier (0.5 to 2.0).

    Returns:
        WAV audio bytes.

    Raises:
        ValueError: If text is empty or voice/language is invalid.
        FileNotFoundError: If the voice model is not found.
        RuntimeError: If the backend is not available.
    """
    if not text or not text.strip():
        raise ValueError("Text must be non-empty")

    # Apply defaults
    voice = voice or DEFAULT_VOICE
    language = language or DEFAULT_LANGUAGE
    backend = backend or DEFAULT_BACKEND
    models_dir = models_dir or TtsConfig().models_dir

    # Dispatch to backend
    if backend == TtsBackend.PIPER:
        return _synthesize_piper(text, voice, language, models_dir, speed)
    elif backend == TtsBackend.KOKORO:
        return _synthesize_kokoro(text, voice, language, models_dir, speed)
    else:
        raise ValueError(f"Unknown TTS backend: {backend}")


def get_available_voices(backend: Optional[TtsBackend] = None, models_dir: Optional[Path] = None) -> list[str]:
    """
    Return a list of available voice identifiers for the given backend.

    Args:
        backend: TtsBackend to query. Defaults to DEFAULT_BACKEND.
        models_dir: Directory containing voice model files.

    Returns:
        List of voice identifiers (strings) that have model files.
    """
    models_dir = models_dir or TtsConfig().models_dir
    backend = backend or DEFAULT_BACKEND

    if not models_dir.exists():
        return []

    if backend == TtsBackend.PIPER:
        # Piper uses .onnx and .onnx.json pairs
        voices = set()
        for model_file in models_dir.glob("*.onnx"):
            voice_name = model_file.stem  # e.g., "en_US-lessac-medium"
            # Verify config file exists
            config_file = model_file.parent / f"{voice_name}.onnx.json"
            if config_file.exists():
                voices.add(voice_name)
        return sorted(voices)

    elif backend == TtsBackend.KOKORO:
        # Kokoro uses .onnx files with specific naming
        voices = []
        for model_file in models_dir.glob("kokoro-*.onnx"):
            voices.append(model_file.stem.replace("kokoro-", ""))
        return sorted(voices)

    return []


def generate_audio(
    text: str,
    output_path: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Convenience function: synthesize text to audio and optionally save to file.

    Args:
        text: Text to synthesize.
        output_path: Optional file path to save WAV audio.
        **kwargs: Passed to synthesize() (voice, language, backend, etc.)

    Returns:
        The output file path if output_path is provided, else "memory".
    """
    audio_bytes = synthesize(text, **kwargs)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(audio_bytes)
        return str(out)

    return "memory"
