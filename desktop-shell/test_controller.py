# desktop-shell/test_controller.py
#
# WHAT: Headless contract tests for the shell controller — the seam
#       between the Tkinter UI and the engines.
# WHY:  P5.2/P5.3. Tkinter can't run without a display, so the controller
#       carries all behavior and these tests prove it: typed-error
#       mapping (no_model/bad_output/input/unexpected), journey flow,
#       render+persist, export routing, and the library API.
# BREAKS IF DELETED: The UI's only brain is unverified; error taxonomy
#       regressions would surface as raw tracebacks in dialogs.

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from desktop_shell.controller import FlowResult, ShellController
from engines.playground_bridge.connectors_hub import Job, Result
from model_layer.client import ConnectionError as LmConnectionError
from model_layer.schema import SchemaValidationError
from storage.persistence import Storage


@pytest.fixture
def storage(tmp_path):
    return Storage(root=tmp_path)


def make_controller(client, storage):
    return ShellController(client=client, storage=storage)


class OkClient:
    def is_available(self):
        return True


class DownClient:
    def is_available(self):
        return False


class TestHealth:
    def test_ready(self, storage):
        result = make_controller(OkClient(), storage).check_model_health()
        assert result.ok and result.payload == "ready"

    def test_down_maps_to_no_model(self, storage):
        result = make_controller(DownClient(), storage).check_model_health()
        assert not result and result.error_kind == "no_model"


class TestGenerateJourneyFlow:
    @pytest.fixture(autouse=True)
    def _patch_gen(self, monkeypatch):
        import engines.journey_core.generator as gen
        self.gen = gen
        yield

    def test_success_returns_journey(self, storage):
        self.gen.generate_journey = lambda **kw: {"topic": kw["topic"], "cards": []}
        result = make_controller(OkClient(), storage).generate_journey("Python basics", "beginner")
        assert result.ok and result.payload["topic"] == "Python basics"

    def test_input_error_maps_to_input_kind(self, storage):
        def boom(**kw): raise ValueError("Invalid level 'expert'")
        self.gen.generate_journey = boom
        result = make_controller(OkClient(), storage).generate_journey("t", "expert")
        assert result.error_kind == "input"

    def test_connection_error_maps_to_no_model_with_actionable_detail(self, storage):
        def boom(**kw): raise LmConnectionError("refused")
        self.gen.generate_journey = boom
        result = make_controller(OkClient(), storage).generate_journey("t", "beginner")
        assert result.error_kind == "no_model"
        assert "localhost:1234" in result.detail  # E6: actionable message

    def test_validation_error_maps_to_bad_output(self, storage):
        def boom(**kw): raise SchemaValidationError(["bad"], 3)
        self.gen.generate_journey = boom
        result = make_controller(OkClient(), storage).generate_journey("t", "beginner")
        assert result.error_kind == "bad_output"

    def test_surprise_exception_maps_to_unexpected(self, storage):
        def boom(**kw): raise KeyError("surprise")
        self.gen.generate_journey = boom
        result = make_controller(OkClient(), storage).generate_journey("t", "beginner")
        assert result.error_kind == "unexpected"


class TestRenderAndSave:
    def test_saves_html_artifact(self, storage, monkeypatch):
        import engines.journey_core.renderer as rend
        monkeypatch.setattr(rend, "render_journey_html",
                            lambda j: f"<html>{j['topic']}</html>")
        c = make_controller(OkClient(), storage)
        result = c.render_and_save_journey({"topic": "My Topic!", "cards": [1]})
        assert result.ok
        saved = Path(str(result.payload))
        assert saved.exists() and b"My Topic" in saved.read_bytes()


