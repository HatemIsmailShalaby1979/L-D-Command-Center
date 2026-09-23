# engines/export-engine/detect.py
#
# WHAT: Content-type detection for the export dispatcher.
# WHY:  P4.1 split of the former 1004-line export god-module (CONSTITUTION
#       §4): one file per concern so layout bugs localize to one adapter.
# BREAKS IF DELETED: the dispatcher cannot route content safely.

from __future__ import annotations

from typing import Any
import logging

logger = logging.getLogger(__name__)

def _detect_type(data: dict[str, Any]) -> str:
    """
    Contract: detect whether the data dict is a Journey, Resume, or audio type.

    Detection heuristic:
      - 'topic' + 'cards' keys → 'journey'
      - 'contact' + 'experience' keys → 'resume'
      - 'target_language' + 'known_language' keys → 'bilingual'
      - 'topic' + 'target_language' + 'segments' keys → 'immersion'
      - 'topic' + 'host_name' keys (no 'cards') → 'podcast'
      - 'text' key (and not any of the above) → 'narration'
      - otherwise → 'unknown'

    Returns:
        'journey', 'resume', 'bilingual', 'immersion', 'podcast',
        'narration', or 'unknown'
    """
    if "topic" in data and "cards" in data:
        return "journey"
    if "contact" in data and "experience" in data:
        return "resume"
    if "target_language" in data and "known_language" in data:
        return "bilingual"
    if "topic" in data and "target_language" in data and "segments" in data:
        return "immersion"
    if "topic" in data and "host_name" in data:
        return "podcast"
    if "text" in data:
        return "narration"
    return "unknown"


# ---------------------------------------------------------------------------
# Journey exports
# ---------------------------------------------------------------------------
