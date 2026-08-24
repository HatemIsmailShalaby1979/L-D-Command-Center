# engines/language-lab/graders.py
#
# WHAT: Grading for Language Lab exercises — deterministic graders first
#       (exact/alternatives/normalization), model-judge fallback for
#       free-form answers, plus a pack-level fidelity audit of the pack's
#       own claims. All verdicts are plain inspectable dicts (P7.3).
# WHY:  Nothing is trusted because the model said so (CONSTITUTION §3,
#       plan §C3). Deterministic grading needs no model and can never be
#       argued with; the judge is only consulted where string equality is
#       the wrong tool, and even then it returns an auditable artifact —
#       never a bare boolean swallowed by a score.
# BREAKS IF DELETED: Learner answers are graded by trusting generated
#       answer keys blindly; pack errors reach learners unverified.

from __future__ import annotations

import json
import logging
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional

from model_layer.client import LmStudioClient
from model_layer.pipeline import DEFAULT_MODEL, generate as run_guardrail_loop
from model_layer.prompts import PromptRegistry

logger = logging.getLogger(__name__)

__all__ = [
    "GradeResult",
    "normalize_answer",
    "accepted_answers",
    "grade_deterministic",
    "grade_item",
    "judge_grade",
    "validate_judge_verdict",
    "verify_lesson_pack",
]

_JUDGE_KEY = "lesson_judge"
_VERIFY_KEY = "lesson_verify"


# ---------------------------------------------------------------------------
# Deterministic grading (pure functions)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GradeResult:
    """Contract: one graded answer. `method` says who decided:
    deterministic | judge | none (fallback needed but unavailable)."""
    item_type: str
    correct: bool
    method: str
    detail: str = ""


_EDGE_PUNCT = "\"'“”‘’….,!?;:¿¡"


def normalize_answer(text: str) -> str:
    """Casefold, trim punctuation at both edges, collapse spaces.

    Opening marks (¿¡) are stripped only at the edges — content words
    are never touched, so politeness markers cannot break exact
    matching."""
    cleaned = text.strip().strip(_EDGE_PUNCT).strip()
    return " ".join(cleaned.casefold().split())


def _accent_fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def accepted_answers(answer_field: Any) -> list[str]:
    """
    Contract: split an answer key into accepted alternatives.
    "soy" -> ["soy"]; "soy / estoy" or "soy;estoy" -> ["soy", "estoy"].
    Alternatives are compared normalized, so spacing around separators
    does not matter.
    """
    if not isinstance(answer_field, str):
        return []
    parts = answer_field.replace(";", "/").split("/")
    return [p for p in (normalize_answer(part) for part in parts) if p]


def _matches(answer: str, keys: list[str]) -> Optional[str]:
    """Return the match kind ("exact" | "accent-folded") or None."""
    norm = normalize_answer(answer)
    if norm in keys:
        return "exact"
    if _accent_fold(norm) in {_accent_fold(k) for k in keys}:
        return "accent-folded"
    return None


def grade_multiple_choice(item: dict[str, Any], answer: Any) -> GradeResult:
    options = item.get("options") or []
    index = item.get("correct_index")
    if isinstance(answer, bool) or not isinstance(answer, int):
        return GradeResult("multiple_choice", False, "deterministic",
                           f"expected the chosen option's index, got {answer!r}")
    if not isinstance(index, int) or not 0 <= answer < len(options):
        return GradeResult("multiple_choice", False, "deterministic",
                           "index out of range")
    return GradeResult("multiple_choice", answer == index, "deterministic")


def _grade_keyed(item_type: str, key: Any, answer: Any) -> GradeResult:
    keys = accepted_answers(key)
    match = _matches(str(answer), keys) if keys else None
    if match == "exact":
        return GradeResult(item_type, True, "deterministic")
    if match == "accent-folded":
        return GradeResult(item_type, True, "deterministic",
                           "correct ignoring accents")
    return GradeResult(
        item_type, False, "deterministic",
        f"expected {key!r}" + ("" if not keys else f" (or {keys[1:]!r})"),
    )


