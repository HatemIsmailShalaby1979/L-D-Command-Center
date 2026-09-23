# engines/language-lab/catalog_store.py
#
# WHAT: "My Library" — the per-language curriculum progress store:
#       which slots are generated, which are done (scored), per-level
#       progress, and the next-lesson pointer.
# WHY:  Owner directive 2026-09-06: users must find a library and
#       ready-made catalogue per level, and the app must PUSH them
#       along the journey. This store is the journey state — persisted
#       through Storage preferences (offline, backup-safe), updated by
#       generation (auto-register) and by quiz completion (mark_done
#       feeds the SRS too). Zero LLM, fully testable.
# BREAKS IF DELETED: Progress evaporates between sessions; the
#       curriculum becomes a poster instead of a journey.

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from storage.persistence import Storage

logger = logging.getLogger(__name__)

__all__ = ["CatalogStore", "curriculum_index_key"]

curriculum_index_key = "curriculum_index"


class CatalogStore:
    """Contract: per-language curriculum state. Shape (one Storage
    preference)::

        {"<lang>": {"<slot_key>": {
            "status": "todo" | "generated" | "done",
            "score": <0-100 or None>,
            "pack_name": "<lesson_packs artifact>",
            "at": "<ISO timestamp>"}}}

    Written by: catalog_register (generation), mark_done (quiz),
    mark_generated. Read by: catalog_index (UI), level_progress,
    next_lesson (the "continue learning" pointer).
    """

    def __init__(self, storage: Storage):
        self.storage = storage

    def _load(self) -> dict[str, Any]:
        raw = self.storage.get_preference(curriculum_index_key, {}) or {}
        return raw if isinstance(raw, dict) else {}

    def _save(self, data: dict[str, Any]) -> None:
        self.storage.set_preference(curriculum_index_key, data)

    # -- writes --------------------------------------------------------------

    def mark_generated(self, language: str, slot_key: str,
                       pack_name: str) -> None:
        language = (language or "").lower()[:2]
        data = self._load()
        lang = data.setdefault(language, {})
        record = lang.get(slot_key) or {}
        # 'done' must never be downgraded by a re-generation
        if record.get("status") == "done":
            record = {**record, "pack_name": pack_name,
                      "regenerated_at": _now()}
        else:
            record = {"status": "generated", "score": None,
                      "pack_name": pack_name, "at": _now()}
        lang[slot_key] = record
        self._save(data)
        logger.info("Catalog: %s/%s generated -> %s", language,
                    slot_key, pack_name)

    def mark_done(self, language: str, slot_key: str,
                  score_pct: int) -> None:
        """Lesson quiz passed: mark done with score. Also queues the
        pack's vocab into the SRS (P7.6) when the caller hands the
        pack over."""
        language = (language or "").lower()[:2]
        data = self._load()
        lang = data.setdefault(language, {})
        record = lang.get(slot_key) or {"status": "generated",
                                        "pack_name": None, "at": _now()}
        record = {**record, "status": "done",
                  "score": max(0, min(100, int(score_pct))),
                  "done_at": _now()}
        lang[slot_key] = record
        self._save(data)
        logger.info("Catalog: %s/%s DONE at %d%%", language, slot_key,
                    score_pct)

    def reset_slot(self, language: str, slot_key: str) -> None:
        data = self._load()
        lang = data.get((language or "").lower()[:2]) or {}
        lang.pop(slot_key, None)
        self._save(data)

    # -- reads ----------------------------------------------------------------

    def slot_status(self, language: str, slot_key: str) -> dict[str, Any]:
        lang = self._load().get((language or "").lower()[:2]) or {}
        record = lang.get(slot_key)
        if not isinstance(record, dict):
            return {"status": "todo", "score": None,
                    "pack_name": None}
        return {"status": str(record.get("status") or "todo"),
                "score": record.get("score"),
                "pack_name": record.get("pack_name")}

    def catalog_index(self, language: str) -> list[dict[str, Any]]:
        """cefr.catalog_index merged with this user's progress — THE
        library view. Slots carry status/score; levels carry progress
        percentages. Zero LLM."""
        from engines.language_lab.cefr import catalog_index
        rows = catalog_index(language)
        by_key = {r["key"]: r for r in rows if r["kind"] == "slot"}
        for key, row in by_key.items():
            row.update(self.slot_status(language, key))
        for row in rows:
            if row.get("kind") == "level" and row.get("level") != "c2":
                row["progress"] = self.level_progress(language,
                                                      row["level"])
        return rows

    def level_progress(self, language: str, level: str) -> int:
        """Percent of a level's slots marked done (0-100)."""
        from engines.language_lab.cefr import lesson_slots
        slots = lesson_slots(level)
        done = sum(1 for slot in slots
                   if self.slot_status(language, slot.key)["status"]
                   == "done")
        return round(done / len(slots) * 100) if slots else 0

    def next_lesson(self, language: str) -> Optional[dict[str, Any]]:
        """The 'continue learning' pointer: first todo slot, else the
        first generated-but-not-done, else None (curriculum complete —
        a genuinely proud moment)."""
        from engines.language_lab.cefr import LEVELS, lesson_slots
        language = (language or "").lower()[:2]
        first_generated = None
        for level in LEVELS:
            for slot in lesson_slots(level):
                status = self.slot_status(language, slot.key)
                if status["status"] == "todo":
                    return {"key": slot.key, "level": level,
                            "title": slot.title}
                if (status["status"] == "generated"
                        and first_generated is None):
                    first_generated = {"key": slot.key, "level": level,
                                       "title": slot.title}
        return first_generated

    def stats(self, language: str) -> dict[str, Any]:
        from engines.language_lab.cefr import LEVELS, lesson_slots
        total = done = generated = 0
        for level in LEVELS:
            for slot in lesson_slots(level):
                total += 1
                status = self.slot_status(language,
                                          slot.key)["status"]
                done += status == "done"
                generated += status != "todo"
        return {"total": total, "done": done, "generated": generated,
                "language": (language or "").lower()[:2]}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
