# model-layer/capabilities.py
#
# WHAT: Capability profiles for the app's task families plus a one-shot
#       probe that grades whatever model LM Studio has loaded, storing the
#       verdict through Storage (P7.1).
# WHY:  Small local models do not need plugins to drive this app — the
#       Generation Pipeline is the wheel. What size changes is how often
#       the retry loop fires and which tasks are realistic at all
#       (docs/PLAYGROUND_AND_LANGUAGE_LAB_PLAN.md Part A). The probe turns
#       that reality into honest UX: the shell health bar shows
#       "ready" or "degraded: <task> may need review" instead of magic.
#       The probe never blocks generation; it informs it.
# BREAKS IF DELETED: The shell loses per-task readiness; users discover
#       small-model limits by failure instead of by warning.

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from model_layer.client import ApiError, LmStudioClient
from model_layer.pipeline import generate as run_guardrail_loop
from model_layer.prompts import PromptRegistry
from model_layer.schema import SchemaValidationError
from storage.persistence import Storage, default_storage

logger = logging.getLogger(__name__)

__all__ = [
    "TaskProfile",
    "TASK_PROFILES",
    "estimate_model_size",
    "probe_model_capabilities",
    "latest_verdict",
    "summarize_verdict",
]

_VERDICT_PREF = "capability_verdict"


# ---------------------------------------------------------------------------
# Size estimation from a model id (best-effort)
# ---------------------------------------------------------------------------

_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*b(?![a-z0-9])", re.IGNORECASE)


def estimate_model_size(model_id: str) -> Optional[float]:
    """
    Contract: best-effort parameter count (in billions) parsed from an
    LM Studio model id such as "deepseek-r1-0528-qwen3-8b",
    "gemma-4-12b-qat", "qwen3:14b", or "llama-3.2-3b-instruct".

    Returns None when the id carries no parseable size hint — callers
    must treat None as "unknown", never as zero.
    """
    matches = _SIZE_RE.findall(model_id)
    if not matches:
        return None
    return float(matches[-1])


# ---------------------------------------------------------------------------
# Probe validators — schema discipline only; semantics stay human-reviewed
# ---------------------------------------------------------------------------

def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_journey_probe(parsed: Any) -> tuple[bool, list[str]]:
    if not isinstance(parsed, dict):
        return False, ["expected a JSON object"]
    errors: list[str] = []
    if not _nonempty_str(parsed.get("topic")):
        errors.append("topic must be a non-empty string")
    if parsed.get("level") not in {"beginner", "intermediate", "advanced"}:
        errors.append("level must be beginner|intermediate|advanced")
    cards = parsed.get("cards")
    if not isinstance(cards, list) or len(cards) != 1:
        errors.append("cards must be a list with exactly one card")
    else:
        card = cards[0]
        required = ("id", "title", "content", "question", "explanation")
        errors += [f"card.{k} must be a non-empty string"
                   for k in required if not _nonempty_str(card.get(k))]
        options = card.get("options")
        if not isinstance(options, list) or not (2 <= len(options) <= 4):
            errors.append("card.options must be a list of 2-4 strings")
        elif card.get("correct_option") not in options:
            errors.append("card.correct_option must match one of options")
    return not errors, errors


def _validate_resume_probe(parsed: Any) -> tuple[bool, list[str]]:
    if not isinstance(parsed, dict):
        return False, ["expected a JSON object"]
    errors: list[str] = []
    contact = parsed.get("contact")
    if not isinstance(contact, dict):
        errors.append("contact must be an object")
    else:
        if not _nonempty_str(contact.get("name")):
            errors.append("contact.name must be a non-empty string")
        if "@" not in str(contact.get("email") or ""):
            errors.append("contact.email must look like an email")
    if not _nonempty_str(parsed.get("summary")):
        errors.append("summary must be a non-empty string")
    skills = parsed.get("skills")
    if not isinstance(skills, list) or not skills or not all(_nonempty_str(s) for s in skills):
        errors.append("skills must be a non-empty list of strings")
    return not errors, errors


def _validate_bilingual_probe(parsed: Any) -> tuple[bool, list[str]]:
    if not isinstance(parsed, dict):
        return False, ["expected a JSON object"]
    errors: list[str] = []
    target, translation = parsed.get("target_text"), parsed.get("translation_text")
    if not _nonempty_str(target):
        errors.append("target_text must be a non-empty string")
    if not _nonempty_str(translation):
        errors.append("translation_text must be a non-empty string")
    if _nonempty_str(target) and target == translation:
        errors.append("target_text and translation_text must differ")
    return not errors, errors


def _validate_grammar_probe(parsed: Any) -> tuple[bool, list[str]]:
    if not isinstance(parsed, dict):
        return False, ["expected a JSON object"]
    errors = [f"{k} must be a non-empty string"
              for k in ("point", "explanation", "example")
              if not _nonempty_str(parsed.get(k))]
    return not errors, errors


