# engines/audio-engine/voice_catalog.py
#
# WHAT: The Voice Catalog — the one table mapping (language, role) to a
#       concrete TTS voice, per backend.
# WHY:  Before P2.3 voice knowledge lived in four places with two disjoint
#       vocabularies (Kokoro ids in narration, Piper names in
#       podcast_audio/bilingual). CONTEXT.md: Narration and podcast
#       rendering resolve voices ONLY through this module, so adding a
#       language or swapping a voice is a one-table change.
# BREAKS IF DELETED: Voice tables scatter back across engines; a missing
#       language silently degrades to English in three places instead of
#       one, and provisioning checks (P2.5) lose their source of truth.

from __future__ import annotations

import logging
from typing import Optional

from model_layer.tts import KOKORO_IMPLEMENTED, TtsBackend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Piper catalog (the implemented backend)
# ---------------------------------------------------------------------------

# One voice per supported language — used for narrator and pair roles.
PIPER_LANGUAGE_VOICES: dict[str, str] = {
    "en": "en_US-lessac-medium",
    "es": "es_ES-carlos-medium",
    "fr": "fr_FR-alphonse-medium",
    "de": "de_DE-karlsson-medium",
    "it": "it_IT-eva-medium",
    "pt": "pt_BR-isabella-medium",
    "ru": "ru_RU-dmitri-medium",
    "ja": "ja_JP-ken_medium",
    "zh": "zh_CN-huayan-medium",
    "ko": "ko_KR-youngmi-medium",
}

# Distinct voices for multi-speaker scripts (podcast roles).
PIPER_SPEAKER_POOL: list[str] = [
    "en_US-lessac-medium",   # Speaker 1: neutral American
    "en_US-joe-medium",      # Speaker 2
    "en_US-amy-medium",      # Speaker 3
    "en_US-ryan-medium",     # Speaker 4
    "en_GB-alan-medium",     # Speaker 5: British accent for variety
]

FALLBACK_LANGUAGE = "en"

# ISO 639-1 code -> English display name, for prompt rendering
# ("written entirely in Spanish" reads better than "in es").
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "it": "Italian", "pt": "Portuguese", "ru": "Russian",
    "ja": "Japanese", "zh": "Chinese", "ko": "Korean",
}


def language_name(code: str) -> str:
    """'es' -> 'Spanish'; unknown codes pass through unchanged."""
    return LANGUAGE_NAMES.get((code or "").lower()[:2], code)

# ---------------------------------------------------------------------------
# Kokoro catalog (future backend — resolved only when implemented)
# ---------------------------------------------------------------------------

KOKORO_LANGUAGE_VOICES: dict[str, str] = {
    "en": "af_heart",
    "es": "bf_emma",
    "fr": "bf_emma",
    "de": "bm_george",
    "it": "bf_emma",
    "pt": "bf_emma",
    "ru": "bm_george",
    "ja": "bf_heart",
    "zh": "bf_emma",
}


def _resolve_language(language: Optional[str], table: dict[str, str], role: str) -> str:
    lang = (language or FALLBACK_LANGUAGE).lower()[:2]
    if lang in table:
        return table[lang]
    logger.warning("Voice Catalog: no %s voice for %r — falling back to %s",
                   role, language, FALLBACK_LANGUAGE)
    return table[FALLBACK_LANGUAGE]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def narrator_voice(
    language: str = FALLBACK_LANGUAGE,
    backend: Optional[TtsBackend] = None,
) -> str:
    """Single-voice narration: (language, backend) -> voice id."""
    resolved_backend = backend or (
        TtsBackend.KOKORO if KOKORO_IMPLEMENTED else TtsBackend.PIPER
    )
    if resolved_backend == TtsBackend.KOKORO:
        return _resolve_language(language, KOKORO_LANGUAGE_VOICES, "kokoro narrator")
    return _resolve_language(language, PIPER_LANGUAGE_VOICES, "piper narrator")


def pair_voices(target_language: str, known_language: str) -> tuple[str, str]:
    """Bilingual lesson voices: (target voice, known-language translation voice)."""
    return (
        _resolve_language(target_language, PIPER_LANGUAGE_VOICES, "bilingual target"),
        _resolve_language(known_language, PIPER_LANGUAGE_VOICES, "bilingual translation"),
    )


def speaker_pool() -> list[str]:
    """Distinct voices available for multi-speaker podcast scripts."""
    return list(PIPER_SPEAKER_POOL)


def speaker_voices(count: int, language: str = FALLBACK_LANGUAGE) -> list[str]:
    """
    Distinct voices for `count` speakers. The pool is language-scoped by
    its base voice so the primary speaker matches the content language;
    when demand exceeds the pool, extra speakers get numeric suffixes on
    the last pool entry (same fallback as the pre-catalog renderer).
    """
    if count <= 0:
        return []
    base = _resolve_language(language, PIPER_LANGUAGE_VOICES, "speaker lead")
    pool = [base] + [v for v in PIPER_SPEAKER_POOL if v != base]
    voices = [pool[i] for i in range(min(count, len(pool)))]
    while len(voices) < count:
        i = len(voices)
        voices.append(f"{pool[-1]}-{i + 1}")
    return voices


def has_language(language: str, backend: Optional[TtsBackend] = None) -> bool:
    """Provisioning check: does a concrete voice exist for this language?"""
    lang = (language or FALLBACK_LANGUAGE).lower()[:2]
    if backend == TtsBackend.KOKORO:
        return lang in KOKORO_LANGUAGE_VOICES
    return lang in PIPER_LANGUAGE_VOICES
