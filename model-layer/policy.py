# model-layer/policy.py
#
# WHAT: Model-aware generation policy — the "skills" injected into every
#       guardrail generation so 7B/12B/14B local models behave.
# WHY:  The owner directive (2026-09-05): any selected model 7B-14B
#       must perform just fine with tools calling — the app injects the
#       plugins and skills needed. Correctness comes from the Model
#       Layer, not model size (CONSTITUTION.md §3). This module turns
#       that into four concrete levers the pipeline applies uniformly:
#         1. A JSON-discipline addendum appended to every system prompt
#            (fences, MMdd blocks, Python booleans, one-line strings).
#         2. JSON mode (response_format json_object) with automatic
#            fallback when the runtime rejects it.
#         3. Thinking suppression (reasoning_effort=none) with the same
#            capability-mismatch fallback — reasoning models must not
#            spend the whole token budget on chain-of-thought.
#         4. Size-aware attempt scaling: smaller models get more retry
#            budget instead of a failure wall.
# BREAKS IF DELETED: Every engine regresses to trusting the bare model;
#       format errors resurface as "model kept producing invalid
#       content".

from __future__ import annotations

import re
from typing import Any, Optional

__all__ = [
    "JSON_DISCIPLINE_ADDENDUM",
    "policy_for",
    "estimate_model_size",
    "size_label",
    "CEFR_DIFFICULTY",
    "difficulty_for_level",
]

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
    must treat None as "unknown", never as zero. (Canonical home is
    model_layer.policy; capabilities.py re-exports it.)
    """
    if not model_id:
        return None
    matches = _SIZE_RE.findall(model_id)
    if not matches:
        return None
    return float(matches[-1])

JSON_DISCIPLINE_ADDENDUM = (
    "OUTPUT RULES — NON-NEGOTIABLE:\n"
    "- Reply with exactly ONE valid JSON object, nothing else.\n"
    "- Start the reply with {{ and end it with }}.\n"
    "- No prose, fences, or commentary around it.\n"
    "- Begin the JSON immediately without preamble, then write it "
    "COMPLETELY: every field full with real content, never empty "
    "strings — an unfinished object always fails.\n"
    "- Keep fields focused (no rambling) but complete."
)

# Below this size, one extra feedback attempt pays for itself.
SMALL_MODEL_ATTEMPTS = 5
DEFAULT_ATTEMPTS = 3
SMALL_MODEL_B = 7.0


def policy_for(model_id: str) -> dict[str, Any]:
    """
    Contract: the generation policy for one model id.

    Returns:
        {
          "system_addendum": str,     # appended to every system prompt
          "max_attempts": int,        # feedback-retry budget
          "json_mode": True,          # ask the runtime for JSON output
          "disable_thinking": True,   # reasoning_effort=none on every
                                      # call (runtime-rejection fallback
                                      # handled in pipeline)
        }

    The addendum is universal (it helps every size); attempts scale for
    models whose id parses to < 7B. Unknown sizes get the default
    budget — never punished for being unparseable.
    """
    size = estimate_model_size(model_id) if model_id else None
    max_attempts = (
        SMALL_MODEL_ATTEMPTS
        if size is not None and size < SMALL_MODEL_B
        else DEFAULT_ATTEMPTS
    )
    return {
        "system_addendum": JSON_DISCIPLINE_ADDENDUM,
        "max_attempts": max_attempts,
        "json_mode": True,
        "disable_thinking": True,
    }


def size_label(model_id: str) -> Optional[str]:
    """Contract: short human label ('~14B' / '~7B' / None) for UI text."""
    size = estimate_model_size(model_id) if model_id else None
    return f"~{size:g}B" if size is not None else None


# ---------------------------------------------------------------------------
# CEFR difficulty descriptors (2026-09-07)
# ---------------------------------------------------------------------------
#
# Measured live on gemma-4-12b: CEFR jargon ("CEFR band", "a1-level")
# in prompts triggers multi-thousand-token deliberation spirals about
# difficulty calibration (4000+ thinking tokens, zero content), while
# plain-language difficulty words complete normally. So: prompts speak
# plain difficulty; codes live ONLY in validators, storage, and UI.
# This map is the single translation point.

CEFR_DIFFICULTY: dict[str, str] = {
    "a1": "absolute beginner",
    "a2": "elementary",
    "b1": "intermediate",
    "b2": "upper-intermediate",
    "c1": "advanced",
}


def difficulty_for_level(level: str) -> str:
    """'a1' -> 'absolute beginner'; unknown codes pass through as
    plain words (beginner/intermediate/advanced already are)."""
    code = (level or "").strip().lower()
    if code in CEFR_DIFFICULTY:
        return CEFR_DIFFICULTY[code]
    return code or "beginner"
