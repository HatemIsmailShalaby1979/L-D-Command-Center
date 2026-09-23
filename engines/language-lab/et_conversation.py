# engines/language-lab/et_conversation.py
#
# WHAT: The E.T. conversation engine — the state machine behind live
#       voice/typed conversations with Mr. or Mrs. E.T.
# WHY:  Owner directive 2026-09-06: interactive LIVE audio conversation
#       where the user records, E.T. evaluates accent/grammar/structure/
#       vocabulary and replies as a chatbot with real feedback. This
#       module owns: session lifecycle, the per-turn pipeline
#       (transcribe -> evaluate -> reply -> speak -> persist), the
#       beginner-kindness rules (unclear audio = kind re-ask, turn not
#       consumed), and honest scoring (clarity + target-match + fluency
#       — never a fake phoneme-by-phoneme "accent score").
#       Everything is injectable (client, transcriber, tts) so the full
#       engine is testable headless with fakes — no mic, no LM, no
#       model weights needed for the suite.
# BREAKS IF DELETED: E.T. is a prompt without a body — no conversation
#       exists, the flagship speaking/listening practice is gone.

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from model_layer.client import ApiError, LmStudioClient
from model_layer.pipeline import DEFAULT_MODEL, generate as run_guardrail_loop
from model_layer.policy import difficulty_for_level
from model_layer.prompts import PromptRegistry
from model_layer.schema import _validate_object, extract_json_from_text

logger = logging.getLogger(__name__)

__all__ = [
    "Turn", "SessionConfig", "EtSession", "start_session",
    "turn_clarity_floor", "TARGET_MATCH_GREAT", "TARGET_MATCH_OK",
]

# Beginner-kindness: below this STT clarity, E.T. asks to repeat and
# the turn is NOT consumed, NOT graded. A whispering mic must never
# cost a learner their turn or their confidence.
turn_clarity_floor = 0.35

# Target-match scoring bands for drills (0-1 similarity).
TARGET_MATCH_GREAT = 0.85
TARGET_MATCH_OK = 0.6


@dataclass
class Turn:
    """One exchange. `source` distinguishes voice from typing; scores
    are None until evaluated. corrections/praise come from the LM."""
    role: str                  # "user" | "et"
    text: str
    source: str = "text"      # "voice" | "text"
    scores: Optional[dict[str, int]] = None
    clarity: Optional[float] = None
    wpm: Optional[float] = None
    corrections: list[dict[str, str]] = field(default_factory=list)
    praise: str = ""
    at: str = field(default_factory=lambda: time.strftime(
        "%Y-%m-%dT%H:%M:%S"))

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "text": self.text,
                "source": self.source, "scores": self.scores,
                "clarity": self.clarity, "wpm": self.wpm,
                "corrections": self.corrections, "praise": self.praise,
                "at": self.at}


@dataclass
class SessionConfig:
    language: str
    level: str
    scenario_key: str
    persona_key: str            # "mr" | "mrs"
    length: str                 # "short" | "medium" | "long"
    user_name: str = ""


