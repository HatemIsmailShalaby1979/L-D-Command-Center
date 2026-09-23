# engines/language-lab/test_et_core.py
#
# WHAT: Contract tests for the E.T. core — personas, scenario bank,
#       and the conversation state machine exercised end-to-end with
#       fake LM client + fake transcriber + fake speaker.
# WHY:  E.T. is the flagship feature; these tests prove the full
#       per-turn pipeline (transcribe -> evaluate -> reply -> speak),
#       beginner-kindness (unclear audio re-asks without consuming a
#       turn), turn limits, persona resolution, and persistence
#       round-trips — all WITHOUT a mic, model weights, or LM Studio.
# BREAKS IF DELETED: A regression in the state machine silently breaks
#       every voice conversation; kindness rules (no-turn-lost) rot.

from __future__ import annotations

import json
from types import SimpleNamespace as SN

import pytest

import engines.language_lab.et_conversation as etc
from engines.audio_engine.stt import TranscriptResult
from engines.language_lab.et_conversation import (
    SessionConfig, Turn, start_session,
)
from engines.language_lab.et_persona import (
    MRS_ET, MR_ET, encouragement, persona_for, status_line,
)
from engines.language_lab.et_scenarios import (
    LENGTHS, SCENARIOS, SPECIAL_SCENARIOS, scenario_bank, scenario_for,
    turn_range,
)
from model_layer.pipeline import DEFAULT_MODEL
from model_layer.client import ModelResponse


