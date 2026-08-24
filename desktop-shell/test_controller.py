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
