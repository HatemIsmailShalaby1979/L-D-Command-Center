# engines/language-lab/level_exam.py
#
# WHAT: The inclusive final test per CEFR level (A1..C1) — one exam
#       covering vocabulary, grammar, reading, writing, listening,
#       speaking, with deterministic grading where possible,
#       rubric-judging where human judgment is needed, and full
#       evaluations + recommendations on the result.
# WHY:  Owner directive 2026-09-06: "design one inclusive final test
#       after each and every level like a1 or a2 or b1… testing
#       vocabulary grammar reading writing speaking and listening,
#       give full evaluations and recommendations upon user result."
#       MC/fill sections grade deterministically (graders.py);
#       writing/speaking grade through the exam_judge rubric; the
#       listening section renders to audio via the assembly seam;
#       the repeat-sentence speaking task scores by STT similarity.
#       All injected fakes make the whole flow testable headless.
# BREAKS IF DELETED: The curriculum ladder has no summit — levels
#       cannot be certified and the journey has no milestones.

from __future__ import annotations

import difflib
import logging
import time
from typing import Any, Callable, Optional

from model_layer.client import LmStudioClient
from model_layer.pipeline import DEFAULT_MODEL, generate as run_guardrail_loop
from model_layer.policy import difficulty_for_level
from model_layer.prompts import PromptRegistry

logger = logging.getLogger(__name__)

__all__ = [
    "EXAM_SCHEMA", "validate_level_exam", "generate_level_exam",
    "grade_objective_sections", "judge_answer", "grade_speaking_repeat",
    "ExamResult", "build_exam_result", "PASS_THRESHOLD",
    "SECTION_WEIGHTS",
]

# Pass bar: strict enough to mean something, kind enough to motivate
# a retry — with recommendations pointing exactly where to go.
PASS_THRESHOLD = 70

# Section weights sum to 100: speaking+writing carry the most because
# they prove active production, per the owner's inclusive mandate.
SECTION_WEIGHTS = {
    "vocabulary": 15,
    "grammar": 20,
    "reading": 15,
    "writing": 20,
    "listening": 15,
    "speaking": 15,
}


# ---------------------------------------------------------------------------
# Validation (schema + counts + shape)
# ---------------------------------------------------------------------------