def _validate_podcast_probe(parsed: Any) -> tuple[bool, list[str]]:
    if not isinstance(parsed, dict):
        return False, ["expected a JSON object"]
    segments = parsed.get("segments")
    if not isinstance(segments, list) or len(segments) != 2:
        return False, ["segments must be a list with exactly two turns"]
    errors: list[str] = []
    speakers: list[str] = []
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            errors.append(f"segments[{i}] must be an object")
            continue
        speaker, content = seg.get("speaker"), seg.get("content")
        if not _nonempty_str(speaker):
            errors.append(f"segments[{i}].speaker must be a non-empty string")
        else:
            speakers.append(str(speaker))
        if not _nonempty_str(content):
            errors.append(f"segments[{i}].content must be a non-empty string")
    if len(set(speakers)) != len(speakers):
        errors.append("the two dialogue turns must have distinct speakers")
    return not errors, errors


def _validate_summary_probe(parsed: Any) -> tuple[bool, list[str]]:
    if not isinstance(parsed, dict):
        return False, ["expected a JSON object"]
    errors: list[str] = []
    if not _nonempty_str(parsed.get("summary")):
        errors.append("summary must be a non-empty string")
    takeaways = parsed.get("key_takeaways")
    if not isinstance(takeaways, list) or not takeaways or not all(_nonempty_str(t) for t in takeaways):
        errors.append("key_takeaways must be a non-empty list of strings")
    return not errors, errors


# ---------------------------------------------------------------------------
# Task profiles (plan Part A table)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TaskProfile:
    """
    Contract: one app task family and what the loaded model needs to run
    it comfortably.

    Fields:
        name: stable identifier used in verdicts and UI text.
        min_b: comfortable-from model size in billions of parameters.
        review_note: user-facing phrase shown when degraded/failed.
        verify_below_b: below this size an extra verification pass is
            mandatory for the task (None = no extra pass).
        task_instruction / expected_shape: the tiny calibration prompt.
        validator: probe output validation (parsed) -> (ok, errors).
    """
    name: str
    min_b: float
    review_note: str
    task_instruction: str
    expected_shape: str
    validator: Callable[[Any], tuple[bool, list[str]]]
    verify_below_b: Optional[float] = None


TASK_PROFILES: dict[str, TaskProfile] = {
    "journey_cards": TaskProfile(
        name="journey_cards",
        min_b=7,
        review_note="journey cards may need frequent retries",
        task_instruction='Create one mini learning card for the topic "clocks".',
        expected_shape=(
            '{\n'
            '  "topic": "<topic string>",\n'
            '  "level": "<beginner|intermediate|advanced>",\n'
            '  "cards": [\n'
            '    {\n'
            '      "id": "card-1",\n'
            '      "title": "...",\n'
            '      "content": "...",\n'
            '      "question": "...",\n'
            '      "options": ["...", "..."],\n'
            '      "correct_option": "<one of options>",\n'
            '      "explanation": "..."\n'
            '    }\n'
            '  ]\n'
            '}'
        ),
        validator=_validate_journey_probe,
    ),
    "resume_generation": TaskProfile(
        name="resume_generation",
        min_b=7,
        review_note="resumes may need review",
        task_instruction='Draft a mini resume snippet for "Ada Lovelace, mathematician".',
        expected_shape=(
            '{\n'
            '  "contact": {"name": "...", "email": "..."},\n'
            '  "summary": "...",\n'
            '  "skills": ["..."]\n'
            '}'
        ),
        validator=_validate_resume_probe,
    ),
    "bilingual_translation": TaskProfile(
        name="bilingual_translation",
        min_b=7,
        review_note="translations may need review",
        verify_below_b=14,
        task_instruction='Translate "The library closes at eight." into Spanish.',
        expected_shape=(
            '{\n'
            '  "target_text": "<the Spanish sentence>",\n'
            '  "translation_text": "<the English sentence>"\n'
            '}'
        ),
        validator=_validate_bilingual_probe,
    ),
    "grammar_explanations": TaskProfile(
        name="grammar_explanations",
        min_b=12,
        review_note="grammar explanations may need review",
        task_instruction='Explain in one sentence when Spanish uses "ser" vs "estar".',
        expected_shape=(
            '{\n'
            '  "point": "<grammar point>",\n'
            '  "explanation": "...",\n'
            '  "example": "..."\n'
            '}'
        ),
        validator=_validate_grammar_probe,
    ),
    "podcast_dialogue": TaskProfile(
        name="podcast_dialogue",
        min_b=7,
        review_note="podcast dialogue may need review",
        task_instruction='Write a two-turn dialogue between Ana and Ben about morning routines.',
        expected_shape=(
            '{\n'
            '  "segments": [\n'
            '    {"speaker": "Ana", "content": "..."},\n'
            '    {"speaker": "Ben", "content": "..."}\n'
            '  ]\n'
            '}'
        ),
        validator=_validate_podcast_probe,
    ),
    "summarization": TaskProfile(
        name="summarization",
        min_b=3,
        review_note="summaries may be shallow",
        task_instruction=(
            'Summarize this text: "Bees pollinate crops. '
            'Without them, harvests shrink."'
        ),
        expected_shape=(
            '{\n'
            '  "summary": "...",\n'
            '  "key_takeaways": ["..."]\n'
            '}'
        ),
        validator=_validate_summary_probe,
    ),
}