class TestCapabilities:
    def test_probe_success_returns_verdict(self, storage, monkeypatch):
        monkeypatch.setattr(
            "model_layer.capabilities.probe_model_capabilities",
            lambda client, storage=None: {"overall": "ready", "tasks": {}},
        )
        result = make_controller(OkClient(), storage).run_capability_probe()
        assert result.ok and result.payload["overall"] == "ready"

    def test_probe_connection_error_maps_to_no_model(self, storage, monkeypatch):
        def boom(client, storage=None):
            raise LmConnectionError("refused")
        monkeypatch.setattr("model_layer.capabilities.probe_model_capabilities", boom)
        result = make_controller(OkClient(), storage).run_capability_probe()
        assert not result and result.error_kind == "no_model"

    def test_summary_none_when_never_probed(self, storage):
        result = make_controller(OkClient(), storage).capability_summary()
        assert result.ok and result.payload is None

    def test_summary_reads_stored_verdict_offline(self, storage):
        from model_layer.capabilities import summarize_verdict
        doc = {"model_id": "gemma-4-12B-it-QAT-GGUF",
               "estimated_params_b": 12.0, "overall": "ready", "tasks": {}}
        storage.save_artifact("capabilities", "gemma.json", doc)
        storage.set_preference("capability_verdict", "gemma.json")
        result = make_controller(OkClient(), storage).capability_summary()
        assert result.ok
        assert result.payload == summarize_verdict(doc)


class TestPlayground:
    class FakeConnector:
        name = "fake-gen"

        def __init__(self, *, fail=False):
            self.fail = fail
            self.ops = []

        def capabilities(self):
            from engines.playground_bridge.connectors_hub import Capabilities, Capability
            return Capabilities("fake-gen", "none", (
                Capability("image", "test image gen", "free forever"),))

        def send(self, artifact, op):
            self.ops.append(op)
            job_id = f"job-{len(self.ops)}"
            if self.fail:
                self._result = (job_id, False, None, "quota blown")
                return Job(job_id, self.name, "failed")
            media = op.get("bytes", b"FAKEPNG")
            self._result = (job_id, True, media, None)
            return Job(job_id, self.name, "done")

        def poll(self, job):
            from engines.playground_bridge.connectors_hub import Result
            jid, ok, media, error = self._result
            return Result(jid, ok, media_bytes=media, error=error)

    def make_playground_controller(self, storage, connector=None,
                                   inbox_path=None):
        return ShellController(client=OkClient(), storage=storage,
                               connectors=[connector] if connector else [],
                               inbox_path=inbox_path)

    def test_import_files_copies_and_collides_safely(self, storage, tmp_path):
        src1 = tmp_path / "art.png"
        src1.write_bytes(b"one")
        sub = tmp_path / "sub"
        sub.mkdir()
        src2 = sub / "art.png"
        src2.write_bytes(b"two")
        ctrl = self.make_playground_controller(storage)
        result = ctrl.import_files([str(src1), str(src2)])
        assert result.ok and all(r["ok"] for r in result.payload)
        listed = ctrl.list_media("library").payload
        assert sorted(listed) == ["art-1.png", "art.png"]
        assert ctrl.load_media("library", "art-1.png").payload == b"two"

    def test_scan_import_inbox_reports_and_moves(self, storage, tmp_path):
        inbox = tmp_path / "drop"
        inbox.mkdir()
        (inbox / "beat.wav").write_bytes(b"WAV")
        ctrl = self.make_playground_controller(storage, inbox_path=str(inbox))
        result = ctrl.scan_import_inbox()
        assert result.ok and result.payload[0]["ok"] is True
        assert not (inbox / "beat.wav").exists()
        assert "beat.wav" in ctrl.list_media("inbox").payload

    def test_connector_capabilities_surface_quota_notes(self, storage):
        connector = self.FakeConnector()
        ctrl = self.make_playground_controller(storage, connector)
        caps = ctrl.connector_capabilities().payload
        entry = next(c for c in caps if c["connector"] == "fake-gen")
        assert entry["auth"] == "none"
        assert entry["items"][0]["quota_note"] == "free forever"

    def test_run_connector_job_success_stores_media_generated(self, storage):
        connector = self.FakeConnector()
        ctrl = self.make_playground_controller(storage, connector)
        result = ctrl.run_connector_job("fake-gen",
                                        {"prompt": "Blue Bird Sky"})
        assert result.ok
        assert result.payload["artifact_name"] == "blue-bird-sky.png"
        assert "blue-bird-sky.png" in ctrl.list_media("generated").payload
        assert connector.ops[0]["prompt"] == "Blue Bird Sky"

    def test_run_connector_job_failure_maps_to_connector_kind(self, storage):
        connector = self.FakeConnector(fail=True)
        ctrl = self.make_playground_controller(storage, connector)
        result = ctrl.run_connector_job("fake-gen", {"prompt": "p"})
        assert not result.ok and result.error_kind == "connector"
        assert "quota blown" in result.detail

    def test_unknown_connector_maps_to_input_kind(self, storage):
        ctrl = self.make_playground_controller(storage)
        result = ctrl.run_connector_job("nope", {"prompt": "p"})
        assert not result.ok and result.error_kind == "input"

    def test_default_roster_registers_keyless_first(self, storage):
        ctrl = self.make_playground_controller(storage)
        names = ctrl.connector_names().payload
        assert "pollinations" in names          # zero-account first
        for expected in ("hf-flux-schnell", "hf-ace-step-music", "figma"):
            assert expected in names


