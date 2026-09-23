# model-layer/quickstart.py
#
# WHAT: The "tiny model quick-start" — a curated, size-aware list of
#       known-good local models plus the one-paragraph instructions a
#       first-run user needs to get generating in minutes.
# WHY:  PROFIT_PLAN §8 risk #1 (model dependency): the app is useless
#       until the user has a working local model, and the wrong pick (a
#       70B on 8 GB of RAM, or a base model with no instruct tuning)
#       is the single most likely reason a new install never produces a
#       first lesson pack. Rather than shipping 4 GB of weights, the app
#       tells the user exactly what to search for in LM Studio — cheap,
#       offline, always current.
# BREAKS IF DELETED: The first-run experience has no answer to "which
#       model should I download?" — the top of the funnel leaks.
#
# NOTE: entries carry SEARCH TERMS, not pinned repo ids. Model hubs
# rename and re-quantize constantly; a wrong id is worse than a search
# string that always resolves. Sizes are nominal parameter counts.

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = ["QUICKSTART_MODELS", "recommended_models", "quickstart_hint",
           "LM_STUDIO_SEARCH_URL"]

LM_STUDIO_SEARCH_URL = "https://lmstudio.ai/models"

# Every entry is instruct-tuned (the app drives models with structured
# JSON prompts; base completions models fail the schema guardrails) and
# small enough to run on consumer hardware.
QUICKSTART_MODELS: tuple[dict[str, Any], ...] = (
    {
        "name": "Qwen 2.5 7B Instruct",
        "search": "qwen2.5-7b-instruct",
        "params_b": 7.6,
        "quantization": "Q4_K_M",
        "min_ram_gb": 8,
        "why": "Best all-rounder for the lesson-pack and resume "
               "schemas; strong non-English output (ja/ko/zh/ar).",
        "recommended": True,
    },
    {
        "name": "Mistral 7B Instruct v0.3",
        "search": "mistral-7b-instruct-v0.3",
        "params_b": 7.2,
        "quantization": "Q4_K_M",
        "min_ram_gb": 8,
        "why": "Fast, tidy JSON; a safe fallback when Qwen drifts.",
        "recommended": False,
    },
    {
        "name": "Llama 3.1 8B Instruct",
        "search": "llama-3.1-8b-instruct",
        "params_b": 8.0,
        "quantization": "Q4_K_M",
        "min_ram_gb": 10,
        "why": "Best English prose (cover letters, LinkedIn posts).",
        "recommended": False,
    },
    {
        "name": "Gemma 2 9B Instruct",
        "search": "gemma-2-9b-it",
        "params_b": 9.2,
        "quantization": "Q4_K_M",
        "min_ram_gb": 12,
        "why": "Stronger grammar explanations; needs more RAM.",
        "recommended": False,
    },
    {
        "name": "Qwen 2.5 3B Instruct",
        "search": "qwen2.5-3b-instruct",
        "params_b": 3.1,
        "quantization": "Q4_K_M",
        "min_ram_gb": 4,
        "why": "Low-memory machines. Expect more retries — the "
               "pipeline raises the attempt budget below 7B.",
        "recommended": False,
    },
)


def recommended_models(*, ram_gb: Optional[float] = None) -> list[dict[str, Any]]:
    """Models this machine can actually run, best pick first.

    `ram_gb` filters by the entry's min_ram_gb; omit it and everything
    is returned in the curated order (recommended flag, then size).
    """
    models = list(QUICKSTART_MODELS)
    if ram_gb is not None:
        models = [m for m in models if float(ram_gb) >= m["min_ram_gb"]]
        if not models:
            # Never answer "nothing works" — return the smallest pick so
            # the user still gets a concrete next step.
            models = [min(QUICKSTART_MODELS,
                          key=lambda m: m["min_ram_gb"])]
    return sorted(models, key=lambda m: (not m["recommended"],
                                         m["min_ram_gb"]))


def quickstart_hint(loaded_models: Optional[list[str]] = None,
                    *, ram_gb: Optional[float] = None) -> str:
    """The first-run paragraph: what to install, where, and what to
    expect. Shown when LM Studio is reachable but nothing is loaded
    (or not running at all)."""
    picks = recommended_models(ram_gb=ram_gb)
    best = picks[0] if picks else QUICKSTART_MODELS[0]
    if loaded_models:
        return (f"Loaded: {', '.join(loaded_models[:3])}. For the best "
                f"lesson packs, {best['name']} or larger is recommended.")
    lines = [
        "No model loaded yet — the app needs one local model and does "
        "not download anything on its own.",
        f"1. Open LM Studio → Discover, and search for: {best['search']}",
        f"2. Pick the {best['quantization']} quant (~{best['params_b']:.0f}B, "
        f"needs ~{best['min_ram_gb']} GB RAM).",
        "3. Load it, then press Refresh above. Any instruct-tuned 7B "
        "model works; bigger is slower but better.",
        f"Browse alternatives: {LM_STUDIO_SEARCH_URL}",
    ]
    others = ", ".join(m["search"] for m in picks[1:3])
    if others:
        lines.insert(2, f"   Alternatives: {others}.")
    return "\n".join(lines)