# ---------------------------------------------------------------------------
# One-shot probe + verdict persistence
# ---------------------------------------------------------------------------

def _model_slug(model_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", model_id.lower()).strip("-")
    return slug or "model"


def _grade(profile: TaskProfile, passed: bool, size: Optional[float],
           error_detail: str) -> dict[str, str]:
    """Turn one probe outcome into a verdict record for one task."""
    if not passed:
        return {"status": "failed", "detail": error_detail}
    detail_parts: list[str] = []
    if size is None:
        status = "degraded"
        detail_parts.append(f"probe passed but model size unknown from id")
    elif size >= profile.min_b:
        status = "ready"
    else:
        status = "degraded"
        detail_parts.append(f"~{size:g}B is below the ~{profile.min_b:g}B comfort threshold")
    if profile.verify_below_b is not None and (size is None or size < profile.verify_below_b):
        detail_parts.append("mandatory verification pass will run automatically")
    return {"status": status, "detail": "; ".join(detail_parts)}


def probe_model_capabilities(
    client: LmStudioClient,
    *,
    storage: Optional[Storage] = None,
) -> dict[str, Any]:
    """
    Contract: grade the model LM Studio currently has loaded, one shot
    per task family — NO feedback retries, because a first-try miss is
    exactly what the probe measures.

    Returns the verdict document:

        {
          "model_id": ..., "estimated_params_b": <float|null>,
          "probed_at": "<ISO timestamp>", "overall": "ready|degraded|failed",
          "tasks": {<profile name>: {"status": ..., "detail": ...}},
        }

    The document is saved under storage kind "capabilities" (named after
    the model) and recorded as the current verdict via preferences.

    Raises:
        ConnectionError / ApiError: LM Studio unreachable or broken;
            nothing is graded and nothing is stored.
        ApiError: LM Studio reports no loaded model.
    """
    storage = storage if storage is not None else default_storage()

    models = client.list_models()
    if not models:
        raise ApiError(
            "LM Studio has no model loaded — load one before probing capabilities."
        )
    model_id = models[0]
    size = estimate_model_size(model_id)

    registry = PromptRegistry()
    tasks: dict[str, dict[str, str]] = {}
    for profile in TASK_PROFILES.values():
        try:
            run_guardrail_loop(
                registry,
                client,
                template="capability_probe",
                variables={
                    "task_instruction": profile.task_instruction,
                    "expected_shape": profile.expected_shape,
                },
                validator=profile.validator,
                model=model_id,
                max_attempts=1,
                max_tokens=512,
                temperature=0.0,
            )
            passed, detail = True, ""
        except SchemaValidationError as exc:
            passed, detail = False, "; ".join(exc.errors[:3])
        except ApiError as exc:
            passed, detail = False, f"model API error: {exc}"
        tasks[profile.name] = _grade(profile, passed, size, detail)
        logger.info("Capability probe %s/%s -> %s", model_id, profile.name,
                    tasks[profile.name]["status"])

    statuses = {t["status"] for t in tasks.values()}
    overall = ("failed" if "failed" in statuses
               else "degraded" if "degraded" in statuses
               else "ready")

    verdict = {
        "model_id": model_id,
        "estimated_params_b": size,
        "probed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "overall": overall,
        "tasks": tasks,
    }
    name = f"{_model_slug(model_id)}.json"
    storage.save_artifact("capabilities", name, verdict)
    storage.set_preference(_VERDICT_PREF, name)
    return verdict


def latest_verdict(storage: Optional[Storage] = None) -> Optional[dict[str, Any]]:
    """
    Contract: return the most recently probed verdict document, or None
    when no probe has ever run (offline read — never touches the model).
    """
    storage = storage if storage is not None else default_storage()
    name = storage.get_preference(_VERDICT_PREF)
    if not name:
        return None
    try:
        return storage.load_artifact("capabilities", name)
    except FileNotFoundError:
        logger.warning("Capability verdict %s vanished; treating as unprobed", name)
        return None


def summarize_verdict(verdict: dict[str, Any]) -> str:
    """
    Contract: one health-bar line for a verdict document, e.g.

        gpt-local-8b (~8B): ready
        gpt-local-8b (~8B): degraded — translations may need review; ...
    """
    model_id = verdict.get("model_id", "?")
    size = verdict.get("estimated_params_b")
    head = f"{model_id}" + (f" (~{size:g}B)" if size else "")
    problems = [
        f"{name}: {record.get('detail') or profile.review_note}"
        if record.get("status") == "failed"
        else f"{profile.review_note}"
        for name, record in verdict.get("tasks", {}).items()
        if (profile := TASK_PROFILES.get(name)) and record.get("status") != "ready"
    ]
    overall = verdict.get("overall", "unknown")
    line = f"{head}: {overall}"
    if problems:
        line += " — " + "; ".join(problems)
    return line
