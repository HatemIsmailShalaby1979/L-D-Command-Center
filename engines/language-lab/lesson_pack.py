# engines/language-lab/lesson_pack.py
#
# WHAT: Whole-lesson generation for the Language Lab flagship — ONE
#       validated JSON pack per (topic, target_language, level) holding
#       two-voice dialogue segments, vocab cards, grammar cards with
#       drills, and mixed-type evaluation items (P7.2).
# WHY:  "Speak Like an Alien" becomes the most powerful tool in the app
#       by generating the whole lesson in one guardrailed pass instead
#       of stitching separate artifacts. Dialogue segments feed today's
#       two-voice rendering; drill/evaluation items are shaped so P7.3's
#       deterministic graders can judge them without trusting the model.
#       Schema validity is enforced by the Generation Pipeline with
#       feedback retry (CONSTITUTION §3).
# BREAKS IF DELETED: The Language Lab loses its flagship artifact; only
#       separate bilingual/immersion flows remain.

from __future__ import annotations

import logging
from typing import Any

from model_layer.client import LmStudioClient
from model_layer.pipeline import DEFAULT_MODEL, generate as run_guardrail_loop
from model_layer.prompts import PromptRegistry
from model_layer.schema import _validate_object

logger = logging.getLogger(__name__)

__all__ = [
    "LESSON_PACK_SCHEMA",
    "validate_lesson_pack",
    "generate_lesson_pack",
    "EVALUATION_TYPES",
]

PROMPT_KEY = "lesson_pack_generate"
RETRY_KEY = "lesson_pack_retry"

DEFAULT_NUM_DIALOGUE = 6
DEFAULT_NUM_VOCAB = 6
DEFAULT_NUM_GRAMMAR = 3
DEFAULT_NUM_EVAL = 5

EVALUATION_TYPES = ("multiple_choice", "fill_in_blank", "translation")

BLANK_MARKER = "___"


# ---------------------------------------------------------------------------
# Schema (declared contract == enforced contract, via _validate_object)
# ---------------------------------------------------------------------------

_LESSON_PACK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "topic", "target_language", "known_language", "level",
        "dialogue", "vocab_cards", "grammar_cards", "evaluation",
    ],
    "properties": {
        "topic": {"type": "string", "minLength": 1},
        "target_language": {"type": "string", "minLength": 1},
        "known_language": {"type": "string", "minLength": 1},
        "level": {
            "type": "string",
            "enum": ["beginner", "intermediate", "advanced"],
        },
        "dialogue": {
            "type": "array",
            "minItems": 2,
            "items": {
                "type": "object",
                "required": ["speaker", "content"],
                "properties": {
                    "speaker": {"type": "string", "minLength": 1},
                    "content": {"type": "string", "minLength": 1},
                },
                "additionalProperties": False,
            },
        },
        "vocab_cards": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["term", "reading", "translation", "example"],
                "properties": {
                    "term": {"type": "string", "minLength": 1},
                    "reading": {"type": "string", "minLength": 1},
                    "translation": {"type": "string", "minLength": 1},
                    "example": {"type": "string", "minLength": 1},
                },
                "additionalProperties": False,
            },
        },
        "grammar_cards": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["point", "explanation", "drills"],
                "properties": {
                    "point": {"type": "string", "minLength": 1},
                    "explanation": {"type": "string", "minLength": 1},
                    "drills": {
                        "type": "array",
                        "minItems": 2,
                        "items": {
                            "type": "object",
                            "required": ["prompt", "answer"],
                            "properties": {
                                "prompt": {"type": "string", "minLength": 1},
                                "answer": {"type": "string", "minLength": 1},
                            },
                            "additionalProperties": False,
                        },
                    },
                },
                "additionalProperties": False,
            },
        },
        # The schema engine has no oneOf, so evaluation items are pinned
        # to their discriminator here; per-type shapes are checked in
        # validate_lesson_pack below.
        "evaluation": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["type"],
                "properties": {
                    "type": {"enum": list(EVALUATION_TYPES)},
                },
            },
        },
    },
    "additionalProperties": False,
}

LESSON_PACK_SCHEMA = _LESSON_PACK_SCHEMA


# ---------------------------------------------------------------------------
# Validation: schema pass + semantic pass
# ---------------------------------------------------------------------------

def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_multiple_choice(item: dict[str, Any], errors: list[str]) -> None:
    if not item.get("question"):
        errors.append("multiple_choice item missing question")
    options = item.get("options")
    if not isinstance(options, list) or len(options) < 2 or \
            not all(isinstance(o, str) and o.strip() for o in options):
        errors.append("multiple_choice item needs >= 2 non-empty string options")
        return
    index = item.get("correct_index")
    if not _is_int(index):
        errors.append("multiple_choice correct_index must be an integer "
                      f"(got {index!r})")
    elif not 0 <= index < len(options):
        errors.append(f"multiple_choice correct_index {index} out of range "
                      f"for {len(options)} options")


