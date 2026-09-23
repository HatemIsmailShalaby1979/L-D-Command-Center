# engines/language-lab/placement.py
#
# WHAT: The 10-minute placement quiz — 12 escalating items spanning
#       A1→B1 that tell a brand-new user exactly where to start, with
#       a rationale and a jump-straight-there pointer.
# WHY:  Owner directive: "the user must find… a ground to start from
#       and a guide." A 30-lesson catalog without a starting point is
#       intimidating; placement is the front door. Deterministic
#       grading (no LM needed to SCORE), one LM call to generate the
#       quiz, honest banding rules (you place INTO a band when you
#       clear most of its items — generous on the boundary, never
#       inflated).
# BREAKS IF DELETED: New users face the library cold — the top of the
#       funnel leaks at the front door.

from __future__ import annotations

import logging
from typing import Any

from model_layer.client import LmStudioClient
from model_layer.pipeline import DEFAULT_MODEL, generate as run_guardrail_loop
from model_layer.policy import difficulty_for_level
from model_layer.prompts import PromptRegistry

logger = logging.getLogger(__name__)

__all__ = ["validate_placement_quiz", "generate_placement_quiz",
           "grade_placement", "PLACEMENT_KEY"]

PLACEMENT_KEY = "placement_result"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_placement_quiz(raw: Any) -> tuple[bool, list[str]]:
    """Exactly 12 items, 4 options each, escalating bands
    (1-4 a1, 5-8 a2, 9-12 b1)."""
    if not isinstance(raw, dict):
        return False, ["expected a JSON object"]
    items = raw.get("items")
    if not isinstance(items, list) or len(items) != 12:
        return False, ["items must have exactly 12 entries"]
    errors: list[str] = []
    expected_bands = ["a1"] * 4 + ["a2"] * 4 + ["b1"] * 4
    for i, (item, band) in enumerate(zip(items, expected_bands)):
        if not isinstance(item, dict):
            errors.append(f"items[{i}] must be an object")
            continue
        if not str(item.get("question") or "").strip():
            errors.append(f"items[{i}] missing question")
        options = item.get("options")
        if not isinstance(options, list) or len(options) != 4:
            errors.append(f"items[{i}] needs exactly 4 options")
        if not _is_int(item.get("correct_index")) or not \
                (0 <= item["correct_index"] < 4):
            errors.append(f"items[{i}] correct_index must be 0-3")
        if str(item.get("band") or "") != band:
            errors.append(f"items[{i}] band must be {band!r}")
    return not errors, errors


def generate_placement_quiz(language: str, *,
                            client: LmStudioClient | None = None,
                            model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """The 12-item quiz, built as three 4-item band blocks (a1, a2,
    b1) assembled in order. Chunked deliberately: reasoning models
    spiral deliberating over long counted lists (measured live: a
    single 12-item call burned 4093 thinking tokens and emitted
    nothing), while 4-item blocks complete reliably. Each block is
    validated on its own, then the whole quiz is validated."""
    from engines.audio_engine.voice_catalog import language_name
    language = (language or "en").lower()[:2]
    name = language_name(language)
    client = client if client is not None else LmStudioClient()

    def _band_validator(parsed: Any) -> tuple[bool, list[str]]:
        if not isinstance(parsed, dict):
            return False, ["expected a JSON object"]
        items = parsed.get("items")
        if not isinstance(items, list) or len(items) != 4:
            return False, ["items must have exactly 4 entries"]
        errors: list[str] = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"items[{i}] must be an object")
                continue
            if not str(item.get("question") or "").strip():
                errors.append(f"items[{i}] missing question")
            options = item.get("options")
            if not isinstance(options, list) or len(options) != 4:
                errors.append(f"items[{i}] needs exactly 4 options")
            if not _is_int(item.get("correct_index")) or not \
                    (0 <= item["correct_index"] < 4):
                errors.append(f"items[{i}] correct_index must be 0-3")
        return not errors, errors

    blocks: list[dict[str, Any]] = []
    for band in ("a1", "a2", "b1"):
        block = run_guardrail_loop(
            PromptRegistry(), client,
            template="placement_band_generate",
            retry_template="placement_band_retry",
            variables={"language_name": name,
                       "difficulty": difficulty_for_level(band)},
            validator=_band_validator,
            model=model,
            max_tokens=4096, temperature=0.4,
        )
        for item in block["items"]:
            item["band"] = band
        blocks.extend(block["items"])
    quiz = {"items": blocks}
    ok, errors = validate_placement_quiz(quiz)
    if not ok:  # pragma: no cover — assembly of validated blocks
        raise ValueError(f"Assembled quiz invalid: {errors}")
    logger.info("Placement quiz generated for %s (3 band blocks)",
                language)
    return quiz


def grade_placement(quiz: dict[str, Any],
                     answers: list[int]) -> dict[str, Any]:
    """Score 12 answers -> band + rationale + next lesson pointer.

    Banding rules (honest, motivating):
      - clear 3+ of a band's 4 items to "reach" it
      - place at the HIGHEST band reached with ≥2/3 of its items
      - clear 3/4 of b1 -> ready for b1 start
    Never inflated: 0 correct = a1 with warmth, not shame."""
    items = quiz.get("items") or []
    chosen = (answers or [])[:12]
    per_band = {"a1": [0, 0], "a2": [0, 0], "b1": [0, 0]}
    for i, item in enumerate(items):
        band = str(item.get("band") or "a1")
        if band not in per_band:
            continue
        per_band[band][1] += 1
        if i < len(chosen) and _is_int(chosen[i]) and \
                chosen[i] == item.get("correct_index"):
            per_band[band][0] += 1

    correct = per_band["a1"][0] + per_band["a2"][0] + per_band["b1"][0]
    # decide the placement band
    if per_band["b1"][0] >= 3:
        band = "b1"
    elif per_band["a2"][0] >= 3:
        band = "a2"
    else:
        band = "a1"
    # a2 with a strong a2 showing but weak a1 basics stays honest
    if band == "a2" and per_band["a1"][0] < 2:
        band = "a1"

    a1_pct = round(per_band["a1"][0] / 4 * 100)
    a2_pct = round(per_band["a2"][0] / 4 * 100)
    b1_pct = round(per_band["b1"][0] / 4 * 100)

    if band == "a1" and correct == 0:
        rationale = ("A perfect blank page — the best place to start. "
                     "A1 is where every fluent speaker began.")
    elif band == "a1":
        rationale = (f"A1 basics are still settling in ({a1_pct}% on "
                     "beginner items). Starting at A1 makes the "
                     "foundation unshakeable.")
    elif band == "a2":
        rationale = (f"A1 is yours ({a1_pct}%), and A2 is warming up "
                     f"({a2_pct}%). A2 lessons will feel like home.")
    else:
        rationale = (f"A1 {a1_pct}%, A2 {a2_pct}%, B1 already at "
                     f"{b1_pct}% — you're placing straight into "
                     "independent-opinion territory.")

    return {
        "band": band,
        "correct": correct,
        "total": len(items) or 12,
        "per_band": {"a1": a1_pct, "a2": a2_pct, "b1": b1_pct},
        "rationale": rationale,
        "recommended_first_slot": f"{band}-people_friends",
    }
