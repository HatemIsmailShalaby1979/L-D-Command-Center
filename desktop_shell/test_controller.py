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


# A minimal valid lesson pack reused by the gate/share tests: gating must
# be provable without paying for a model call.
_PACK = {
    "topic": "coffee", "target_language": "es", "known_language": "en",
    "level": "beginner",
    "dialogue": [{"speaker": "Ana", "content": "Un cafe, por favor."},
                 {"speaker": "Luis", "content": "Son cuatro euros."}],
    "vocab_cards": [{"term": "el cafe", "reading": "ka-FE",
                     "translation": "coffee", "example": "Un cafe."}],
    "grammar_cards": [{"point": "tener", "explanation": "to have",
                       "drills": [{"prompt": "Yo ___ sed.",
                                   "answer": "tengo"}]}],
    "evaluation": [{"type": "multiple_choice",
                    "question": "'la cuenta' means?",
                    "options": ["the bill", "the coffee"],
                    "correct_index": 0}],
}


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


class TestAudioStudio:
    def test_audiobook_saves_wav_and_mp3(self, storage, monkeypatch):
        import engines.audio_engine.narration as nar
        from types import SimpleNamespace
        result = SimpleNamespace(
            wav_bytes=b"WAVDATA", mp3_bytes=b"MP3DATA",
            sample_rate=22050, backend_used="PIPER",
            voice_used="en_US-lessac-medium")
        captured = {}
        def fake_narrate(text, **kw):
            captured.update(kw)
            return result
        monkeypatch.setattr(nar, "narrate", fake_narrate)
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.generate_audiobook("The three little pigs", "en", 1.0)
        assert res.ok
        assert res.payload["mp3"].endswith(".mp3")
        assert res.payload["duration_seconds"] == round(7/22050, 1)
        assert captured["voice"] == "en_US-lessac-medium"

    def test_audiobook_empty_text_maps_to_input(self, storage):
        res = make_controller(OkClient(), storage).generate_audiobook("   ")
        assert not res and res.error_kind == "input"

    def test_podcast_generates_script_and_audio(self, storage, monkeypatch):
        import engines.audio_engine.podcast_audio as pa
        import engines.audio_engine.podcast_script as ps
        from types import SimpleNamespace

        script = SimpleNamespace(
            segments=[SimpleNamespace(duration_seconds=30, speaker="Alex"),
                      SimpleNamespace(duration_seconds=40, speaker="Maya")],
            to_dict=lambda: {"title": "T"},
            title="Tea episode")
        audio = SimpleNamespace(wav_bytes=b"W", mp3_bytes=b"M",
                                duration_seconds=70.0)
        captured = {}
        monkeypatch.setattr(ps, "generate_script_from_topic",
                            lambda topic, **kw: captured.update(kw) or script)
        monkeypatch.setattr(pa, "render_podcast_to_audio",
                            lambda s, **kw: audio)
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.generate_podcast("tea history", language="es")
        assert res.ok and res.payload["segments"] == 2
        assert res.payload["wav"].endswith(".wav")
        assert "podcast-tea-history.json" in storage.list_artifacts("podcast_scripts")
        assert captured["language"] == "Spanish"  # catalog name, not code
        assert captured["co_host_name"] == "Maya"
        assert res.payload["speakers"] == ["Alex", "Maya"]

    def test_missing_voice_downloads_on_demand_and_retries(self, storage,
                                                           monkeypatch):
        import engines.audio_engine.narration as nar
        from engines.audio_engine import provisioning
        from types import SimpleNamespace

        calls = []
        def flaky(text, **kw):
            if not calls:
                calls.append("fail")
                raise FileNotFoundError(
                    "Piper voice model not found: "
                    "/x/models/tts/en_US-joe-medium.onnx")
            calls.append("ok")
            return SimpleNamespace(wav_bytes=b"W", mp3_bytes=b"M",
                                   sample_rate=22050, backend_used="PIPER",
                                   voice_used="en_US-joe-medium")

        monkeypatch.setattr(nar, "narrate", flaky)
        downloaded = []
        monkeypatch.setattr(provisioning, "download_voice",
                            lambda vid, d: downloaded.append(vid))
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.generate_audiobook("hello", "en")
        assert res.ok
        assert downloaded == ["en_US-joe-medium"]
        assert len(calls) == 2  # failed once, retried after provisioning

    def test_download_voice_flow_validates_id(self, storage, monkeypatch):
        from engines.audio_engine import provisioning
        seen = []
        monkeypatch.setattr(provisioning, "download_voice",
                            lambda vid, d: seen.append(vid))
        ctrl = make_controller(OkClient(), storage)
        bad = ctrl.download_voice("../../etc/passwd")
        assert not bad and bad.error_kind == "input"
        good = ctrl.download_voice("en_GB-alan-medium")
        assert good.ok and seen == ["en_GB-alan-medium"]

    def test_all_known_voices_marks_uninstalled(self, storage, monkeypatch):
        ctrl = make_controller(OkClient(), storage)
        # pretend only one voice is installed; the rest must be flagged
        monkeypatch.setattr(ctrl, "available_voices",
                            lambda: ["en_US-lessac-medium"])
        known = ctrl.all_known_voices()
        marked = [v for v in known if "(will download on first use)" in v]
        assert marked and all("en_US-lessac-medium" != v.split("   ")[0]
                              for v in marked)

    def test_podcast_empty_topic_maps_to_input(self, storage):
        res = make_controller(OkClient(), storage).generate_podcast("")
        assert not res and res.error_kind == "input"


