# engines/language-lab/skills.py
#
# WHAT: The four-skills practice engine for the Skills Arena —
#       reading packs from imported text, writing evaluation with a
#       corrected version, and listening-question generation from
#       imported audio (via STT).
# WHY:  Owner directive 2026-09-06: the Playground becomes the area
#       where users practice reading, writing, listening and speaking
#       interactively with their own files/text. These are the three
#       LM-powered flows (speaking is E.T. + drills, already shipped
#       in L2). Deterministic-first where possible, rubric-judged
#       where judgment is real, all through the Guardrail Loop.
# BREAKS IF DELETED: The Arena's reading/writing/listening panels
#       have no engine behind them.

from __future__ import annotations

import logging
from typing import Any

from model_layer.client import LmStudioClient
from model_layer.pipeline import DEFAULT_MODEL, generate as run_guardrail_loop
from model_layer.policy import difficulty_for_level
from model_layer.prompts import PromptRegistry

logger = logging.getLogger(__name__)

__all__ = [
    "generate_reading_pack", "evaluate_writing",
    "extract_document_text",
]


def extract_document_text(path: str) -> str:
    """Contract: pull readable text from txt/PDF/DOCX for the reading
    panel. Returns '' (never raises) on unreadable input — the UI says
    'couldn't read that file' instead of crashing."""
    from pathlib import Path
    suffix = Path(path).suffix.lower()
    try:
        if suffix == ".txt":
            return Path(path).read_text(encoding="utf-8",
                                         errors="replace")
        if suffix == ".pdf":
            import pdfplumber
            chunks = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    chunks.append(page.extract_text() or "")
            return "\n".join(chunks)
        if suffix == ".docx":
            import docx
            document = docx.Document(path)
            return "\n".join(p.text for p in document.paragraphs)
    except Exception as exc:  # noqa: BLE001 — unreadable is data
        logger.warning("Document text extraction failed for %s: %s",
                       path, exc)
        return ""
    logger.warning("Unsupported document type for reading: %s", suffix)
    return ""


def generate_reading_pack(text: str, language: str, level: str, *,
                          client: LmStudioClient | None = None,
                          model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """One reading pack from imported text: cleaned text, glossary,
    exactly 4 comprehension questions."""
    from engines.audio_engine.voice_catalog import language_name
    text = (text or "").strip()
    if len(text.split()) < 40:
        raise ValueError(
            "That text is too short to practice with — reading packs "
            "need ~40+ words so the questions have something to ask "
            "about.")
    level = (level or "a2").lower()
    if level not in ("a1", "a2", "b1", "b2", "c1"):
        level = "a2"

    def validator(parsed: Any) -> tuple[bool, list[str]]:
        if not isinstance(parsed, dict):
            return False, ["expected a JSON object"]
        errors: list[str] = []
        if not str(parsed.get("cleaned_text") or "").strip():
            errors.append("cleaned_text must be non-empty")
        glossary = parsed.get("glossary")
        if not isinstance(glossary, list) or not (5 <= len(glossary) <= 8):
            errors.append("glossary needs 5-8 entries")
        questions = parsed.get("questions")
        if not isinstance(questions, list) or len(questions) != 4:
            errors.append("questions must have exactly 4 items")
        else:
            for i, item in enumerate(questions):
                options = item.get("options")
                if not isinstance(options, list) or len(options) != 4:
                    errors.append(f"questions[{i}] needs 4 options")
                index = item.get("correct_index")
                if not isinstance(index, int) or not 0 <= index < 4:
                    errors.append(f"questions[{i}] correct_index 0-3")
        return not errors, errors

    pack = run_guardrail_loop(
        PromptRegistry(),
        client if client is not None else LmStudioClient(),
        template="reading_pack_generate",
        variables={"text": text[:6000],
                   "level": level,
                   "difficulty": difficulty_for_level(level),
                   "language_name": language_name(language)},
        validator=validator,
        model=model,
        max_tokens=4096, temperature=0.3,
    )
    logger.info("Reading pack generated (%d glossary, %d questions)",
                len(pack["glossary"]), len(pack["questions"]))
    return pack


def evaluate_writing(task: str, text: str, language: str, level: str, *,
                     client: LmStudioClient | None = None,
                     model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """Rubric evaluation + corrected version + highlights. The
    learner's voice survives; the grammar gets a spa day."""
    from engines.audio_engine.voice_catalog import language_name
    text = (text or "").strip()
    if len(text.split()) < 10:
        raise ValueError("Write a little more first — even three "
                         "sentences gives the coach something to "
                         "praise.")
    level = (level or "a2").lower()
    if level not in ("a1", "a2", "b1", "b2", "c1"):
        level = "a2"

    def validator(parsed: Any) -> tuple[bool, list[str]]:
        if not isinstance(parsed, dict):
            return False, ["expected a JSON object"]
        errors: list[str] = []
        for key in ("grammar", "vocabulary", "structure", "register"):
            value = parsed.get(key)
            if not isinstance(value, int) or not 1 <= value <= 5:
                errors.append(f"{key} must be 1-5")
        for key in ("strength", "corrected_text", "next_step"):
            if not str(parsed.get(key) or "").strip():
                errors.append(f"{key} must be non-empty")
        highlights = parsed.get("highlights")
        if not isinstance(highlights, list) or not (2 <= len(highlights)
                                                     <= 5):
            errors.append("highlights needs 2-5 fixes")
        return not errors, errors

    result = run_guardrail_loop(
        PromptRegistry(),
        client if client is not None else LmStudioClient(),
        template="writing_eval_generate",
        retry_template="writing_eval_retry",
        variables={"task": task or "Free writing practice",
                   "text": text[:4000],
                   "level": level,
                   "difficulty": difficulty_for_level(level),
                   "language_name": language_name(language)},
        validator=validator,
        model=model,
        max_tokens=4096, temperature=0.3,
    )
    logger.info("Writing evaluated: %s", {k: result[k] for k in
                                           ("grammar", "vocabulary")})
    return result