def grade_fill_in_blank(item: dict[str, Any], answer: Any) -> GradeResult:
    return _grade_keyed("fill_in_blank", item.get("answer"), answer)


def grade_drill(drill: dict[str, Any], answer: Any) -> GradeResult:
    """Grammar-card drills share the fill-in-blank grading path."""
    return _grade_keyed("drill", drill.get("answer"), answer)


def _grade_translation(item: dict[str, Any], answer: Any) -> Optional[GradeResult]:
    """
    Free-form by nature: deterministic grading only accepts exact/
    alternative/folded equality with the key. Anything else returns
    None meaning "needs the judge" — a different-but-valid translation
    must NOT be marked wrong without review.
    """
    result = _grade_keyed("translation", item.get("answer"), answer)
    return result if result.correct else None


def grade_deterministic(item: dict[str, Any], answer: Any) -> Optional[GradeResult]:
    """
    Contract: grade one evaluation item without any model involvement.
    Returns None when the item type requires judgment (free-form miss),
    so callers can fall back to the model judge.

    Raises:
        ValueError: unknown item type.
    """
    item_type = item.get("type")
    if item_type == "multiple_choice":
        return grade_multiple_choice(item, answer)
    if item_type == "fill_in_blank":
        return grade_fill_in_blank(item, answer)
    if item_type == "translation":
        return _grade_translation(item, answer)
    raise ValueError(f"Unknown evaluation item type: {item_type!r}")


# ---------------------------------------------------------------------------
# Model-judge fallback (single pipeline attempt, P3.2 pattern)
# ---------------------------------------------------------------------------

def validate_judge_verdict(data: Any) -> tuple[bool, list[str]]:
    """Contract: shape-check the judge's {passed, correct_answer, issues}."""
    if not isinstance(data, dict):
        return False, [f"expected a JSON object, got {type(data).__name__}"]
    errors = []
    if not isinstance(data.get("passed"), bool):
        errors.append("'passed' must be a boolean")
    correct = data.get("correct_answer")
    if correct is not None and (not isinstance(correct, str) or not correct.strip()):
        errors.append("'correct_answer' must be a non-empty string when present")
    issues = data.get("issues", [])
    if not isinstance(issues, list):
        errors.append("'issues' must be a list")
    else:
        errors += [f"issue {i} must be a string"
                   for i, issue in enumerate(issues) if not isinstance(issue, str)]
    return not errors, errors


def judge_grade(
    item: dict[str, Any],
    answer: Any,
    *,
    target_language: str,
    known_language: str = "en",
    level: str = "beginner",
    client: LmStudioClient | None = None,
    model: str = DEFAULT_MODEL,
) -> GradeResult:
    """
    Contract: ask the model to judge ONE learner answer and return an
    inspectable GradeResult whose detail carries the canonical answer
    and every issue raised. Single pipeline attempt — a malformed
    verdict raises rather than being mistaken for a failing grade.
    """
    parsed = run_guardrail_loop(
        PromptRegistry(),
        client if client is not None else LmStudioClient(),
        template=_JUDGE_KEY,
        variables={
            "target_language": target_language,
            "known_language": known_language,
            "level": level,
            "item": json.dumps(item, ensure_ascii=False),
            "answer": json.dumps(str(answer), ensure_ascii=False),
        },
        validator=validate_judge_verdict,
        model=model,
        max_tokens=512,
        temperature=0.0,
    )
    issues = "; ".join(parsed.get("issues") or [])
    detail = issues or (f"accepted; canonical answer: {parsed['correct_answer']}"
                        if parsed.get("correct_answer") else "accepted")
    logger.info("Judge graded %s item as %s", item.get("type"), parsed["passed"])
    return GradeResult(str(item.get("type")), bool(parsed["passed"]),
                       "judge", detail)


