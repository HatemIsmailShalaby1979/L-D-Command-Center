# engines/export-engine/export.py
#
# WHAT: The export-engine's public surface — deterministic conversion of
#       EXISTING artifacts (Journey, Resume, narration text) into txt /
#       PDF / DOCX / PPTX / XLSX / WAV. Rendering lives in per-format
#       adapter modules; this file is only re-exports + dispatch.
# WHY:  P4.1/P4.2 of docs/PRODUCTION_PLAN.md. The former 1004-line
#       god-module mixed four jobs and secretly GENERATED new podcasts
#       inside "export". Export never calls the model (CONTEXT.md
#       "Export"); producing new content is generation, done by engines.
# BREAKS IF DELETED: No download/share formats exist; every consumer
#       loses its artifact writers.

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from engines.export_engine.detect import _detect_type  # noqa: F401 (re-export)
from engines.export_engine.text_format import (
    export_resume_to_plain_text,
    export_resume_to_text_file,
    export_to_plain_text,
    export_to_text_file,
)
from engines.export_engine.pdf_format import (
    export_resume_to_pdf,
    export_resume_to_pdf_file,
    export_to_pdf,
    export_to_pdf_file,
)
from engines.export_engine.docx_format import (
    export_resume_to_docx,
    export_resume_to_docx_file,
)
from engines.export_engine.pptx_format import export_journey_to_pptx
from engines.export_engine.xlsx_format import export_journey_to_xlsx

logger = logging.getLogger(__name__)

_AUDIO_KINDS = {"narration", "podcast", "bilingual", "immersion"}

_JOURNEY_FORMATS = {"text", "pdf", "pptx", "xlsx"}
_RESUME_FORMATS = {"text", "pdf", "docx"}


def export(content: dict[str, Any], format: str = "text", filepath: str | None = None) -> str | bytes:
    """
    Contract: deterministically convert an existing artifact.

    Args:
        content: a Journey dict, Resume dict, or {"text": ...} narration
            payload — detected via _detect_type.
        format: journey → text|pdf|pptx|xlsx; resume → text|pdf|docx;
            narration → wav|mp3.
        filepath: optional destination; when given, writes the file and
            returns its path instead of the payload.

    Returns:
        The rendered payload (str or bytes), or `filepath` when written.

    Raises:
        ValueError: unknown content keys, unsupported format, or an audio
            kind that would require GENERATION (podcast/bilingual/
            immersion) — compose those engines explicitly instead.
    """
    kind = _detect_type(content)

    if kind in ("podcast", "bilingual", "immersion"):
        raise ValueError(
            f"Export cannot produce '{kind}' audio: that would generate NEW "
            "content, and export is deterministic by contract. Compose "
            "engines explicitly, e.g. podcast_script.generate_podcast_script() "
            "-> podcast_audio.render_podcast_to_audio() (see CONTEXT.md 'Export')."
        )

    if kind == "journey":
        if format == "text":
            result: str | bytes = export_to_plain_text(content)
        elif format == "pdf":
            result = export_to_pdf(content)
        elif format == "pptx":
            result = export_journey_to_pptx(content)
        elif format == "xlsx":
            result = export_journey_to_xlsx(content)
        else:
            raise KeyError(f"Journey export supports {_JOURNEY_FORMATS}; got {format!r}")
    elif kind == "resume":
        if format == "text":
            result = export_resume_to_plain_text(content)
        elif format == "pdf":
            result = export_resume_to_pdf(content)
        elif format == "docx":
            result = export_resume_to_docx(content)
        else:
            raise KeyError(f"Resume export supports {_RESUME_FORMATS}; got {format!r}")
    elif kind == "narration":
        if format not in ("wav", "mp3"):
            raise KeyError("Narration export supports {'wav', 'mp3'}")
        from engines.audio_engine import assembly, voice_catalog

        audio = assembly.render_segments(
            [(content["text"], voice_catalog.narrator_voice("en"))],
            include_mp3=(format == "mp3"),
        )
        return _maybe_write(audio.wav_bytes if format == "wav" else (audio.mp3_bytes or audio.wav_bytes), filepath)
    else:
        raise ValueError(
            f"Cannot detect content type. Keys: {list(content.keys())}"
        )

    logger.info("Exported %s as %s (%d %s)", kind, format,
                len(result), "chars" if isinstance(result, str) else "bytes")
    return _maybe_write(result, filepath)


def _maybe_write(result: str | bytes, filepath: str | None) -> str | bytes:
    if filepath is None:
        return result
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(result, str):
        path.write_text(result, encoding="utf-8")
    else:
        path.write_bytes(result)
    return filepath


__all__ = [
    # detection
    "_detect_type",
    # journey
    "export_to_plain_text", "export_to_pdf",
    "export_journey_to_pptx", "export_journey_to_xlsx",
    "export_to_text_file", "export_to_pdf_file",
    # resume
    "export_resume_to_plain_text", "export_resume_to_pdf",
    "export_resume_to_docx",
    "export_resume_to_text_file", "export_resume_to_pdf_file",
    "export_resume_to_docx_file",
    # unified dispatcher
    "export",
]