class TestLanguageLabTab:
    def test_lesson_pack_flow_renders_and_saves_html(self, storage):
        # A scripted MODEL CLIENT drives the REAL lesson-pack generation,
        # validation, and rendering end-to-end.
        import json

        from model_layer.client import ModelResponse

        pack = {
            "topic": "coffee", "target_language": "es",
            "known_language": "en", "level": "beginner",
            "dialogue": [{"speaker": "A", "content": "x"},
                         {"speaker": "B", "content": "y"}],
            "vocab_cards": [{"term": "t", "reading": "r",
                             "translation": "tr", "example": "e"}],
            "grammar_cards": [{"point": "p", "explanation": "e",
                               "drills": [{"prompt": "?", "answer": "a"},
                                          {"prompt": "??", "answer": "b"}]}],
            "evaluation": [{"type": "multiple_choice", "question": "q",
                            "options": ["a", "b"], "correct_index": 0}],
        }

        class ScriptedModel:
            def generate(self, request):
                return ModelResponse(
                    content=json.dumps(pack), model=request.model,
                    finish_reason="stop", tool_calls=None, raw={})

        ctrl = make_controller(ScriptedModel(), storage)
        result = ctrl.generate_lesson_pack("coffee", "ES", "en", "Beginner")
        assert result.ok
        path = Path(str(result.payload))
        assert path.exists() and path.name.startswith("lesson-coffee-es")
        assert "Dialogue" in path.read_text(encoding="utf-8")

    def test_empty_topic_maps_to_input_kind(self, storage):
        result = make_controller(OkClient(), storage).generate_lesson_pack(
            "  ", "es", "en", "beginner")
        assert not result and result.error_kind == "input"


class TestExportAndLibrary:
    JOURNEY = {"topic": "T", "level": "beginner",
               "cards": [{"id": "c", "title": "t", "content": "c",
                          "question": "q", "options": ["a"],
                          "correct_option": "a", "explanation": "e"}]}

    def test_export_routes_through_dispatcher(self, storage):
        result = make_controller(OkClient(), storage).export_artifact(self.JOURNEY, "text")
        assert result.ok and "T (BEGINNER)" in result.payload

    def test_library_roundtrip(self, storage):
        c = make_controller(OkClient(), storage)
        c.save_raw_export("hello", "note.txt")
        listed = c.list_saved("exports")
        assert listed.ok and "note.txt" in listed.payload
        loaded = c.load_saved("exports", "note.txt")
        assert loaded.ok and loaded.payload == "hello"