def grade_item(
    item: dict[str, Any],
    answer: Any,
    *,
    target_language: str = "es",
    known_language: str = "en",
    level: str = "beginner",
    client: LmStudioClient | None = None,
    model: str = DEFAULT_MODEL,
) -> GradeResult:
    """
    Contract: deterministic first, judge second.

    Deterministic results (including incorrect ones) never consult the
    model — only a free-form translation that misses its key falls
    through to the judge. When the judge is needed but no client was
    provided, ValueError is raised instead of silently failing the
    learner.
    """
    result = grade_deterministic(item, answer)
    if result is not None:
        return result
    if client is None:
        raise ValueError(
            "Answer could not be graded deterministically and no judge "
            "client was provided.")
    return judge_grade(
        item, answer, target_language=target_language,
        known_language=known_language, level=level, client=client, model=model)


# ---------------------------------------------------------------------------
# Pack fidelity audit (§C3: verification extended to grammar explanations)
# ---------------------------------------------------------------------------

def _pack_claims(pack: dict[str, Any]) -> list[dict[str, str]]:
    claims = []
    for i, card in enumerate(pack.get("vocab_cards", [])):
        claims.append({"id": f"V{i}", "kind": "vocab_translation",
                       "text": f"term '{card.get('term')}' means "
                               f"'{card.get('translation')}'"})
    for i, card in enumerate(pack.get("grammar_cards", [])):
        claims.append({"id": f"G{i}", "kind": "grammar_explanation",
                       "text": f"{card.get('point')}: {card.get('explanation')}"})
    return claims


def validate_pack_verdict(data: Any) -> tuple[bool, list[str]]:
    """Contract: shape-check the auditor's {passed, issues} payload."""
    if not isinstance(data, dict):
        return False, [f"expected a JSON object, got {type(data).__name__}"]
    errors = []
    if not isinstance(data.get("passed"), bool):
        errors.append("'passed' must be a boolean")
    issues = data.get("issues", [])
    if not isinstance(issues, list):
        errors.append("'issues' must be a list")
    else:
        for i, issue in enumerate(issues):
            if not isinstance(issue, dict) or "claim" not in issue or "problem" not in issue:
                errors.append(f"issue {i} needs 'claim' and 'problem'")
    return not errors, errors


def verify_lesson_pack(
    pack: dict[str, Any],
    *,
    client: LmStudioClient | None = None,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """
    Contract: audit the pack's own checkable claims — every vocab
    translation and grammar explanation — with one judge call, and
    return an inspectable artifact:

        {
          "topic": ..., "passed": <bool>,
          "claims": [{"id","kind","text","ok","problem"}, ...],
        }

    Single pipeline attempt (no feedback retry): a malformed audit
    raises rather than passing silently (P3.2 discipline).
    """
    claims = _pack_claims(pack)
    formatted = "\n".join(f"{c['id']}. [{c['text']}]" for c in claims)
    parsed = run_guardrail_loop(
        PromptRegistry(),
        client if client is not None else LmStudioClient(),
        template=_VERIFY_KEY,
        variables={
            "topic": pack.get("topic", ""),
            "target_language": pack.get("target_language", ""),
            "known_language": pack.get("known_language", ""),
            "level": pack.get("level", "beginner"),
            "claims": formatted,
        },
        validator=validate_pack_verdict,
        model=model,
        max_tokens=1024,
        temperature=0.0,
    )
    problems = {issue["claim"]: issue["problem"] for issue in parsed.get("issues", [])}
    claim_rows = [{
        **claim,
        "ok": claim["id"] not in problems,
        "problem": problems.get(claim["id"], ""),
    } for claim in claims]
    artifact = {
        "topic": pack.get("topic", ""),
        "passed": bool(parsed["passed"]) and all(row["ok"] for row in claim_rows),
        "claims": claim_rows,
    }
    logger.info("Pack audit for %r: passed=%s (%d claims)",
                artifact["topic"], artifact["passed"], len(claim_rows))
    return artifact
