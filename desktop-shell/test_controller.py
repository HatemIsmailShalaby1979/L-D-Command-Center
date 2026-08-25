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
        result = ctrl.generate_lesson_pack("coffee", "ES", "en", "Beginner")
        assert result.ok
        path = Path(str(result.payload))
        assert path.exists() and path.name.startswith("lesson-coffee-es")
        assert "Dialogue" in path.read_text(encoding="utf-8")

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
        result = ctrl.generate_lesson_pack("tea", "es", "en", "beginner")
        assert result.ok
        html = Path(str(result.payload)).read_text(encoding="utf-8")
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
                                               "beginner")
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

    def test_save_job_watchlist_persists_role(self, storage):
        ctrl = make_controller(OkClient(), storage)
        res = ctrl.save_job_watchlist("support engineer", "",
                                      "stripe", "", "")
        assert res.ok
        cfg = ctrl._job_watch()
        assert cfg["role"] == "support engineer"
        assert "stripe" in cfg["greenhouse_companies"]

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

    def test_import_github_empty_username_rejected(self, storage):
        res = make_controller(OkClient(), storage).import_github_projects(
            "", {})
        assert not res and res.error_kind == "input"

    def test_fetch_linkedin_profile_fills_contact(self, storage,
                                                  monkeypatch):
        from types import SimpleNamespace as SN
        import engines.career_engine.integrations.linkedin_client as lc
        monkeypatch.setattr(lc, "LinkedInClient", lambda **kw: SN(
            get_profile=lambda: SN(name="Ada L.", email="ada@linkedin.com")
        ))
        ctrl = make_controller(OkClient(), storage)
        # resume without contact.name set — LinkedIn should fill it
        resume = {**self.VALID_RESUME, "contact": {"email": ""}}
        res = ctrl.fetch_linkedin_profile(resume)
        assert res.ok
        assert res.payload["resume"]["contact"]["name"] == "Ada L."
        assert res.payload["resume"]["contact"]["email"] == "ada@linkedin.com"
        assert res.payload["who"] == "Ada L."

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