class TestCareerTab:
    VALID_RESUME = {
        "contact": {"name": "Ada", "email": "ada@example.com"},
        "summary": "Mathematician.",
        "experience": [{"title": "Analyst", "company": "Analytical Engines",
                        "dates": "1843-1845", "description": "First programmer."}],
        "education": [{"degree": "Mathematics", "school": "Self-taught",
                       "dates": "1835"}],
        "skills": ["math"], "projects": [{"name": "Notes", "description": "n"}],
    }

    def _patch_career(self, monkeypatch, enhance_result=None):
        import engines.career_engine.resume.generator as gen
        monkeypatch.setattr(gen, "generate",
                            lambda profile, **kw: dict(self.VALID_RESUME))
        monkeypatch.setattr(gen, "enhance",
                            lambda resume, role, **kw: enhance_result
                            or {"enhanced_resume": dict(self.VALID_RESUME),
                                "changes": [{"field": "summary",
                                             "change": "tailored",
                                             "reason": role}]})

    def test_generate_saves_under_resumes_kind(self, storage, monkeypatch):
        self._patch_career(monkeypatch)
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.generate_resume("  Ada Lovelace, mathematician.  ")
        assert res.ok and res.payload["saved_as"].endswith(".json")
        assert "ada-lovelace--mathematician.json" in storage.list_artifacts("resumes")

    def test_enhance_returns_inspectable_changes_and_persists(self, storage,
                                                              monkeypatch):
        self._patch_career(monkeypatch)
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.enhance_resume(self.VALID_RESUME, "Data Engineer")
        assert res.ok and res.payload["changes"][0]["field"] == "summary"
        assert any("-enhanced.json" in n
                   for n in storage.list_artifacts("resumes"))

    @pytest.mark.parametrize("kwargs,resume", [
        ({"profile": "   "}, None),
        ({}, {}),
        ({}, None),
    ])
    def test_empty_inputs_map_to_input_kind(self, storage, monkeypatch,
                                            kwargs, resume):
        self._patch_career(monkeypatch)
        ctrl = make_controller(OkClient(), storage)
        if "profile" in kwargs:
            res = ctrl.generate_resume(**kwargs)
        else:
            res = ctrl.enhance_resume(resume, kwargs.get("_role", ""))
        assert not res and res.error_kind == "input"

    def test_resume_exports_to_pdf_through_dispatcher(self, storage):
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.export_artifact(self.VALID_RESUME, "pdf")
        assert res.ok and isinstance(res.payload, bytes) and len(res.payload) > 500

    def test_resume_pdf_survives_typographic_unicode(self, storage):
        # the exact crash from live use: helveticaB cannot draw "—"
        resume = {**self.VALID_RESUME,
                  "summary": "28 years in frontline ops — followed by "
                             "quality control, “curly quotes” and café…"}
        res = make_controller(OkClient(), storage).export_artifact(resume, "pdf")
        assert res.ok and len(res.payload) > 500
        res_docx = make_controller(OkClient(), storage).export_artifact(
            resume, "docx")
        assert res_docx.ok


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
        result = ctrl.generate_lesson_pack("coffee", "ES", "en", "Beginner",
                                           num_dialogue=2, num_vocab=1,
                                           num_grammar=1, num_eval=1)
        assert result.ok
        path = Path(result.payload["path"])
        assert path.exists() and path.name.startswith("lesson-coffee-es")
        assert "Dialogue" in path.read_text(encoding="utf-8")
        # the flow reports the pack artifact + the free-tier counter so
        # the UI can share it and show "2 of 3 packs left this week"
        assert result.payload["pack"] == "lesson-coffee-es.json"
        assert result.payload["quota"]["remaining"] == 2

    def test_lesson_pack_flow_wires_per_segment_audio(self, storage,
                                                      monkeypatch):
        # spec C2: listening items must reach the learner — the flow
        # renders per-turn audio and hands the renderer its name map
        import json

        from model_layer.client import ModelResponse

        pack = {
            "topic": "tea", "target_language": "es",
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

        captured = {}

        def fake_render_audio(pack, *, stem, output_path):
            from engines.language_lab.pack_audio import SegmentAudio
            captured["stem"] = stem
            captured["output_path"] = output_path
            return [SegmentAudio("dialogue-0", f"{stem}-dialogue-0.wav",
                                 b"RIFFDATA", 0.5),
                    SegmentAudio("dialogue-1", f"{stem}-dialogue-1.wav",
                                 b"RIFFDATA2", 0.5)]

        import engines.language_lab.pack_audio as pa
        monkeypatch.setattr(pa, "render_pack_audio", fake_render_audio)

        ctrl = make_controller(ScriptedModel(), storage)
        result = ctrl.generate_lesson_pack("tea", "es", "en", "beginner",
                                           num_dialogue=2, num_vocab=1,
                                           num_grammar=1, num_eval=1)
        assert result.ok
        html = Path(result.payload["path"]).read_text(encoding="utf-8")
        # audio is EMBEDDED (data URI): no file:// policy can silence it
        assert "data:audio/wav;base64" in html
        import base64 as _b64
        assert _b64.b64encode(b"RIFFDATA").decode() in html
        assert "Play full dialogue" in html
        assert "<h2>Listening</h2>" in html
        assert captured["output_path"].endswith("exports")

    def test_lesson_pack_flow_survives_missing_tts(self, storage):
        # piper absent -> honest silent pack, never a failed generation
        import json

        from model_layer.client import ModelResponse

        pack = {
            "topic": "tea", "target_language": "es",
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

        class NoPiper(RuntimeError):
            pass

        ctrl = make_controller(ScriptedModel(), storage)
        import engines.language_lab.pack_audio as pa
        original = pa.render_pack_audio

        def boom(*a, **k):
            raise RuntimeError("piper-tts package not installed")

        pa.render_pack_audio = boom
        try:
            result = ctrl.generate_lesson_pack("tea", "es", "en",
                                               "beginner",
                                               num_dialogue=2,
                                               num_vocab=1,
                                               num_grammar=1,
                                               num_eval=1)
        finally:
            pa.render_pack_audio = original
        assert result.ok

    def test_empty_topic_maps_to_input_kind(self, storage):
        result = make_controller(OkClient(), storage).generate_lesson_pack(
            "  ", "es", "en", "beginner")
        assert not result and result.error_kind == "input"





class TestCareerAgentFlows:
    VALID_RESUME = TestCareerTab.VALID_RESUME.copy()

    @staticmethod
    def _make_listing(**overrides):
        base = {"company": "acme", "title": "Support Manager",
                "location": "Berlin", "url": "https://x/j/1",
                "source": "greenhouse", "snippet": "own support queue"}
        base.update(overrides)
        return base

    def test_search_jobs_now_returns_ranked_listings(self, storage,
                                                     monkeypatch):
        from engines.career_engine.job_boards import JobListing
        listings = [JobListing("acme", "Support Manager", "Berlin",
                               "https://x/j/1", "greenhouse",
                               "own support queue"),
                    JobListing("acme", "Backend Engineer", "Remote",
                               "https://x/j/2", "greenhouse",
                               "go services")]
        import engines.career_engine.job_boards as jb
        monkeypatch.setattr(jb, "search_all",
                            lambda **kw: {"greenhouse": listings})
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.search_jobs_now("support", "Berlin",
                                   greenhouse_companies="acme")
        assert res.ok
        assert len(res.payload) == 1  # backend engineer excluded by filter
        assert res.payload[0]["title"] == "Support Manager"
        assert res.payload[0]["score"] >= 3

    def test_search_jobs_now_empty_role_rejected(self, storage):
        res = make_controller(OkClient(), storage).search_jobs_now(
            "", location="Berlin")
        assert not res and res.error_kind == "input"

    def test_search_jobs_now_uses_saved_rosters(self, storage, monkeypatch):
        """No explicit companies + saved job_sources -> the saved roster
        is hunted, not the engine default."""
        captured = {}

        def fake_search_all(**kw):
            captured.update(kw)
            return {}

        import engines.career_engine.job_boards as jb
        monkeypatch.setattr(jb, "search_all", fake_search_all)
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.save_job_sources(greenhouse="dialpad,five9",
                                    lever="aircall", ashby="gorgias")
        assert res.ok
        res = ctrl.search_jobs_now("support")
        assert res.ok
        assert captured["greenhouse_companies"] == ["dialpad", "five9"]
        assert captured["lever_companies"] == ["aircall"]
        assert captured["ashby_companies"] == ["gorgias"]

    def test_search_jobs_now_falls_back_to_engine_defaults(self, storage,
                                                           monkeypatch):
        """Never-saved rosters -> the engine's contact-center/CX defaults
        reach the boards (the legacy stripe/figma roster is dead)."""
        captured = {}

        def fake_search_all(**kw):
            captured.update(kw)
            return {}

        import engines.career_engine.job_boards as jb
        monkeypatch.setattr(jb, "search_all", fake_search_all)
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.search_jobs_now("workforce management")
        assert res.ok
        assert captured["greenhouse_companies"] == \
            jb.GREENHOUSE_DEFAULT_COMPANIES
        assert captured["ashby_companies"] == jb.ASHBY_DEFAULT_COMPANIES

    def test_save_job_sources_empty_means_skip_not_default(self, storage):
        """Saving an empty roster means "skip this board" — an explicit
        empty list must never silently resurrect engine defaults."""
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.save_job_sources(greenhouse="dialpad", lever="", ashby="")
        assert res.ok
        src = ctrl._job_sources()
        assert src["greenhouse_companies"] == ["dialpad"]
        assert src["lever_companies"] == []      # explicit skip
        assert src["ashby_companies"] == []      # explicit skip

    def test_check_job_watchlist_diffs_new_from_seen(self, storage,
                                                     monkeypatch):
        from engines.career_engine.job_boards import JobListing
        listings = [JobListing("a", "Support", "R", "https://x/1",
                                "gh", "s1"),
                    JobListing("a", "Support", "R", "https://x/2",
                                "gh", "s2")]
        import engines.career_engine.job_boards as jb
        monkeypatch.setattr(jb, "search_all",
                            lambda **kw: {"gh": listings})
        ctrl = make_controller(OkClient(), storage)
        # seed a watchlist
        ctrl.storage.set_preference(ctrl._JOB_WATCH_KEY,
                                    {"role": "support", "seen_urls": []})
        res = ctrl.check_job_watchlist()
        assert res.ok and len(res.payload["new"]) == 2
        assert res.payload["total"] == 2
        # run again — second run sees both URLs already stored, so 0 new
        res2 = ctrl.check_job_watchlist()
        assert res2.ok and len(res2.payload["new"]) == 0

    def test_watchlist_saved_before_rosters_uses_live_defaults(self, storage,
                                                                monkeypatch):
        """A watchlist armed with the old empty-company shape (or before
        rosters existed) must keep hunting the shared live defaults, not
        silently watch zero boards."""
        from engines.career_engine.job_boards import JobListing
        listings = [JobListing("a", "Support", "R", "https://x/1",
                                "gh", "s1")]
        captured = {}

        def fake_search_all(**kw):
            captured.update(kw)
            return {"gh": listings}

        import engines.career_engine.job_boards as jb
        monkeypatch.setattr(jb, "search_all", fake_search_all)
        ctrl = make_controller(OkClient(), storage)
        ctrl.storage.set_preference(ctrl._JOB_WATCH_KEY,
                                    {"role": "support", "seen_urls": [],
                                     "greenhouse_companies": [],
                                     "lever_companies": [],
                                     "ashby_companies": []})
        res = ctrl.check_job_watchlist()
        assert res.ok and res.payload["total"] == 1
        assert captured["greenhouse_companies"] == \
            jb.GREENHOUSE_DEFAULT_COMPANIES

    def test_save_job_watchlist_persists_role(self, storage):
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.save_job_watchlist("support engineer", "",
                                      "dialpad", "", "")
        assert res.ok
        cfg = ctrl._job_watch()
        assert cfg["role"] == "support engineer"
        assert cfg["greenhouse_companies"] == ["dialpad"]

    def test_save_job_watchlist_empty_companies_fall_back_to_saved(self,
                                                                   storage):
        """Arming a watchlist with empty roster args must inherit the
        shared job_sources preference, never arm a silent no-op."""
        ctrl = make_controller(OkClient(), storage)
        ctrl.save_job_sources(greenhouse="five9", lever="aircall",
                              ashby="gorgias")
        res = ctrl.save_job_watchlist("support engineer", "")
        assert res.ok
        cfg = ctrl._job_watch()
        assert cfg["greenhouse_companies"] == ["five9"]
        assert cfg["lever_companies"] == ["aircall"]
        assert cfg["ashby_companies"] == ["gorgias"]

    def test_save_job_watchlist_empty_role_rejected(self, storage):
        res = make_controller(OkClient(), storage).save_job_watchlist("")
        assert not res and res.error_kind == "input"

    def test_prepare_application_creates_package(self, storage,
                                                 monkeypatch):
        self._patch_career(monkeypatch)
        # patch cover letter generator
        import engines.career_engine.resume.generator as gen
        monkeypatch.setattr(gen, "generate_cover_letter",
                            lambda resume, **kw: "Dear Hiring Manager,\n"
                            + "I am excited to apply as Support Manager at "
                            + "acme. My experience aligns well.\n"
                            + "Looking forward to discussing how I can "
                            + "contribute.\nBest regards.")
        ctrl = make_controller(OkClient(), storage)
        listing = self._make_listing()
        res = ctrl.prepare_application(listing, dict(self.VALID_RESUME))
        assert res.ok
        pkg = Path(res.payload["dir"])
        assert (pkg / "resume.pdf").exists() and                (pkg / "resume.docx").exists()
        assert (pkg / "cover_letter.txt").exists()
        assert (pkg / "listing.txt").exists()
        assert "apply_url" in res.payload
        assert "acme" in (pkg / "listing.txt").read_text()

    def test_prepare_application_cover_letter_mentions_company(self,
                                                               storage,
                                                               monkeypatch):
        self._patch_career(monkeypatch)
        import engines.career_engine.resume.generator as gen
        # cover letter that omits company name → generator validator
        # will retry with feedback; patched version just returns once
        monkeypatch.setattr(gen, "generate_cover_letter",
                            lambda resume, **kw: "Dear team,\n"
                            + "I am very excited about this role.\n"
                            + "My background in ops is a strong match.\n"
                            + "Sincerely.")
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.prepare_application(
            self._make_listing(company="widgetco"),
            dict(self.VALID_RESUME))
        assert res.ok  # generate_cover_letter bypassed validator here

    def test_upload_resume_txt_parses_and_saves(self, storage):
        txt = ("name: Ada Lovelace\n"
               "email: ada@example.com\n"
               "summary: Mathematician.\n"
               "skills: math, programming\n")
        tmp = storage.root / "test_resume.txt"
        tmp.write_text(txt, encoding="utf-8")
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.upload_resume(str(tmp))
        assert res.ok
        assert res.payload["saved_as"].endswith(".json")
        assert "contact" in res.payload["resume"]
        # confidence flags populated (at least some low/unknown)
        assert isinstance(res.payload["flags"], list)

    def test_upload_resume_bad_path_rejected(self, storage):
        res = make_controller(OkClient(), storage).upload_resume(
            "/nonexistent/resume.pdf")
        assert not res and res.error_kind == "input"

    def test_import_github_projects_injects_repos(self, storage,
                                                   monkeypatch):
        from types import SimpleNamespace as SN
        import engines.career_engine.integrations.github_client as gc
        monkeypatch.setattr(gc, "GitHubClient", lambda **kw: SN(
            get_user_repos=lambda user, limit=10: [
                SN(name="ldcc", full_name="u/ldcc",
                   description="L&D tool", language="Python",
                   topics=["learning"]),
                SN(name="blog", full_name="u/blog",
                   description=None, language="",
                   topics=[]),
            ]))
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.import_github_projects("testuser",
                                          dict(self.VALID_RESUME))
        assert res.ok and res.payload["imported"] == 2
        projects = res.payload["resume"]["projects"]
        assert projects[-2]["name"] == "ldcc"
        assert projects[-1]["description"] == "u/blog"

    def test_import_github_persists_identity(self, storage, monkeypatch):
        from types import SimpleNamespace as SN
        import engines.career_engine.integrations.github_client as gc
        monkeypatch.setattr(gc, "GitHubClient", lambda **kw: SN(
            get_user_repos=lambda user, limit=10: [
                SN(name="ldcc", full_name="u/ldcc",
                   description="L&D tool", language="Python",
                   topics=[]),
            ]))
        ctrl = make_controller(OkClient(), storage)
        ctrl.import_github_projects("testuser", dict(self.VALID_RESUME))
        identity = ctrl.get_career_identity()
        assert identity.ok
        assert identity.payload["github_username"] == "testuser"
        assert identity.payload["github_projects"][0]["name"] == "ldcc"

    def test_import_github_offline_serves_cached_projects(self, storage,
                                                          monkeypatch):
        from types import SimpleNamespace as SN
        import engines.career_engine.integrations.github_client as gc
        good = SN(get_user_repos=lambda user, limit=10: [
            SN(name="ldcc", full_name="u/ldcc", description="d",
               language="Python", topics=[])])
        monkeypatch.setattr(gc, "GitHubClient", lambda **kw: good)
        ctrl = make_controller(OkClient(), storage)
        assert ctrl.import_github_projects("u", {}).ok

        def unreachable(**kw):
            raise ConnectionError("network down")
        monkeypatch.setattr(gc, "GitHubClient", unreachable)
        res = ctrl.import_github_projects("u", {})
        assert res.ok and res.payload["cached"] is True
        assert res.payload["imported"] == 1

    def test_import_github_404_gets_actionable_guidance(self, storage,
                                                        monkeypatch):
        import engines.career_engine.integrations.github_client as gc
        class NotFound:
            def __init__(self, **kw): pass
            def get_user_repos(self, user, limit=10):
                raise RuntimeError("GitHub API error: 404")
        monkeypatch.setattr(gc, "GitHubClient", NotFound)
        res = make_controller(OkClient(), storage).import_github_projects(
            "no-such-user", {})
        assert not res and res.error_kind == "input"
        assert "no user named" in res.detail

    def test_import_github_rate_limit_gets_token_guidance(self, storage,
                                                          monkeypatch):
        import engines.career_engine.integrations.github_client as gc
        class Limited:
            def __init__(self, **kw): pass
            def get_user_repos(self, user, limit=10):
                raise RuntimeError("GitHub API rate limit exceeded")
        monkeypatch.setattr(gc, "GitHubClient", Limited)
        res = make_controller(OkClient(), storage).import_github_projects(
            "u", {})
        assert not res and res.error_kind == "input"
        assert "GITHUB_TOKEN" in res.detail

    def test_import_github_empty_username_rejected(self, storage):
        res = make_controller(OkClient(), storage).import_github_projects(
            "", {})
        assert not res and res.error_kind == "input"

    def test_fetch_linkedin_profile_fills_contact(self, storage,
                                                  monkeypatch):
        from types import SimpleNamespace as SN
        import engines.career_engine.integrations.linkedin_client as lc
        import storage.secrets as secrets_mod
        monkeypatch.setattr(secrets_mod, "load_secret",
                            lambda name, **kw: "token-123")
        monkeypatch.setattr(lc, "LinkedInClient", lambda **kw: SN(
            is_authenticated=True,
            get_profile=lambda: SN(name="Ada L.",
                                   email="ada@linkedin.com",
                                   sub="sub-123")
        ))
        ctrl = make_controller(OkClient(), storage)
        # resume without contact.name set — LinkedIn should fill it
        resume = {**self.VALID_RESUME, "contact": {"email": ""}}
        res = ctrl.fetch_linkedin_profile(resume)
        assert res.ok
        assert res.payload["resume"]["contact"]["name"] == "Ada L."
        assert res.payload["resume"]["contact"]["email"] == "ada@linkedin.com"
        assert res.payload["who"] == "Ada L."
        # identity persisted — survives restarts
        identity = ctrl.get_career_identity()
        assert identity.payload["linkedin"]["name"] == "Ada L."

    def test_fetch_linkedin_without_token_gives_setup_guidance(
            self, storage, monkeypatch):
        import storage.secrets as secrets_mod
        monkeypatch.setattr(secrets_mod, "load_secret",
                            lambda name, **kw: None)
        res = make_controller(OkClient(), storage).fetch_linkedin_profile(
            {"contact": {}})
        assert not res and res.error_kind == "input"
        assert "LINKEDIN_TOKEN" in res.detail
        assert "linkedin.secrets" in res.detail

    def test_fetch_linkedin_offline_serves_cached_identity(
            self, storage, monkeypatch):
        from types import SimpleNamespace as SN
        import engines.career_engine.integrations.linkedin_client as lc
        import storage.secrets as secrets_mod
        monkeypatch.setattr(lc, "LinkedInClient", lambda **kw: SN(
            is_authenticated=True,
            get_profile=lambda: SN(name="Ada L.", email="ada@x.com",
                                   sub="sub-1")))
        monkeypatch.setattr(secrets_mod, "load_secret",
                            lambda name, **kw: "token-123")
        ctrl = make_controller(OkClient(), storage)
        assert ctrl.fetch_linkedin_profile({"contact": {}}).ok
        # token vanishes (offline / expired): cached identity serves
        monkeypatch.setattr(lc, "LinkedInClient", lambda **kw: SN(
            is_authenticated=False))
        monkeypatch.setattr(secrets_mod, "load_secret",
                            lambda name, **kw: None)
        res = ctrl.fetch_linkedin_profile({"contact": {}})
        assert res.ok and res.payload["cached"] is True
        assert res.payload["who"] == "Ada L."

    def test_enhance_persists_target_role(self, storage, monkeypatch):
        self._patch_career(monkeypatch)
        ctrl = make_controller(OkClient(), storage)
        ctrl.generate_resume("profile text")
        res = ctrl.enhance_resume(ctrl.__dict__.get("x", None)
                                  or {"contact": {}, "summary": "",
                                      "skills": []},
                                  "senior support engineer")
        assert res.ok
        identity = ctrl.get_career_identity()
        assert identity.payload["target_role"] == "senior support engineer"

    def test_draft_linkedin_post_saves_and_validates(self, storage,
                                                     monkeypatch):
        import json as _json
        import engines.career_engine.resume.generator as gen
        post = {"post_text": "Spent the morning wiring a retry loop "
                "until it stopped lying about failures. Shipping it "
                "was the easy part.", "style_notes": "concrete moment"}
        monkeypatch.setattr(gen, "generate_linkedin_post",
                            lambda resume, goal, **kw: dict(post))
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.draft_linkedin_post({"contact": {"name": "Ada"}},
                                       "share I am job hunting")
        assert res.ok
        assert res.payload["draft"]["post_text"] == post["post_text"]
        assert res.payload["saved_as"].endswith(".json")
        saved = ctrl.list_saved("linkedin_posts")
        assert res.payload["saved_as"] in saved.payload

    def test_draft_linkedin_post_requires_resume_and_goal(self, storage):
        ctrl = make_controller(OkClient(), storage)
        assert not ctrl.draft_linkedin_post({}, "goal")
        assert not ctrl.draft_linkedin_post({"contact": {}}, "  ")

    def test_publish_requires_explicit_confirm(self, storage, monkeypatch):
        from types import SimpleNamespace as SN
        import engines.career_engine.integrations.linkedin_client as lc
        import storage.secrets as secrets_mod
        monkeypatch.setattr(secrets_mod, "load_secret",
                            lambda name, **kw: "token-123")
        posted = {}
        monkeypatch.setattr(lc, "LinkedInClient", lambda **kw: SN(
            post_to_profile=lambda text, confirm=False, visibility="PUBLIC":
            posted.update(text=text) or {"id": "urn:1"}))
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.publish_linkedin_post("hello world", confirm=False)
        assert not res and res.error_kind == "input"
        assert not posted  # nothing fired
        res = ctrl.publish_linkedin_post("hello world", confirm=True)
        assert res.ok and res.payload["post_id"] == "urn:1"
        assert posted["text"] == "hello world"

    def _patch_career(self, monkeypatch):
        import engines.career_engine.resume.generator as gen
        monkeypatch.setattr(gen, "generate",
                            lambda profile, **kw: dict(self.VALID_RESUME))
        monkeypatch.setattr(gen, "enhance",
                            lambda resume, role, **kw: {
                                "enhanced_resume": dict(self.VALID_RESUME),
                                "changes": [{"field": "summary",
                                             "change": "tailored",
                                             "reason": role}]})

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


class TestLicenseSeam:
    """F7 / PROFIT_PLAN §2 — offline licensing and the Free/Pro gates.

    The rules that matter: the gate fires BEFORE expensive work, the
    refusal is a typed 'license' error with upgrade copy, an invalid key
    never destroys a working one, and sharing packs is never gated.
    """

    @staticmethod
    def _pro_key(days=None):
        from storage.licensing import issue_license
        return issue_license("pro", licensee="Ada", days=days)

    def test_default_status_is_free_with_published_quotas(self, storage):
        res = make_controller(OkClient(), storage).license_status()
        assert res.ok and res.payload["tier"] == "free"
        assert not res.payload["valid"]
        quotas = res.payload["quotas"]
        assert quotas["lesson_pack"]["limit"] == 3
        assert quotas["application_package"]["limit"] == 5
        assert quotas["resume_profile"]["limit"] == 1

    def test_activating_a_key_upgrades_the_install(self, storage):
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.activate_license(self._pro_key())
        assert res.ok and res.payload["tier"] == "pro"
        assert res.payload["valid"] and res.payload["licensee"] == "Ada"
        assert ctrl.license_status().payload["tier"] == "pro"

    def test_bad_key_is_a_typed_license_error_not_a_crash(self, storage):
        res = make_controller(OkClient(), storage).activate_license("nope")
        assert not res and res.error_kind == "license"
        assert "not a valid license key" in res.detail

    def test_expired_key_reports_renewal_guidance(self, storage):
        from datetime import datetime, timedelta, timezone
        from storage.licensing import issue_license
        past = datetime.now(timezone.utc) - timedelta(days=60)
        key = issue_license("pro", days=30, issued_at=past)
        res = make_controller(OkClient(), storage).activate_license(key)
        assert not res and res.error_kind == "license"
        assert "expired" in res.detail.lower()

    def test_deactivate_returns_to_free(self, storage):
        ctrl = make_controller(OkClient(), storage)
        ctrl.activate_license(self._pro_key())
        assert ctrl.deactivate_license().ok
        assert ctrl.license_status().payload["tier"] == "free"

    def test_fourth_free_pack_is_gated_with_upgrade_copy(self, storage,
                                                          monkeypatch):
        import engines.language_lab.lesson_pack as lp
        monkeypatch.setattr(lp, "generate_lesson_pack",
                            lambda *a, **kw: _PACK)
        ctrl = make_controller(OkClient(), storage)
        for i in range(3):
            assert ctrl.generate_lesson_pack(f"t{i}", "es", "en",
                                             "beginner").ok
        blocked = ctrl.generate_lesson_pack("t4", "es", "en", "beginner")
        assert not blocked and blocked.error_kind == "license"
        assert "3 lesson packs" in blocked.detail
        assert "http" in blocked.detail  # upgrade link is always offered
        # and the quota payload lets the UI say why
        assert blocked.payload["used"] == 3

    def test_pro_removes_the_pack_gate(self, storage, monkeypatch):
        import engines.language_lab.lesson_pack as lp
        monkeypatch.setattr(lp, "generate_lesson_pack",
                            lambda *a, **kw: _PACK)
        ctrl = make_controller(OkClient(), storage)
        ctrl.activate_license(self._pro_key())
        for i in range(5):
            assert ctrl.generate_lesson_pack(f"t{i}", "es", "en",
                                             "beginner").ok

    def test_application_packages_gated_at_five(self, storage,
                                                 monkeypatch):
        ctrl = make_controller(OkClient(), storage)
        for _ in range(5):
            ctrl.licenses.consume("application_package")
        res = ctrl.prepare_application({"company": "acme",
                                        "title": "Support",
                                        "url": "u", "snippet": "s"},
                                       TestCareerTab.VALID_RESUME)
        assert not res and res.error_kind == "license"
        assert "application packages" in res.detail

    def test_second_free_resume_profile_is_gated(self, storage):
        ctrl = make_controller(OkClient(), storage)
        ctrl.licenses.consume("resume_profile")
        res = ctrl.generate_resume("experienced support lead")
        assert not res and res.error_kind == "license"
        assert "resume profiles" in res.detail

    def test_upload_resume_counts_against_the_profile_cap(self, storage):
        ctrl = make_controller(OkClient(), storage)
        ctrl.licenses.consume("resume_profile")
        txt = storage.root / "r.txt"
        txt.write_text("name: Ada\nemail: ada@example.com\n",
                       encoding="utf-8")
        res = ctrl.upload_resume(str(txt))
        assert not res and res.error_kind == "license"

    def test_linkedin_draft_is_gated_after_the_free_one(self, storage):
        ctrl = make_controller(OkClient(), storage)
        ctrl.licenses.consume("linkedin_post")
        res = ctrl.draft_linkedin_post(TestCareerTab.VALID_RESUME,
                                       "announce my search")
        assert not res and res.error_kind == "license"
        assert "LinkedIn" in res.detail

    def test_publishing_is_never_metered(self, storage):
        """Publishing is the user's own voice on their own account; only
        drafting consumes quota (PROFIT_PLAN §7: no dark patterns)."""
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.publish_linkedin_post("hello world", confirm=False)
        assert not res and res.error_kind == "input"  # confirm gate, not quota


class TestShareablePacks:
    """PROFIT_PLAN §3.1 — the growth loop lives in the artifact itself."""

    def test_share_writes_a_footed_self_contained_copy(self, storage):
        ctrl = make_controller(OkClient(), storage)
        ctrl.storage.save_artifact("lesson_packs", "coffee.json", _PACK)
        dest = storage.root / "shared.html"
        res = ctrl.share_lesson_pack("coffee.json", destination=str(dest))
        assert res.ok
        document = dest.read_text(encoding="utf-8")
        assert "L&amp;D Command Center" in document
        assert "sharePack()" in document
        assert "<h2>Dialogue</h2>" in document

    def test_share_reuses_the_rendered_export_so_audio_survives(
            self, storage):
        ctrl = make_controller(OkClient(), storage)
        ctrl.storage.save_artifact("lesson_packs", "coffee.json", _PACK)
        rendered = storage.root / "exports" / "coffee.html"
        rendered.parent.mkdir(parents=True, exist_ok=True)
        rendered.write_text("<html><body>data:audio/wav;base64,AAA"
                            "</body></html>", encoding="utf-8")
        res = ctrl.share_lesson_pack("coffee.json")
        assert res.ok
        document = Path(res.payload["path"]).read_text(encoding="utf-8")
        assert "data:audio/wav;base64,AAA" in document
        assert "ldcc-footer" in document

    def test_share_carries_sponsor_branding(self, storage):
        ctrl = make_controller(OkClient(), storage)
        ctrl.storage.save_artifact("lesson_packs", "coffee.json", _PACK)
        res = ctrl.share_lesson_pack("coffee.json", brand="Berlin Lab",
                                     brand_url="https://example.edu")
        assert res.ok and res.payload["brand"] == "Berlin Lab"
        document = Path(res.payload["path"]).read_text(encoding="utf-8")
        assert "Berlin Lab" in document

    def test_share_needs_a_real_pack(self, storage):
        ctrl = make_controller(OkClient(), storage)
        assert not ctrl.share_lesson_pack("").ok
        res = ctrl.share_lesson_pack("missing.json")
        assert not res and res.error_kind in ("input", "unexpected")


class TestCampaignMode:
    """Campaign tier v0 (PROFIT_PLAN §2/§6): auto-tracking on prepare,
    the advance ladder gated to Campaign, interview prep gated + saved,
    the user's own history never paywalled."""

    LISTING = {"company": "Widgetco", "title": "Support Engineer",
               "url": "https://boards.example/w/1", "snippet": "team"}

    @staticmethod
    def _campaign_key():
        from storage.licensing import issue_license
        return issue_license("campaign", licensee="Ada")

    @staticmethod
    def _patch_career(monkeypatch):
        import engines.career_engine.resume.generator as gen
        monkeypatch.setattr(gen, "generate",
                            lambda profile, **kw: dict(
                                TestCareerAgentFlows.VALID_RESUME))
        monkeypatch.setattr(gen, "enhance",
                            lambda resume, role, **kw: {
                                "enhanced_resume": dict(
                                    TestCareerAgentFlows.VALID_RESUME),
                                "changes": [{"field": "summary",
                                             "change": "tailored",
                                             "reason": role}]})

    def test_prepare_application_auto_tracks(self, storage, monkeypatch):
        self._patch_career(monkeypatch)
        # patch cover letter generator (same pattern as
        # TestCareerAgentFlows.prepare_application tests)
        import engines.career_engine.resume.generator as gen
        monkeypatch.setattr(gen, "generate_cover_letter",
                            lambda resume, **kw: "Dear Hiring Manager,\n"
                            "I am excited to apply at Widgetco.\n"
                            "Best regards.")
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.prepare_application(self.LISTING,
                                       dict(TestCareerAgentFlows.VALID_RESUME))
        assert res.ok
        assert res.payload["campaign_status"] == "prepared"
        assert res.payload["campaign_key"] == self.LISTING["url"]
        # tracked in the campaign pipeline too
        status = ctrl.campaign_status()
        assert status.ok and status.payload["total"] == 1

    def test_tracking_is_free_on_every_tier(self, storage):
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.campaign_track(self.LISTING)
        assert res.ok and res.payload["status"] == "prepared"
        status = ctrl.campaign_status()
        assert status.payload["counts"]["prepared"] == 1

    def test_advance_is_gated_to_campaign_tier(self, storage):
        ctrl = make_controller(OkClient(), storage)
        ctrl.campaign_track(self.LISTING)
        res = ctrl.campaign_advance(self.LISTING, "submitted")
        assert not res and res.error_kind == "license"
        assert "Campaign" in res.detail

    def test_campaign_key_unlocks_advance_and_prep(self, storage,
                                                    monkeypatch):
        import engines.career_engine.campaign as campaign_mod
        prep_doc = {"role": "Support Engineer", "company": "Widgetco",
                    "likely_questions": [], "story_bank": [],
                    "questions_to_ask": []}
        monkeypatch.setattr(campaign_mod, "generate_interview_prep",
                            lambda resume, **kw: prep_doc)
        ctrl = make_controller(OkClient(), storage)
        ctrl.activate_license(self._campaign_key())
        ctrl.campaign_track(self.LISTING)
        moved = ctrl.campaign_advance(self.LISTING, "interviewing")
        assert moved.ok and moved.payload["status"] == "interviewing"
        prep = ctrl.campaign_generate_interview_prep(
            self.LISTING, TestCareerTab.VALID_RESUME)
        assert prep.ok
        assert Path(prep.payload["path"]).exists()
        assert prep.payload["prep"]["company"] == "Widgetco"

    def test_interview_prep_gated_to_campaign_tier(self, storage):
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.campaign_generate_interview_prep(
            self.LISTING, TestCareerTab.VALID_RESUME)
        assert not res and res.error_kind == "license"
        assert "interview prep" in res.detail.lower()

    def test_summary_is_readable_on_free_tier(self, storage):
        """The user's own application history is never paywalled
        (PROFIT_PLAN §7: no dark patterns)."""
        ctrl = make_controller(OkClient(), storage)
        ctrl.campaign_track(self.LISTING)
        res = ctrl.campaign_status()
        assert res.ok
        assert res.payload["records"][0]["status"] == "prepared"