class EtSession:
    """Contract: one live conversation. Holds config + turns; every
    submit_audio/submit_text runs the full per-turn pipeline and
    appends exactly one user turn (+ evaluation) and one E.T. turn.
    The caller (controller) persists the transcript AFTER each turn
    and speaks the returned reply audio on a worker thread."""

    def __init__(self, config: SessionConfig, *,
                 scenario: Any,
                 persona: Any,
                 client: Optional[LmStudioClient] = None,
                 model: str = DEFAULT_MODEL,
                 transcribe_fn: Optional[Callable] = None,
                 speak_fn: Optional[Callable] = None):
        self.config = config
        self.scenario = scenario
        self.persona = persona
        self.client = client if client is not None else LmStudioClient()
        self.model = model
        self._transcribe = transcribe_fn
        self._speak = speak_fn
        self.turns: list[Turn] = []
        self.turns_used = 0
        self.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.last_error: str = ""

    # -- transcript helpers ------------------------------------------------

    def _history_text(self, limit: int = 12) -> str:
        lines = []
        for turn in self.turns[-limit:]:
            who = (self.config.user_name or "Learner") \
                if turn.role == "user" else self.persona.name
            lines.append(f"{who}: {turn.text}")
        return "\n".join(lines) or "(conversation just started)"

    @property
    def min_turns(self) -> int:
        from engines.language_lab.et_scenarios import turn_range
        return turn_range(self.config.length)[0]

    @property
    def max_turns(self) -> int:
        from engines.language_lab.et_scenarios import turn_range
        return turn_range(self.config.length)[1]

    # -- opening line -------------------------------------------------------

    def opening_line(self) -> str:
        """E.T. speaks first: persona-flavored, scenario-grounded,
        generated through the reply pipeline with an empty user turn
        so tone rules apply from word one. Falls back to a curated
        safe line if the model is unavailable (conversation starts
        anyway — never a dead end)."""
        stub = "(greet the learner and start the situation naturally)"
        try:
            reply = self._generate_reply(
                user_text=stub,
                turn_number=0,
                end_hint="; this is the OPENING turn — greet warmly "
                "and set the scene in one or two sentences")
            return reply["reply"]
        except Exception as exc:  # noqa: BLE001 — opening must never fail
            logger.warning("Opening line generation failed: %s", exc)
            return self._fallback_opening()

    def _fallback_opening(self) -> str:
        lang = self.config.language
        if lang == "de":
            return ("Hallo! Schön, dass du da bist. Ich bin "
                    f"{self.persona.name}. "
                    f"Szenario: {self.scenario.title_en}. Lass uns "
                    "beginnen — ich bin gespannt auf dich!")
        if lang == "es":
            return (f"¡Hola! Me alegra que estés aquí. Soy "
                    f"{self.persona.name}. Empezamos: "
                    f"{self.scenario.title_en}. ¡Cuéntame!")
        if lang == "ja":
            return (f"こんにちは！会いに来てくれてうれしいです。"
                    f"{self.persona.name}です。"
                    f"シチュエーション：{self.scenario.title_en}。"
                    "始めましょう！")
        return (f"Hello! So glad you made it. I am "
                f"{self.persona.name}. Let's begin: "
                f"{self.scenario.title_en}. I'm listening!")

    # -- core per-turn pipeline ----------------------------------------------

    def submit_voice(self, wav_bytes: bytes) -> dict[str, Any]:
        """Voice turn. Returns the event dict for the caller:

            {"kind": "repeat"}                       — unclear audio,
              kind re-ask, turn NOT consumed
            {"kind": "turn", "reply": ..., "audio": ...}  — full exchange
            {"kind": "error", "detail": ...}          — typed failure
        """
        if self._transcribe is None:
            return {"kind": "error",
                    "detail": "Voice input is not available here — type "
                              "instead, E.T. hears text perfectly."}
        from engines.audio_engine.stt import SttUnavailableError
        try:
            transcript = self._transcribe(wav_bytes,
                                          self.config.language)
        except SttUnavailableError as exc:
            return {"kind": "error", "detail": str(exc)}
        if (not transcript.text.strip()
                or transcript.clarity < turn_clarity_floor):
            logger.info("Unclear audio (clarity %.2f) — kind re-ask",
                        transcript.clarity)
            return {"kind": "repeat",
                    "clarity": transcript.clarity}
        return self._run_turn(transcript.text, source="voice",
                              clarity=transcript.clarity,
                              wpm=transcript.wpm)

    def submit_text(self, text: str) -> dict[str, Any]:
        """Typed turn — same pipeline, voice-grade clarity assumed."""
        text = (text or "").strip()
        if not text:
            return {"kind": "error",
                    "detail": "Say something first — even one word "
                              "counts."}
        return self._run_turn(text, source="text", clarity=1.0,
                              wpm=0.0)

    def _run_turn(self, user_text: str, *, source: str,
                  clarity: float, wpm: float) -> dict[str, Any]:
        if self.turns_used >= self.max_turns:
            return {"kind": "closed",
                    "detail": "This conversation has finished. Start a "
                    "new one — E.T. is ready for the next round."}
        turn_number = self.turns_used + 1
        evaluation = self._evaluate(user_text)
        reply = self._generate_reply(user_text, turn_number)
        self.turns.append(Turn("user", user_text, source=source,
                               scores=evaluation["scores"],
                               clarity=round(clarity, 2), wpm=wpm))
        self.turns.append(Turn("et", reply["reply"],
                               corrections=reply["corrections"],
                               praise=reply["praise"]))
        self.turns_used = turn_number
        audio = None
        if self._speak is not None:
            try:
                audio = self._speak(reply["reply"], self.persona,
                                    self.config.language)
            except Exception as exc:  # noqa: BLE001 — voice optional
                logger.warning("E.T. voice synthesis failed: %s", exc)
        closed = bool(reply.get("end_conversation"))
        return {"kind": "turn", "reply": reply["reply"],
                "corrections": reply["corrections"],
                "praise": reply["praise"], "scores": evaluation["scores"],
                "corrected_sentence": evaluation["corrected_sentence"],
                "notes": evaluation["notes"],
                "clarity": round(clarity, 2), "wpm": wpm,
                "audio": audio, "turn_number": turn_number,
                "max_turns": self.max_turns, "closed": closed}

    # -- LM steps (both through the Guardrail Loop) -------------------------

    def _evaluate(self, user_text: str) -> dict[str, Any]:
        from engines.language_lab.et_persona import BANNED_TELLS
        from engines.language_lab.et_scenarios import turn_range
        from engines.audio_engine.voice_catalog import language_name

        def validator(parsed: Any) -> tuple[bool, list[str]]:
            if not isinstance(parsed, dict):
                return False, ["expected a JSON object"]
            errors: list[str] = []
            scores = {}
            for key in ("grammar", "vocabulary", "structure",
                        "relevance"):
                value = parsed.get(key)
                if not isinstance(value, int) or not (1 <= value <= 5):
                    errors.append(f"{key} must be an integer 1-5")
                else:
                    scores[key] = value
            if not isinstance(parsed.get("corrected_sentence"), str):
                errors.append("corrected_sentence must be a string")
            if not isinstance(parsed.get("notes"), str):
                errors.append("notes must be a string")
            return not errors, errors

        try:
            parsed = run_guardrail_loop(
                PromptRegistry(), self.client,
                template="et_evaluate",
                retry_template="et_evaluate_retry",
                variables={
                    "user_text": user_text,
                    "history": self._history_text(6),
                    "language_name": language_name(
                        self.config.language),
                    "level": self.config.level,
                    "difficulty": difficulty_for_level(
                        self.config.level),
                },
                validator=validator,
                model=self.model,
                max_tokens=3072, temperature=0.2,
            )
            return {"scores": {k: parsed[k] for k in
                               ("grammar", "vocabulary", "structure",
                                "relevance")},
                    "corrected_sentence": parsed["corrected_sentence"],
                    "notes": parsed["notes"]}
        except Exception as exc:  # noqa: BLE001 — evaluation optional
            logger.warning("Evaluation skipped (%s) — conversation "
                           "continues ungraded", exc)
            return {"scores": {}, "corrected_sentence": "",
                    "notes": ""}

    def _generate_reply(self, user_text: str, turn_number: int,
                        end_hint: str = "") -> dict[str, Any]:
        from engines.language_lab.et_persona import BANNED_TELLS
        from engines.language_lab.et_scenarios import turn_range
        from engines.audio_engine.voice_catalog import language_name

        def validator(parsed: Any) -> tuple[bool, list[str]]:
            if not isinstance(parsed, dict):
                return False, ["expected a JSON object"]
            errors: list[str] = []
            if not isinstance(parsed.get("reply"), str) \
                    or not parsed["reply"].strip():
                errors.append("reply must be a non-empty string")
            corrections = parsed.get("corrections")
            if not isinstance(corrections, list) or len(corrections) > 3:
                errors.append("corrections must be a list of 0-3 items")
            else:
                for i, fix in enumerate(corrections):
                    if not (isinstance(fix, dict)
                            and isinstance(fix.get("wrong"), str)
                            and isinstance(fix.get("right"), str)
                            and isinstance(fix.get("why"), str)):
                        errors.append(
                            f"corrections[{i}] needs wrong/right/why")
            if not isinstance(parsed.get("praise"), str):
                errors.append("praise must be a string")
            if not isinstance(parsed.get("end_conversation"), bool):
                errors.append("end_conversation must be true/false")
            return not errors, errors

        turn_min, turn_max = turn_range(self.config.length)
        parsed = run_guardrail_loop(
            PromptRegistry(), self.client,
            template="et_reply",
            retry_template="et_reply_retry",
            variables={
                "persona": self.persona.system_persona(),
                "persona_name": self.persona.name,
                "language_name": language_name(self.config.language),
                "level": self.config.level,
                "difficulty": difficulty_for_level(self.config.level),
                "banned": ", ".join(BANNED_TELLS[:8]),
                "situation": self.scenario.situation,
                "goal": self.scenario.goal,
                "turn_min": turn_min,
                "turn_max": turn_max,
                "turn_number": turn_number,
                "end_hint": end_hint,
                "history": self._history_text(),
                "user_text": user_text,
            },
            validator=validator,
            model=self.model,
            max_tokens=3072, temperature=0.8,
        )
        return {"reply": parsed["reply"],
                "corrections": parsed["corrections"],
                "praise": parsed["praise"],
                "end_conversation": parsed["end_conversation"]}

    # -- persistence ----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": {
                "language": self.config.language,
                "level": self.config.level,
                "scenario_key": self.config.scenario_key,
                "persona_key": self.config.persona_key,
                "length": self.config.length,
                "user_name": self.config.user_name,
            },
            "created_at": self.created_at,
            "turns_used": self.turns_used,
            "turns": [t.to_dict() for t in self.turns],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], **deps) -> "EtSession":
        from engines.language_lab.et_persona import persona_for
        from engines.language_lab.et_scenarios import scenario_for
        cfg = data.get("config") or {}
        scenario = scenario_for(str(cfg.get("scenario_key") or ""))
        if scenario is None:
            scenario = scenario_for("free-talk")
        session = cls(
            SessionConfig(
                language=str(cfg.get("language") or "en"),
                level=str(cfg.get("level") or "a1"),
                scenario_key=scenario.key,
                persona_key=str(cfg.get("persona_key") or "mr"),
                length=str(cfg.get("length") or "medium"),
                user_name=str(cfg.get("user_name") or ""),
            ),
            scenario=scenario,
            persona=persona_for(str(cfg.get("persona_key") or "mr")),
            **deps,
        )
        session.created_at = str(data.get("created_at") or
                                 session.created_at)
        session.turns_used = int(data.get("turns_used") or 0)
        for raw in data.get("turns") or []:
            session.turns.append(Turn(
                role=str(raw.get("role") or "user"),
                text=str(raw.get("text") or ""),
                source=str(raw.get("source") or "text"),
                scores=raw.get("scores"),
                clarity=raw.get("clarity"),
                wpm=raw.get("wpm"),
                corrections=list(raw.get("corrections") or []),
                praise=str(raw.get("praise") or ""),
                at=str(raw.get("at") or ""),
            ))
        return session


