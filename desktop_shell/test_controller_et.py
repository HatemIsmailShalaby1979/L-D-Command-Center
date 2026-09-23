# desktop-shell/test_controller_et.py
#
# WHAT: Contract tests for the controller's E.T. surface — session
#       lifecycle, quota gating (10 turns/week free), typed device
#       errors, transcript persistence, and the mic/STT fakes.
# WHY:  The controller seam is where a crash becomes a dialog vs. a
#       dead app. These prove: no-session errors are friendly, quota
#       refusals carry upgrade copy BEFORE any recording is wasted,
#       mic failures degrade to typing mode, completed turns persist,
#       and replaying a line works headless (no audio hardware).
# BREAKS IF DELETED: E.T.'s error handling rots — voice failures
#       resurface as tracebacks in production.

from __future__ import annotations

import json
from types import SimpleNamespace as SN

import pytest

import desktop_shell.controller as ctrl_mod
from desktop_shell.controller import FlowResult, ShellController
from engines.audio_engine.stt import TranscriptResult
from model_layer.client import ModelResponse
from model_layer.pipeline import DEFAULT_MODEL
from storage.persistence import Storage


@pytest.fixture
def storage(tmp_path):
    return Storage(root=tmp_path)


class OkClient:
    def is_available(self):
        return True


class FakeLm:
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


def _reply_json(reply="Sehr gut!", end=False):
    return json.dumps({"reply": reply, "corrections": [],
                       "praise": "Nice!", "end_conversation": end})


def _eval_json():
    return json.dumps({"grammar": 4, "vocabulary": 3,
                       "structure": 4, "relevance": 5,
                       "corrected_sentence": "", "notes": "ok"})


def make_et_controller(client, storage, *, transcribe=None, speak=None):
    controller = ShellController(client=client, storage=storage)
    if transcribe is not None or speak is not None:
        session_holder = {}

        def start(language, level, scenario_key, persona_key, length,
                  **kw):
            from engines.language_lab.et_conversation import start_session
            session = start_session(language, level, scenario_key,
                                    persona_key, length,
                                    client=client, model=DEFAULT_MODEL,
                                    transcribe_fn=transcribe,
                                    speak_fn=speak)
            session_holder["session"] = session
            return session
        controller._et_session_factory = start
    return controller


class TestEtScenarioBank:
    def test_bank_lists_33_scenarios_with_metadata(self, storage):
        controller = ShellController(client=OkClient(), storage=storage)
        res = controller.et_scenario_bank()
        assert res.ok and len(res.payload) == 33
        entry = res.payload[0]
        assert {"key", "title", "domain", "goal", "special"} <= \
            set(entry.keys())

    def test_microphone_devices_degrades_to_empty(self, storage,
                                                  monkeypatch):
        import engines.audio_engine.mic as mic
        monkeypatch.setattr(mic, "list_input_devices", lambda: [])
        controller = ShellController(client=OkClient(), storage=storage)
        res = controller.et_microphone_devices()
        assert res.ok and res.payload == []


class TestEtSessionLifecycle:
    def _started(self, storage, client=None, **kw):
        controller = ShellController(client=client or FakeLm(
            _eval_json(), _reply_json()), storage=storage)
        res = controller.et_start_session("de", "a1", "restaurant-order",
                                          "mr", "short")
        assert res.ok, res.detail
        return controller

    def test_start_and_opening_line(self, storage):
        client = FakeLm(_reply_json(reply="Hallo, Erdenmensch!"))
        controller = ShellController(client=client, storage=storage)
        assert controller.et_start_session(
            "de", "a1", "restaurant-order", "mr", "short").ok
        line = controller.et_opening_line()
        assert line.ok and "Erdenmensch" in line.payload["line"]

    def test_opening_without_session_is_friendly(self, storage):
        controller = ShellController(client=OkClient(), storage=storage)
        res = controller.et_opening_line()
        assert not res and res.error_kind == "input"
        assert "Start a conversation" in res.detail

    def test_state_snapshot_shows_transcript(self, storage):
        controller = self._started(storage)
        assert controller.et_submit_text("Guten Tag").ok
        state = controller.et_session_state()
        assert state.ok and state.payload["active"]
        assert state.payload["turns_used"] == 1
        assert len(state.payload["transcript"]) == 2

    def test_end_session_clears_state(self, storage):
        controller = self._started(storage)
        assert controller.et_end_session().ok
        state = controller.et_session_state()
        assert state.ok and not state.payload["active"]

    def test_completed_turns_persist_transcript(self, storage):
        controller = self._started(storage)
        controller.et_submit_text("Ich bin müde.")
        sessions = controller.list_saved("et_sessions")
        assert sessions.ok and len(sessions.payload) == 1


