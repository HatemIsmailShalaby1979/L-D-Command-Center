# engines/language-lab/srs.py
#
# WHAT: Spaced-repetition-lite — the classic SM-2 scheduler over plain
#       card states, plus an SrsStore persisting progress through the
#       Storage engine's preference blob so reviews survive restarts and
#       stay offline/exportable (P7.6).
# WHY:  Flashcards without scheduling are a toy. SM-2 is small enough to
#       be fully inspectable and deterministic — correctness here is
#       arithmetic, not model judgement. `today` is injectable everywhere
#       so every rule is testable without clock games.
# BREAKS IF DELETED: Review history resets on every restart; due-card
#       selection disappears.

from __future__ import annotations

import dataclasses
import logging
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
from typing import Any, Optional

from storage.persistence import Storage, default_storage

logger = logging.getLogger(__name__)

__all__ = ["CardState", "new_card", "review", "quality_from_correct",
           "SrsStore", "SRS_PREFERENCE_KEY"]

SRS_PREFERENCE_KEY = "srs_progress"

_MIN_EASE = 1.3
_DEFAULT_EASE = 2.5


# ---------------------------------------------------------------------------
# Pure SM-2 core
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CardState:
    """One card's schedule. interval_days=0 + due=None means 'never
    studied — due immediately'."""
    ease: float = _DEFAULT_EASE
    interval_days: int = 0
    repetitions: int = 0
    lapses: int = 0
    due: Optional[str] = None  # ISO date string; None => due now

    def is_due(self, today: date) -> bool:
        return self.due is None or date.fromisoformat(self.due) <= today

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CardState":
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})


def new_card() -> CardState:
    return CardState()


def quality_from_correct(correct: bool) -> int:
    """Map a binary grade onto SM-2's 0–5 scale (wrong = 2: a miss that
    felt familiar still counts as a lapse)."""
    return 5 if correct else 2


def _clamp_ease(ease: float) -> float:
    return max(_MIN_EASE, ease)


def review(state: CardState, quality: int, *,
           today: Optional[date] = None) -> CardState:
    """
    Contract: one SM-2 review of a card.

    q >= 3 (recalled): repetitions++, interval follows the classic
      ladder 1 -> 6 -> round(prev*ease); ease adjusts by quality
      (floored at 1.3).
    q < 3 (lapsed): repetitions and interval reset to 1 day, lapses++,
      ease unchanged.

    Raises:
        ValueError: quality outside 0..5.
    """
    if not isinstance(quality, int) or isinstance(quality, bool) \
            or not 0 <= quality <= 5:
        raise ValueError(f"quality must be an integer 0..5, got {quality!r}")
    today = today or date.today()

    if quality < 3:
        return replace(
            state,
            ease=state.ease,
            interval_days=1,
            repetitions=0,
            lapses=state.lapses + 1,
            due=(today + timedelta(days=1)).isoformat(),
        )

    if state.repetitions == 0:
        interval = 1
    elif state.repetitions == 1:
        interval = 6
    else:
        interval = max(1, round(state.interval_days * state.ease))

    delta = 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    return replace(
        state,
        ease=_clamp_ease(round(state.ease + delta, 4)),
        interval_days=interval,
        repetitions=state.repetitions + 1,
        due=(today + timedelta(days=interval)).isoformat(),
    )


# ---------------------------------------------------------------------------
# Persistence through Storage
# ---------------------------------------------------------------------------

class SrsStore:
    """
    Contract: card schedules for every deck, persisted as one JSON blob
    under Storage preferences (key srs_progress). All methods are
    synchronous and offline; `today` is injectable for deterministic
    tests.
    """

    def __init__(self, storage: Optional[Storage] = None) -> None:
        self._storage = storage if storage is not None else default_storage()

    def _load_all(self) -> dict[str, dict[str, Any]]:
        return self._storage.get_preference(SRS_PREFERENCE_KEY, {}) or {}

    def all_states(self) -> dict[str, CardState]:
        return {cid: CardState.from_dict(raw)
                for cid, raw in self._load_all().items()}

    def get(self, card_id: str) -> Optional[CardState]:
        raw = self._load_all().get(card_id)
        return CardState.from_dict(raw) if raw else None

    def save(self, card_id: str, state: CardState) -> None:
        blob = self._load_all()
        blob[card_id] = state.to_dict()
        self._storage.set_preference(SRS_PREFERENCE_KEY, blob)

    def review(self, card_id: str, quality: int, *,
               today: Optional[date] = None) -> CardState:
        """Review one card (creating it if unseen) and persist the result."""
        state = self.get(card_id) or new_card()
        updated = review(state, quality, today=today)
        self.save(card_id, updated)
        logger.info("SRS review %s q=%d -> due %s",
                    card_id, quality, updated.due)
        return updated

    def due_cards(self, *, today: Optional[date] = None) -> list[str]:
        today = today or date.today()
        return sorted(cid for cid, state in self.all_states().items()
                      if state.is_due(today))

    def forget(self, card_id: str) -> None:
        """Drop a card's schedule entirely."""
        blob = self._load_all()
        if card_id in blob:
            del blob[card_id]
            self._storage.set_preference(SRS_PREFERENCE_KEY, blob)