def start_session(language: str, level: str, scenario_key: str,
                   persona_key: str, length: str, *,
                   user_name: str = "",
                   client: Optional[LmStudioClient] = None,
                   model: str = DEFAULT_MODEL,
                   transcribe_fn: Optional[Callable] = None,
                   speak_fn: Optional[Callable] = None) -> EtSession:
    """Contract: the single entry point. Resolves scenario + persona,
    validates inputs with actionable ValueErrors, returns a live
    session. The opening line is generated by the CALLER (controller)
    so session construction never blocks."""
    from engines.language_lab.et_persona import persona_for
    from engines.language_lab.et_scenarios import scenario_for, LENGTHS
    scenario = scenario_for(scenario_key)
    if scenario is None:
        raise ValueError(
            f"Unknown conversation scenario {scenario_key!r}. Pick one "
            "from E.T.'s list — there are 33 to choose from.")
    length = (length or "medium").strip().lower()
    if length not in LENGTHS:
        raise ValueError(f"Length must be one of {sorted(LENGTHS)}")
    level = (level or "a1").strip().lower()
    if level not in ("a1", "a2", "b1", "b2", "c1"):
        raise ValueError("Level must be a1, a2, b1, b2 or c1")
    return EtSession(
        SessionConfig(language=(language or "en").lower()[:2],
                      level=level, scenario_key=scenario.key,
                      persona_key=persona_for(persona_key).key,
                      length=length, user_name=user_name.strip()),
        scenario=scenario, persona=persona_for(persona_key),
        client=client, model=model, transcribe_fn=transcribe_fn,
        speak_fn=speak_fn)
