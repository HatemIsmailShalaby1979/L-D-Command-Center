# engines/language-lab/pack_audio.py
#
# WHAT: Per-segment audio for lesson packs — each dialogue turn becomes
#       its own WAV artifact, rendered through the public assembly seam,
#       named exactly as the LanguageLabRenderer's audio contract expects
#       ("dialogue-<i>" -> "<stem>-dialogue-<i>.wav") (P7.5).
# WHY:  The flagship's listening items must play the EXACT segment a
#       learner is studying, not a mixed track. Speaker->voice assignment
#       resolves ONLY through the Voice Catalog (two distinct speakers =
#       two distinct voices), so this module owns zero voice knowledge.
# BREAKS IF DELETED: Lesson packs lose their audio; the renderer's
#       listening rows silently disappear.

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from engines.audio_engine import assembly, voice_catalog

logger = logging.getLogger(__name__)

__all__ = ["SegmentAudio", "assign_speaker_voices", "render_pack_audio",
           "DEFAULT_SPEED"]

DEFAULT_SPEED = 0.9  # slightly slower for learners (matches bilingual)
_KEY_PREFIX = "dialogue"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class SegmentAudio:
    """One rendered dialogue turn. `key` is the renderer's lookup key;
    `name` is the artifact filename."""
    key: str
    name: str
    wav_bytes: bytes
    duration_seconds: float


def pack_slug(topic: str) -> str:
    slug = _SLUG_RE.sub("-", (topic or "").lower()).strip("-")
    return slug or "lesson"


def assign_speaker_voices(pack: dict[str, Any]) -> dict[str, str]:
    """
    Contract: map each distinct dialogue speaker to a concrete TTS voice
    deterministically — first appearance order, distinct voices drawn
    from the Voice Catalog's language-scoped pool.
    """
    seen: list[str] = []
    for seg in pack.get("dialogue", []):
        speaker = str(seg.get("speaker", ""))
        if speaker and speaker not in seen:
            seen.append(speaker)
    pool = voice_catalog.speaker_voices(len(seen),
                                        pack.get("target_language", "en"))
    return dict(zip(seen, pool))


def render_pack_audio(
    pack: dict[str, Any],
    *,
    speed: float = DEFAULT_SPEED,
    backend: Optional[Any] = None,
    include_mp3: bool = False,
    output_path: Optional[str] = None,
    stem: Optional[str] = None,
) -> list[SegmentAudio]:
    """
    Contract: render every dialogue turn of a lesson pack into its own
    audio artifact via assembly.render_segments.

    Args:
        pack: validated lesson pack (needs non-empty `dialogue`).
        speed: playback rate passed to synthesis.
        backend: optional explicit TTS backend (None = model-layer default).
        include_mp3: also attempt MP3 conversion per turn (off by
            default; browser <audio> plays WAV).
        output_path: optional directory; artifacts are ALSO written
            there under their `.name`.
        stem: filename stem; defaults to "<topic-slug>-lesson".

    Returns:
        SegmentAudio list ordered by turn index; keys are
        "dialogue-<i>", names "<stem>-dialogue-<i>.wav" — byte-stable
        for identical packs so artifact references survive re-renders.

    Raises:
        ValueError: pack has no dialogue to render.
        RuntimeError: TTS synthesis failure propagates.
    """
    dialogue = pack.get("dialogue") or []
    if not dialogue:
        raise ValueError("Lesson pack has no dialogue to render")

    voices = assign_speaker_voices(pack)
    base = stem or f"{pack_slug(str(pack.get('topic', '')))}-lesson"
    rendered: list[SegmentAudio] = []
    for i, seg in enumerate(dialogue):
        key = f"{_KEY_PREFIX}-{i}"
        name = f"{base}-{key}.wav"
        result = assembly.render_segments(
            [(str(seg.get("content", "")), voices[str(seg.get("speaker", ""))],
              speed)],
            include_mp3=include_mp3,
            output_path=output_path,
            basename=name[:-4],  # strip .wav; seam appends it
        )
        rendered.append(SegmentAudio(
            key=key, name=name,
            wav_bytes=result.wav_bytes,
            duration_seconds=result.duration_seconds,
        ))
    logger.info("Rendered %d dialogue segments for pack %r",
                len(rendered), pack.get("topic"))
    return rendered