def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_level_exam(raw: Any, *, language: str = "",
                         level: str = "") -> tuple[bool, list[str]]:
    """Contract: the full shape check — exact item counts, MC option
    sanity, fill blanks, listening script with 2 distinct speakers,
    exactly 3 speaking tasks covering repeat/describe/respond."""
    if not isinstance(raw, dict):
        return False, [f"expected a JSON object, got {type(raw).__name__}"]
    errors: list[str] = []

    # -- vocabulary: exactly 8 MC items
    vocab = raw.get("vocabulary")
    if not isinstance(vocab, list) or len(vocab) != 8:
        errors.append("vocabulary must have exactly 8 items")
    else:
        for i, item in enumerate(vocab):
            _check_mc(item, f"vocabulary[{i}]", errors)

    # -- grammar: exactly 10 = 6 MC + 4 fill
    grammar = raw.get("grammar")
    if not isinstance(grammar, list) or len(grammar) != 10:
        errors.append("grammar must have exactly 10 items")
    else:
        mc = sum(1 for g in grammar if g.get("type") == "mc")
        fill = sum(1 for g in grammar if g.get("type") == "fill")
        if mc != 6 or fill != 4:
            errors.append("grammar needs 6 'mc' + 4 'fill' items")
        for i, item in enumerate(grammar):
            if item.get("type") == "mc":
                _check_mc(item, f"grammar[{i}]", errors)
            elif item.get("type") == "fill":
                if not str(item.get("sentence_with_blank") or "").strip():
                    errors.append(f"grammar[{i}] missing sentence_with_blank")
                if not str(item.get("answer") or "").strip():
                    errors.append(f"grammar[{i}] missing answer")
                if "___" not in str(item.get("sentence_with_blank")):
                    errors.append(f"grammar[{i}] blank must contain ___")
            else:
                errors.append(f"grammar[{i}] type must be mc or fill")

    # -- reading: passage + exactly 5 questions
    reading = raw.get("reading") or {}
    if not str(reading.get("passage") or "").strip():
        errors.append("reading.passage must be a non-empty text")
        reading_questions = []
    else:
        if len(reading["passage"].split()) < 60:
            errors.append("reading.passage too short (min ~60 words)")
        reading_questions = reading.get("questions") or []
    if not isinstance(reading_questions, list) or \
            len(reading_questions) != 5:
        errors.append("reading.questions must have exactly 5 items")
    else:
        for i, item in enumerate(reading_questions):
            _check_mc(item, f"reading.questions[{i}]", errors)

    # -- writing: one task with a word floor
    writing = raw.get("writing") or {}
    if not str(writing.get("prompt") or "").strip():
        errors.append("writing.prompt must be a non-empty task")
    min_words = writing.get("min_words")
    if not _is_int(min_words) or not (30 <= min_words <= 250):
        errors.append("writing.min_words must be an int 30-250")

    # -- listening: 6-8 turn script, 2 distinct speakers, 5 questions
    listening = raw.get("listening") or {}
    script = listening.get("script")
    if not isinstance(script, list) or not (6 <= len(script) <= 8):
        errors.append("listening.script must have 6-8 turns")
    else:
        speakers = {str(s.get("speaker") or "").strip() for s in script}
        if len(speakers) != 2:
            errors.append("listening.script needs exactly 2 distinct "
                          "speakers")
        for i, turn in enumerate(script):
            if not str(turn.get("content") or "").strip():
                errors.append(f"listening.script[{i}] empty content")
    listen_questions = listening.get("questions") or []
    if not isinstance(listen_questions, list) or \
            len(listen_questions) != 5:
        errors.append("listening.questions must have exactly 5 items")
    else:
        for i, item in enumerate(listen_questions):
            _check_mc(item, f"listening.questions[{i}]", errors)

    # -- speaking: exactly 3 tasks: repeat, describe, respond
    speaking = raw.get("speaking")
    if not isinstance(speaking, list) or len(speaking) != 3:
        errors.append("speaking must have exactly 3 tasks")
    else:
        expected = ("repeat", "describe", "respond")
        for i, (task, want) in enumerate(zip(speaking, expected)):
            if task.get("type") != want:
                errors.append(f"speaking[{i}] must be type {want!r}")
            if want == "repeat" and not str(
                    task.get("text") or "").strip():
                errors.append("speaking[0] (repeat) needs text")
            if want == "describe" and not str(
                    task.get("situation") or "").strip():
                errors.append("speaking[1] (describe) needs situation")

    return not errors, errors


def _check_mc(item: Any, path: str, errors: list[str]) -> None:
    if not isinstance(item, dict):
        errors.append(f"{path} must be an object")
        return
    if not str(item.get("question") or "").strip():
        errors.append(f"{path} missing question")
    options = item.get("options")
    if not isinstance(options, list) or len(options) != 4:
        errors.append(f"{path} needs exactly 4 options")
    elif not all(str(o).strip() for o in options):
        errors.append(f"{path} has empty options")
    index = item.get("correct_index")
    if not _is_int(index) or not (0 <= index < 4):
        errors.append(f"{path} correct_index must be 0-3")


# ---------------------------------------------------------------------------
# Generation (Guardrail Loop)
# ---------------------------------------------------------------------------