class FakeLm:
    """Scripted pipeline client: returns queued JSON payloads."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return ModelResponse(content=outcome, model=DEFAULT_MODEL,
                             finish_reason="stop", tool_calls=None,
                             raw={})


def _reply_json(reply="Hallo!", corrections=None, praise="Super!",
                end=False):
    return json.dumps({"reply": reply,
                       "corrections": corrections or [],
                       "praise": praise,
                       "end_conversation": end})


def _eval_json(grammar=4, vocabulary=3, structure=4, relevance=5,
               corrected="", notes="Watch verb position."):
    return json.dumps({"grammar": grammar, "vocabulary": vocabulary,
                       "structure": structure, "relevance": relevance,
                       "corrected_sentence": corrected,
                       "notes": notes})


class TestPersonas:
    def test_mr_and_mrs_exist_with_roles(self):
        assert MR_ET.voice_role == "male"
        assert MRS_ET.voice_role == "female"
        assert MR_ET.name == "Mr. E.T."
        assert MRS_ET.name == "Mrs. E.T."

    def test_persona_for_unknown_key_never_crashes(self):
        assert persona_for("nonsense").key == "mr"
        assert persona_for("").key == "mr"
        assert persona_for("mrs").key == "mrs"

    def test_system_persona_mentions_name_and_bans_lecturing(self):
        text = MR_ET.system_persona()
        assert "Mr. E.T." in text
        assert "never mock" in text.lower()

    def test_encouragement_is_level_and_language_aware(self):
        line = encouragement("de", "a1")
        assert line  # never empty
        assert encouragement("en", "zz")  # unknown band falls back
        assert encouragement("xx", "b1")  # unknown lang -> english

    def test_status_lines_cover_the_full_cooking_ladder(self):
        for stage in ("listening", "transcribing", "thinking",
                      "speaking", "saved", "repeat", "error"):
            assert status_line(stage, "en")
            assert status_line(stage, "de")
            assert status_line(stage, "xx")  # english fallback


class TestScenarioBank:
    def test_thirty_everyday_scenarios_plus_three_specials(self):
        assert len(SCENARIOS) == 30
        assert len(SPECIAL_SCENARIOS) == 3
        assert len(scenario_bank()) == 33

    def test_scenario_keys_unique_and_stable(self):
        keys = [s.key for s in scenario_bank()]
        assert len(keys) == len(set(keys))

    def test_special_modes_exist(self):
        assert scenario_for("mock-interview").special == "interview"
        assert scenario_for("support-call").special == "support"
        assert scenario_for("free-talk").special == "freetalk"

    def test_lengths_map_to_turn_counts(self):
        assert turn_range("short") == (6, 8)
        assert turn_range("medium") == (10, 14)
        assert turn_range("long") == (18, 24)
        assert turn_range("whatever") == (10, 14)  # safe default

    def test_every_scenario_has_situation_and_goal(self):
        for s in scenario_bank():
            assert len(s.situation) >= 40, s.key
            assert s.goal.strip(), s.key

    def test_unknown_scenario_is_none(self):
        assert scenario_for("nonsense") is None


class TestSessionLifecycle:
    def _start(self, client, **kw):
        transcribe = kw.pop("transcribe_fn", None)
        speak = kw.pop("speak_fn", None)
        return start_session(
            "de", kw.pop("level", "a1"), kw.pop("scenario", "cafe"
                                                if False else
                                                "restaurant-order"),
            kw.pop("persona", "mr"), kw.pop("length", "short"),
            client=client, transcribe_fn=transcribe, speak_fn=speak)

    def test_start_rejects_unknown_scenario_with_copy(self):
        with pytest.raises(ValueError, match="33 to choose"):
            start_session("de", "a1", "nonsense", "mr", "short",
                          client=FakeLm())

    def test_start_rejects_bad_level_and_length(self):
        with pytest.raises(ValueError, match="Level"):
            start_session("de", "c3", "free-talk", "mr", "short",
                          client=FakeLm())
        with pytest.raises(ValueError, match="Length"):
            start_session("de", "a1", "free-talk", "mr", "huge",
                          client=FakeLm())

    def test_opening_line_generated_through_pipeline(self):
        client = FakeLm(_reply_json(reply="Hallo, Erdenmensch!"))
        session = self._start(client)
        assert "Erdenmensch" in session.opening_line()

    def test_opening_line_falls_back_when_model_down(self):
        client = FakeLm(ConnectionError("LM Studio down"))
        session = self._start(client)
        line = session.opening_line()
        assert line  # never empty — conversation always starts

    def test_typed_turn_full_pipeline(self):
        client = FakeLm(_eval_json(), _reply_json(reply="Sehr gut!"))
        spoken = []
        session = self._start(
            client, speak_fn=lambda text, persona, lang:
            spoken.append((text, persona.key)) or b"RIFF")
        event = session.submit_text("Ich mag Kaffee.")
        assert event["kind"] == "turn"
        assert event["reply"] == "Sehr gut!"
        assert event["scores"]["grammar"] == 4
        assert event["audio"] == b"RIFF"
        assert spoken and spoken[0][1] == "mr"
        assert session.turns_used == 1
        assert len(session.turns) == 2  # user + et

    def test_voice_turn_uses_transcriber(self):
        client = FakeLm(_eval_json(), _reply_json())
        captured = {}

        def fake_transcribe(wav, lang):
            captured["wav"] = wav
            captured["lang"] = lang
            return TranscriptResult(text="Ein Kaffee, bitte.",
                                    language=lang, clarity=0.9, wpm=95.0)
        session = self._start(client, transcribe_fn=fake_transcribe)
        event = session.submit_voice(b"WAVBYTES")
        assert event["kind"] == "turn"
        assert captured["wav"] == b"WAVBYTES"
        assert event["clarity"] == 0.9
        assert event["wpm"] == 95.0

    def test_unclear_audio_is_kind_reask_and_turn_not_consumed(self):
        client = FakeLm()  # nothing should be requested
        session = self._start(client, transcribe_fn=lambda w, l:
            TranscriptResult(text="mmm…", language=l, clarity=0.2,
                             wpm=10))
        event = session.submit_voice(b"quiet")
        assert event["kind"] == "repeat"
        assert session.turns_used == 0
        assert not client.requests  # no LM calls wasted

    def test_empty_transcript_reasks(self):
        session = self._start(FakeLm(), transcribe_fn=lambda w, l:
            TranscriptResult(text="", language=l))
        assert session.submit_voice(b"x")["kind"] == "repeat"

    def test_missing_transcriber_is_typed_error_not_crash(self):
        session = self._start(FakeLm())
        event = session.submit_voice(b"x")
        assert event["kind"] == "error"
        assert "type" in event["detail"]

    def test_turn_limit_closes_session(self):
        client = FakeLm(*([_eval_json(),
                           _reply_json()] * 12))
        session = self._start(client, length="short")  # max 8
        for i in range(8):
            assert session.submit_text(f"turn {i}")["kind"] == "turn"
        done = session.submit_text("one more?")
        assert done["kind"] == "closed"
        assert session.turns_used == 8

    def test_evaluation_failure_never_kills_conversation(self):
        # et_evaluate returns garbage 3x (incl. feedback retry) ->
        # scores empty, reply still live on its own outcome
        client = FakeLm("not json at all", "still not json",
                        _reply_json(reply="Weiter!"),
                        _reply_json(reply="Weiter!"))
        session = self._start(client)
        event = session.submit_text("Hallo")
        assert event["kind"] == "turn"
        assert event["scores"] == {}
        assert event["reply"] == "Weiter!"

    def test_speak_failure_still_returns_turn(self):
        client = FakeLm(_eval_json(), _reply_json())

        def broken_speak(text, persona, lang):
            raise RuntimeError("piper missing")
        session = self._start(client, speak_fn=broken_speak)
        event = session.submit_text("hi")
        assert event["kind"] == "turn"
        assert event["audio"] is None  # text reply still delivered

    def test_persistence_roundtrip(self):
        client = FakeLm(_eval_json(), _reply_json())
        session = self._start(client, length="short")
        session.submit_text("Guten Tag")
        data = session.to_dict()
        restored = etc.EtSession.from_dict(
            data, client=FakeLm(), transcribe_fn=lambda w, l:
            TranscriptResult(text="x", language=l, clarity=1.0))
        assert restored.turns_used == 1
        assert restored.persona.key == session.persona.key
        assert restored.turns[0].text == "Guten Tag"
        assert restored.turns[1].role == "et"

    def test_from_dict_unknown_scenario_falls_to_freetalk(self):
        data = {"config": {"language": "en", "level": "a1",
                           "scenario_key": "deleted-scenario",
                           "persona_key": "mrs", "length": "short"}}
        restored = etc.EtSession.from_dict(data, client=FakeLm())
        assert restored.scenario.key == "free-talk"
        assert restored.persona.key == "mrs"

    def test_reply_carries_corrections_and_praise(self):
        client = FakeLm(
            _eval_json(),
            _reply_json(corrections=[{
                "wrong": "Ich mag Kaffee",
                "right": "Ich mag Kaffee.",
                "why": "German sentences end with a period."}],
                praise="Great ordering!"))
        session = self._start(client)
        event = session.submit_text("Ich mag Kaffee")
        assert event["corrections"][0]["right"] == "Ich mag Kaffee."
        assert event["praise"] == "Great ordering!"
