# engines/test_e2e_live.py
#
# WHAT: End-to-end smoke tests against a REAL running LM Studio server
#       and a REAL loaded model (exit criterion E2).
# WHY:  Everything else in this repo is proven against fakes; this
#       module proves the whole Guardrail Loop survives contact with an
#       actual model — discovery, capability probe, journey, resume,
#       bilingual+verification, and the flagship LessonPack pipeline
#       (generate -> validate -> grade -> audit -> render). Deselected by
#       default; run explicitly:
#
#           python -m pytest -m live
#
# Requires: LM Studio server on localhost:1234 with a chat model loaded
# (JIT loading counts). Skips — never fails — when the server is down,
# so CI stays green without services.
# BREAKS IF DELETED: Model-side regressions (truncation, format drift,
# retry exhaustion) would only surface in production use.

from __future__ import annotations

import pytest

from model_layer.client import LmStudioClient

pytestmark = [pytest.mark.live]

LONG_TIMEOUT = 900  # seconds per HTTP request; CPU inference is slow


@pytest.fixture(scope="session")
def live_client():
    client = LmStudioClient(timeout=LONG_TIMEOUT)
    try:
        models = client.list_models()
    except Exception as exc:  # noqa: BLE001 — unreachable == skip, never fail
        pytest.skip(f"LM Studio not reachable ({exc})")
    if not models:
        pytest.skip("LM Studio reachable but no model available")
    return client


@pytest.fixture(scope="session")
def model_id(live_client):
    return live_client.list_models()[0]


# ---------------------------------------------------------------------------
# Discovery + capability probe (P7.1 against reality)
# ---------------------------------------------------------------------------

class TestDiscoveryAndProbe:
    def test_chat_model_discoverable_and_size_parses(self, live_client,
                                                     model_id):
        from model_layer.capabilities import estimate_model_size
        assert model_id
        size = estimate_model_size(model_id)
        assert size is not None, f"no size hint in real model id {model_id!r}"

    def test_capability_probe_grades_real_model(self, live_client,
                                                tmp_path_factory):
        from model_layer.capabilities import (
            TASK_PROFILES,
            probe_model_capabilities,
        )
        from storage.persistence import Storage

        storage = Storage(root=tmp_path_factory.mktemp("e2e-cap"))
        verdict = probe_model_capabilities(live_client, storage=storage)

        assert set(verdict["tasks"]) == set(TASK_PROFILES)
        assert verdict["overall"] in {"ready", "degraded", "failed"}
        # every graded task carries a status and human-readable detail
        for record in verdict["tasks"].values():
            assert record["status"] in {"ready", "degraded", "failed"}
            assert isinstance(record["detail"], str)


# ---------------------------------------------------------------------------
# Generation pipelines end-to-end
# ---------------------------------------------------------------------------

class TestJourneyE2E:
    def test_generate_render_export_roundtrip(self, live_client, model_id):
        from engines.journey_core.generator import generate_journey
        from engines.journey_core.renderer import render_journey_html
        from model_layer.schema import validate_journey

        journey = generate_journey(
            topic="the basics of photosynthesis",
            level="beginner",
            num_cards=2,
            client=live_client,
            model=model_id,
        )
        ok, errors = validate_journey(journey)
        assert ok, errors
        assert len(journey["cards"]) == 2
        html = render_journey_html(journey)
        assert "photosynthesis" in html.lower()


class TestResumeE2E:
    def test_resume_generate_validates(self, live_client, model_id):
        from engines.career_engine.resume.generator import generate
        from engines.career_engine.resume.schema import validate_resume

        resume = generate(
            profile="Ada Lovelace, mathematician. Wrote the first "
                    "algorithm for Babbage's Analytical Engine. Skills: "
                    "mathematics, mechanical computation.",
            client=live_client,
            model=model_id,
        )
        ok, errors = validate_resume(resume)
        assert ok, errors
        assert resume["contact"]["name"].strip()
        assert len(resume["experience"]) >= 1


class TestBilingualE2E:
    def test_generate_with_verification_audit_trail(self, live_client,
                                                    model_id):
        from engines.language_lab.bilingual import (
            generate_bilingual_pair_verified,
        )

        verified = generate_bilingual_pair_verified(
            "greetings at a cafe", "es", "en",
            num_segments=3,
            client=live_client,
            model=model_id,
        )
        assert len(verified.pair.segments) == 3
        # every segment pair has both sides of the lesson
        for seg in verified.pair.segments:
            assert seg.target_text.strip() and seg.translation_text.strip()
        # P3.2 discipline: a verdict exists and is inspectable either way
        assert verified.verdicts
        assert isinstance(verified.verdicts[-1].passed, bool)


class TestLessonPackFlagshipE2E:
    def test_full_pipeline_generate_grade_audit_render(
        self, live_client, model_id, tmp_path
    ):
        from engines.language_lab.graders import (
            grade_deterministic,
            verify_lesson_pack,
        )
        from engines.language_lab.lesson_pack import (
            generate_lesson_pack,
            validate_lesson_pack,
        )
        from engines.language_lab.renderer import render_lesson_pack_html
        from storage.persistence import Storage

        pack = generate_lesson_pack(
            "ordering coffee", "es", "en", "beginner",
            num_dialogue=4, num_vocab=4, num_grammar=2, num_eval=3,
            client=live_client,
            model=model_id,
        )

        ok, errors = validate_lesson_pack(pack)
        assert ok, errors

        # deterministic grading agrees with the pack's own answer keys
        for item in pack["evaluation"]:
            if item["type"] == "multiple_choice":
                result = grade_deterministic(item, item["correct_index"])
                assert result.correct
            elif item["type"] == "fill_in_blank":
                result = grade_deterministic(item, item["answer"])
                assert result.correct, result.detail

        # fidelity audit of the pack's own claims produces an artifact
        client_for_audit = live_client
        audit = verify_lesson_pack(pack, client=client_for_audit)
        assert len(audit["claims"]) == len(pack["vocab_cards"]) + \
            len(pack["grammar_cards"])
        assert isinstance(audit["passed"], bool)

        # renderer consumes the validated pack without modification
        html = render_lesson_pack_html(pack)
        for section in ("<h2>Dialogue</h2>", "<h2>Vocabulary</h2>",
                        "<h2>Evaluation</h2>"):
            assert section in html

        # persistence roundtrip through the real storage layout — a
        # LessonPack is not a Journey: it gets its own kind, and its
        # fidelity audit lands under verdicts
        storage = Storage(root=tmp_path)
        pack_name = "e2e-pack.json"
        storage.save_artifact("lesson_packs", pack_name, pack)
        reloaded = storage.load_artifact("lesson_packs", pack_name)
        ok_again, _ = validate_lesson_pack(reloaded)
        assert ok_again
        audit_name = "e2e-pack-audit.json"
        storage.save_artifact("verdicts", audit_name, audit)
        assert storage.load_artifact("verdicts", audit_name)["passed"] \
            == audit["passed"]