def generate_level_exam(language: str, level: str, *,
                        client: LmStudioClient | None = None,
                        model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """One complete validated exam for (language, level). Raises
    ValueError on bad inputs; SchemaValidationError after retries."""
    from engines.audio_engine.voice_catalog import language_name
    level = (level or "").strip().lower()
    if level not in ("a1", "a2", "b1", "b2", "c1"):
        raise ValueError("Level must be a1, a2, b1, b2 or c1")
    language = (language or "en").lower()[:2]
    name = language_name(language)

    def validator(parsed: Any) -> tuple[bool, list[str]]:
        return validate_level_exam(parsed)

    exam = run_guardrail_loop(
        PromptRegistry(),
        client if client is not None else LmStudioClient(),
        template="level_exam_generate",
        retry_template="level_exam_retry",
        variables={"level": level, "language_name": name,
                   "difficulty": difficulty_for_level(level)},
        validator=validator,
        model=model,
        max_tokens=6144, temperature=0.5,
    )
    logger.info("Level exam generated: %s %s (%d vocab, %d grammar)",
                language, level, len(exam["vocabulary"]),
                len(exam["grammar"]))
    return exam


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

def grade_objective_sections(exam: dict[str, Any],
                             answers: dict[str, Any]) -> dict[str, Any]:
    """Deterministic grading of vocabulary, grammar, reading,
    listening MC/fill. `answers` shape::

        {"vocabulary": [0-3, ...],              # 8 chosen indices
         "grammar": {"mc": [0-3, ...],          # 6
                      "fill": ["word", ...]},    # 4
         "reading": [0-3, ...],                 # 5
         "listening": [0-3, ...]}               # 5

    Returns per-section (correct, total, pct).
    """
    from engines.language_lab.graders import normalize_answer

    result: dict[str, Any] = {}
    # vocabulary
    chosen = answers.get("vocabulary") or []
    correct = sum(
        1 for i, item in enumerate(exam.get("vocabulary") or [])
        if i < len(chosen)
        and _is_int(chosen[i])
        and chosen[i] == item.get("correct_index"))
    result["vocabulary"] = _section(correct, 8)

    # grammar
    grammar_answers = answers.get("grammar") or {}
    correct = 0
    mc_items = [g for g in exam.get("grammar") or []
                if g.get("type") == "mc"]
    mc_chosen = grammar_answers.get("mc") or []
    for i, item in enumerate(mc_items):
        if i < len(mc_chosen) and _is_int(mc_chosen[i]) \
                and mc_chosen[i] == item.get("correct_index"):
            correct += 1
    fill_items = [g for g in exam.get("grammar") or []
                  if g.get("type") == "fill"]
    fill_chosen = grammar_answers.get("fill") or []
    for i, item in enumerate(fill_items):
        if i < len(fill_chosen):
            given = normalize_answer(str(fill_chosen[i]))
            expected = normalize_answer(str(item.get("answer")))
            if given == expected:
                correct += 1
            elif given and expected and (
                    given in expected or expected in given):
                correct += 1  # generous on tiny typos/variants
    result["grammar"] = _section(correct, 10)

    # reading
    chosen = answers.get("reading") or []
    questions = (exam.get("reading") or {}).get("questions") or []
    correct = sum(
        1 for i, item in enumerate(questions)
        if i < len(chosen) and _is_int(chosen[i])
        and chosen[i] == item.get("correct_index"))
    result["reading"] = _section(correct, 5)

    # listening
    chosen = answers.get("listening") or []
    questions = (exam.get("listening") or {}).get("questions") or []
    correct = sum(
        1 for i, item in enumerate(questions)
        if i < len(chosen) and _is_int(chosen[i])
        and chosen[i] == item.get("correct_index"))
    result["listening"] = _section(correct, 5)
    return result


def _section(correct: int, total: int) -> dict[str, int]:
    return {"correct": correct, "total": total,
            "pct": round(correct / total * 100) if total else 0}


def judge_answer(task: str, answer: str, *, language: str, level: str,
                 client: LmStudioClient | None = None,
                 model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """Rubric-judge one writing or speaking free-form answer.
    Returns {grammar, vocabulary, structure, register, feedback,
    band_estimate} or the graceful-empty dict on model trouble
    (an exam must never die mid-grading)."""
    from engines.audio_engine.voice_catalog import language_name

    def validator(parsed: Any) -> tuple[bool, list[str]]:
        if not isinstance(parsed, dict):
            return False, ["expected a JSON object"]
        errors: list[str] = []
        for key in ("grammar", "vocabulary", "structure", "register"):
            value = parsed.get(key)
            if not _is_int(value) or not (1 <= value <= 5):
                errors.append(f"{key} must be an integer 1-5")
        for key in ("feedback", "band_estimate"):
            if not isinstance(parsed.get(key), str) or not \
                    parsed[key].strip():
                errors.append(f"{key} must be a non-empty string")
        band = str(parsed.get("band_estimate") or "").lower()
        if band not in ("a1", "a2", "b1", "b2", "c1"):
            errors.append("band_estimate must be a1..c1")
        return not errors, errors

    try:
        parsed = run_guardrail_loop(
            PromptRegistry(),
            client if client is not None else LmStudioClient(),
            template="exam_judge",
            retry_template="exam_judge_retry",
            variables={"task": task, "answer": answer,
                       "language_name": language_name(language),
                       "level": level,
                       "difficulty": difficulty_for_level(level)},
            validator=validator,
            model=model,
            max_tokens=3072, temperature=0.2,
        )
        return parsed
    except Exception as exc:  # noqa: BLE001 — grading must continue
        logger.warning("Judge failed (%s) — section ungraded", exc)
        return {"grammar": 3, "vocabulary": 3, "structure": 3,
                "register": 3, "feedback":
                "This answer could not be auto-graded (model "
                "trouble) — counted as a neutral 3/5, not against "
                "you.", "band_estimate": level}


def grade_speaking_repeat(target_text: str, transcript: str) -> float:
    """Similarity score 0..1 for the repeat-aloud task, using the
    same normalization as the graders. Honest: it measures how close
    the words E.T. heard were to the target — clarity + content."""
    from engines.language_lab.graders import normalize_answer
    a = normalize_answer(target_text)
    b = normalize_answer(transcript)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Result assembly: scores, bands, recommendations
# ---------------------------------------------------------------------------

def build_exam_result(exam: dict[str, Any],
                      objective: dict[str, Any],
                      writing_judged: dict[str, Any],
                      speaking_scores: list[dict[str, Any]],
                      *, language: str, level: str) -> dict[str, Any]:
    """Assemble the full result document: per-section scores, overall,
    pass/fail, per-skill band estimates, and recommendations pointing
    at real curriculum slots — the owner's 'full evaluations and
    recommendations' demand."""
    sections: dict[str, Any] = {}
    for name in ("vocabulary", "grammar", "reading", "listening"):
        sections[name] = dict(objective.get(name) or
                              _section(0, 1))
    # writing: rubric mean 1-5 -> pct
    writing_pct = _rubric_pct(writing_judged)
    sections["writing"] = {"pct": writing_pct,
                           "feedback": writing_judged.get("feedback",
                                                          ""),
                           "band": writing_judged.get("band_estimate")}
    # speaking: mean of the 3 task scores (each 0..1 + band from
    # describe/respond judgments if provided)
    task_pcts = [max(0.0, min(1.0, float(t.get("score", 0.0)))) * 100
                 for t in speaking_scores]
    speaking_pct = round(sum(task_pcts) / len(task_pcts)) \
        if task_pcts else 0
    bands = [t.get("band") for t in speaking_scores if t.get("band")]
    sections["speaking"] = {"pct": speaking_pct,
                            "band": _mode_band(bands) if bands else None}

    overall = round(sum(
        sections[name]["pct"] * weight
        for name, weight in SECTION_WEIGHTS.items()) / 100)
    passed = overall >= PASS_THRESHOLD

    # per-skill bands across the exam (writing/speaking judged bands
    # + objective pct mapped onto the level)
    skill_bands = {
        "writing": writing_judged.get("band_estimate"),
        "speaking": sections["speaking"]["band"],
        "reading": _pct_band(sections["reading"]["pct"], level),
        "listening": _pct_band(sections["listening"]["pct"], level),
        "grammar": _pct_band(sections["grammar"]["pct"], level),
        "vocabulary": _pct_band(sections["vocabulary"]["pct"], level),
    }

    return {
        "language": language, "level": level,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "sections": sections,
        "overall": overall,
        "passed": passed,
        "threshold": PASS_THRESHOLD,
        "skill_bands": {k: v for k, v in skill_bands.items() if v},
        "recommendations": _recommendations(sections, skill_bands,
                                           language, level),
        "verdict_line": _verdict_line(overall, passed, level),
    }


def _rubric_pct(judged: dict[str, Any]) -> int:
    values = [judged.get(k) for k in
              ("grammar", "vocabulary", "structure", "register")]
    ints = [v for v in values if _is_int(v) and 1 <= v <= 5]
    if not ints:
        return 0
    return round(sum(ints) / len(ints) / 5 * 100)


def _pct_band(pct: int, level: str) -> str:
    ladder = ("a1", "a2", "b1", "b2", "c1")
    position = ladder.index(level) if level in ladder else 0
    if pct >= 85:
        shift = 1
    elif pct < 50:
        shift = -1
    else:
        shift = 0
    return ladder[max(0, min(len(ladder) - 1, position + shift))]


def _mode_band(bands: list[str]) -> str:
    counts: dict[str, int] = {}
    for band in bands:
        counts[band] = counts.get(band, 0) + 1
    return max(counts, key=counts.get)


def _recommendations(sections: dict[str, Any],
                     skill_bands: dict[str, str],
                     language: str, level: str) -> list[str]:
    """Concrete remediation pointing at curriculum slots (the library
    closes the loop — exam failure has a next step, always)."""
    from engines.language_lab.cefr import lesson_slots, slot_for
    tips: list[str] = []
    domain_by_slot = {s.key: s for s in lesson_slots(level)}

    def _slot_for_topic(section: str) -> str:
        mapping = {
            "vocabulary": {"a1": "a1-shopping_money",
                            "a2": "a2-leisure_media",
                            "b1": "b1-people_friends",
                            "b2": "b2-leisure_media",
                            "c1": "c1-people_friends"},
            "grammar": {"a1": "a1-people_friends",
                         "a2": "a2-home_admin",
                         "b1": "b1-work_school",
                         "b2": "b2-work_school",
                         "c1": "c1-work_school"},
            "reading": {"a1": "a1-food_dining",
                         "a2": "a2-people_friends",
                         "b1": "b1-leisure_media",
                         "b2": "b2-leisure_media",
                         "c1": "c1-leisure_media"},
            "listening": {"a1": "a1-transport_travel",
                           "a2": "a2-health_body",
                           "b1": "b1-transport_travel",
                           "b2": "b2-transport_travel",
                           "c1": "c1-food_dining"},
            "writing": {"a1": "a1-home_admin",
                         "a2": "a2-work_school",
                         "b1": "b1-services_authorities",
                         "b2": "b2-services_authorities",
                         "c1": "c1-services_authorities"},
            "speaking": {"a1": "a1-people_friends",
                          "a2": "a2-people_friends",
                          "b1": "b1-feelings_opinions",
                          "b2": "b2-feelings_opinions",
                          "c1": "c1-feelings_opinions"},
        }
        return mapping.get(section, {}).get(level, "")

    weak = sorted(sections.items(), key=lambda kv: kv[1]["pct"])[:2]
    for name, data in weak:
        if data["pct"] >= 80:
            continue
        slot_key = _slot_for_topic(name)
        slot = slot_for(slot_key)
        tip = (f"{name.capitalize()} was your softest section "
               f"({data['pct']}%). ")
        if slot:
            tip += (f"Revisit the library lesson "
                    f"\"{slot.title}\" ({level}) — then try E.T. "
                    "conversation practice on the same topic.")
        else:
            tip += "Practice it with E.T. — he never tires."
        tips.append(tip)
    if not tips:
        tips.append(
            "Nothing weak anywhere — every section 80%+. Your next "
            "move: the next level's exam, or a long free-talk with "
            "E.T. to stretch. 👽")
    return tips


def _verdict_line(overall: int, passed: bool, level: str) -> str:
    if passed and overall >= 90:
        return (f"{level.upper()} demolished — {overall}%. The next "
                "level is lucky to have you. 🚀")
    if passed:
        return (f"{level.upper()} passed at {overall}% — solid work. "
                "A little polish and the next level will feel the "
                "same. 💪")
    return (f"{level.upper()} at {overall}% — not yet, and that's "
            "fine. The recommendations below know exactly where "
            "you'll win it back. 🌱")