def _check_fill_in_blank(item: dict[str, Any], errors: list[str]) -> None:
    sentence = item.get("sentence_with_blank")
    if not isinstance(sentence, str) or not sentence.strip():
        errors.append("fill_in_blank item missing sentence_with_blank")
    elif BLANK_MARKER not in sentence:
        errors.append(
            f"fill_in_blank sentence must contain a {BLANK_MARKER} blank marker"
        )
    if not isinstance(item.get("answer"), str) or not item["answer"].strip():
        errors.append("fill_in_blank item missing answer")


def _check_translation(item: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(item.get("prompt"), str) or not item["prompt"].strip():
        errors.append("translation item missing prompt")
    if not isinstance(item.get("answer"), str) or not item["answer"].strip():
        errors.append("translation item missing answer")


_EVAL_CHECKS = {
    "multiple_choice": _check_multiple_choice,
    "fill_in_blank": _check_fill_in_blank,
    "translation": _check_translation,
}


def validate_lesson_pack(raw: Any) -> tuple[bool, list[str]]:
    """
    Contract: validate a parsed lesson pack against LESSON_PACK_SCHEMA
    plus semantic rules the schema subset cannot express:

      - dialogue has EXACTLY two distinct speakers (two-voice rendering);
      - every evaluation item matches its declared type's shape.

    Translation fidelity of generated content is NOT checked here — it
    is a correctness problem owned by P7.3's graders and verification
    passes, never trusted from the generator.
    """
    if isinstance(raw, str):
        return False, ["lesson pack must arrive as a parsed object"]
    if not isinstance(raw, dict):
        return False, [f"expected a JSON object, got {type(raw).__name__}"]

    errors = _validate_object(raw, LESSON_PACK_SCHEMA, "$")

    speakers = {seg.get("speaker") for seg in raw.get("dialogue", [])}
    if len(speakers) != 2:
        errors.append(
            f"dialogue must have exactly two distinct speakers "
            f"(found {sorted(s for s in speakers if s)!r})"
        )

    for i, item in enumerate(raw.get("evaluation", [])):
        check = _EVAL_CHECKS.get(item.get("type"))
        if check is not None:
            item_errors: list[str] = []
            check(item, item_errors)
            errors.extend(f"evaluation[{i}]: {e}" for e in item_errors)

    return not errors, errors


# ---------------------------------------------------------------------------
# Generation entry point
# ---------------------------------------------------------------------------

def generate_lesson_pack(
    topic: str,
    target_language: str,
    known_language: str,
    level: str,
    *,
    num_dialogue: int = DEFAULT_NUM_DIALOGUE,
    num_vocab: int = DEFAULT_NUM_VOCAB,
    num_grammar: int = DEFAULT_NUM_GRAMMAR,
    num_eval: int = DEFAULT_NUM_EVAL,
    client: LmStudioClient | None = None,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """
    Contract: generate one validated lesson pack via the Generation
    Pipeline. Public interface mirrors generate_bilingual_pair; the
    pack is returned as a plain dict matching LESSON_PACK_SCHEMA so
    renderers (P7.4), graders (P7.3), and storage can consume it
    without adapter layers.

    Raises:
        ValueError: empty topic/languages.
        SchemaValidationError: invalid after all pipeline attempts.
        ConnectionError / ApiError: per the pipeline error taxonomy.
    """
    if not topic or not topic.strip():
        raise ValueError("Topic must be non-empty")
    if not target_language or not target_language.strip():
        raise ValueError("Target language must be specified")
    if not known_language or not known_language.strip():
        raise ValueError("Known language must be specified")

    variables = {
        "topic": topic.strip(),
        "target_language": target_language.strip(),
        "known_language": known_language.strip(),
        "level": level,
        "num_dialogue": int(num_dialogue),
        "num_vocab": int(num_vocab),
        "num_grammar": int(num_grammar),
        "num_eval": int(num_eval),
    }
    parsed = run_guardrail_loop(
        PromptRegistry(),
        client if client is not None else LmStudioClient(),
        template=PROMPT_KEY,
        retry_template=RETRY_KEY,
        variables=variables,
        validator=validate_lesson_pack,
        model=model,
        max_tokens=4096,
        temperature=0.3,
    )
    logger.info("Lesson pack generated: %s (%s→%s, %s)",
                variables["topic"][:50], target_language, known_language, level)
    return parsed