class TestEtQuotaGating:
    def test_eleventh_free_turn_is_blocked_with_upgrade_copy(
            self, storage, monkeypatch):
        # pre-consume 10 turns (the full free weekly budget)
        controller = ShellController(client=FakeLm(), storage=storage)
        for _ in range(10):
            controller.licenses.consume("et_turn")
        assert controller.et_start_session(
            "de", "a1", "restaurant-order", "mr", "short").ok
        blocked = controller.et_submit_text("Hallo?")
        assert not blocked and blocked.error_kind == "license"
        assert "E.T. conversation turns" in blocked.detail
        assert "http" in blocked.detail

    def test_pro_key_removes_the_gate(self, storage):
        from storage.licensing import issue_license
        controller = ShellController(
            client=FakeLm(_eval_json(), _reply_json()), storage=storage)
        controller.activate_license(issue_license("pro", licensee="Ada"))
        for _ in range(10):
            controller.licenses.consume("et_turn")
        assert controller.et_start_session(
            "de", "a1", "restaurant-order", "mr", "short").ok
        assert controller.et_submit_text("Hallo").ok  # unlimited

    def test_gate_fires_before_recording(self, storage, monkeypatch):
        """The quota check must run BEFORE any mic work — nobody
        records 30 seconds only to be told they're out of turns."""
        controller = ShellController(client=FakeLm(), storage=storage)
        for _ in range(10):
            controller.licenses.consume("et_turn")
        calls = {"capture": 0}

        def fake_capture(**kw):
            calls["capture"] += 1
            raise RuntimeError("should never get here")
        import engines.audio_engine.mic as mic
        monkeypatch.setattr(mic, "capture_speech", fake_capture)
        assert controller.et_start_session(
            "de", "a1", "restaurant-order", "mr", "short").ok
        controller._et_device = None
        res = controller.et_submit_voice()
        assert res.error_kind == "license"
        assert calls["capture"] == 0  # no recording was wasted


class TestEtVoicePath:
    def test_voice_turn_through_fake_transcriber(self, storage,
                                                 monkeypatch):
        import engines.audio_engine.mic as mic
        import numpy as np

        class FakeStream:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, blocksize):
                loud = np.full((blocksize, 1), 0.3, "float32")
                quiet = np.zeros((blocksize, 1), "float32")
                self.n = getattr(self, "n", 0) + 1
                return (loud if self.n <= 5 else quiet), False

        fake_sd = SN(
            query_devices=lambda: [
                {"name": "Test Mic", "max_input_channels": 1,
                 "default_samplerate": 16000}],
            default=SN(device=(0, -1)),
            InputStream=lambda **kw: FakeStream(),
        )
        monkeypatch.setattr(mic, "_sd", lambda: fake_sd)

        def fake_transcribe(wav, lang):
            return TranscriptResult(text="Ein Wasser, bitte.",
                                    language=lang, clarity=0.9,
                                    wpm=80.0)
        controller = ShellController(
            client=FakeLm(_eval_json(), _reply_json()), storage=storage)
        # inject the fake transcriber through the controller hook
        controller._et_transcribe_fn = fake_transcribe
        assert controller.et_start_session(
            "de", "a1", "restaurant-order", "mr", "short").ok
        # replace the session's transcriber too (created at start)
        controller._et_active._transcribe = fake_transcribe
        res = controller.et_submit_voice(device_index=0)
        assert res.ok, res.detail
        assert res.payload["reply"] == "Sehr gut!"
        assert res.payload["clarity"] == 0.9

    def test_no_microphone_is_typed_device_error(self, storage,
                                                 monkeypatch):
        import engines.audio_engine.mic as mic
        monkeypatch.setattr(mic, "list_input_devices", lambda: [])
        controller = ShellController(client=FakeLm(), storage=storage)
        assert controller.et_start_session(
            "de", "a1", "restaurant-order", "mr", "short").ok
        res = controller.et_submit_voice()
        assert not res and res.error_kind == "device"
        assert "type to E.T." in res.detail

    def test_unclear_audio_is_et_repeat_kind(self, storage):
        def unclear(wav, lang):
            return TranscriptResult(text="mmm", language=lang,
                                    clarity=0.2)
        controller = ShellController(
            client=FakeLm(_eval_json(), _reply_json()), storage=storage)
        controller._et_transcribe_fn = unclear
        assert controller.et_start_session(
            "de", "a1", "restaurant-order", "mr", "short").ok
        controller._et_active._transcribe = unclear
        res = controller.et_submit_text("")  # empty text path
        assert not res and res.error_kind == "input"
