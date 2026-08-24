# model-layer/test_capabilities.py
#
# WHAT: Contract tests for capability profiles and the one-shot probe.
# WHY:  P7.1 — the shell health bar must show honest readiness
#       (ready/degraded/failed per task family), persist verdicts through
#       Storage, and never block generation. These tests prove the
#       grading rules, size estimation, persistence, and error taxonomy
#       against a scripted client — LM Studio never required.
# BREAKS IF DELETED: Small-model degradation could silently regress into
#       blocking errors or magic UX.

from __future__ import annotations

import json

import pytest

from model_layer.capabilities import (
    TASK_PROFILES,
    estimate_model_size,
    latest_verdict,
    probe_model_capabilities,
    summarize_verdict,
)
from model_layer.client import ApiError, ConnectionError, ModelResponse


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

GOOD_RESPONSES = {
    "clocks": {
        "topic": "clocks",
        "level": "beginner",
        "cards": [{
            "id": "card-1", "title": "Ticking", "content": "Clocks tick.",
            "question": "What do clocks do?",
            "options": ["tick", "fly"], "correct_option": "tick",
            "explanation": "Clocks tick.",
        }],
    },
    "Ada Lovelace": {
        "contact": {"name": "Ada Lovelace", "email": "ada@example.com"},
        "summary": "Mathematician.",
        "skills": ["math"],
    },
    "library closes": {
        "target_text": "La biblioteca cierra a las ocho.",
        "translation_text": "The library closes at eight.",
    },
    "ser": {
        "point": "ser vs estar",
        "explanation": "Ser is permanent; estar is temporary.",
        "example": "Soy alta. Estoy cansada.",
    },
    "Ana and Ben": {
        "segments": [
            {"speaker": "Ana", "content": "I wake at seven."},
            {"speaker": "Ben", "content": "I sleep until nine."},
        ],
    },
    "Bees pollinate": {
        "summary": "Bees pollinate crops; losing them shrinks harvests.",
        "key_takeaways": ["Protect pollinators."],
    },
}


class FakeProbeClient:
    """Scripted LmStudioClient stand-in: list_models + generate."""

    def __init__(self, model_id="lmstudio-community/gemma-4-12B-it-QAT-GGUF",
                 *, overrides=None, models=None):
        self.model_id = model_id
        self.models = [model_id] if models is None else models
        self.overrides = dict(overrides or {})
        self.requests = []

    def list_models(self):
        return list(self.models)

    def generate(self, request):
        self.requests.append(request)
        override = self.overrides.get(request.model)
        if isinstance(override, Exception):
            raise override
        user = request.messages[-1]["content"]
        for key, payload in GOOD_RESPONSES.items():
            if key in user:
                content = self.overrides.get(key, payload)
                if isinstance(content, Exception):
                    raise content
                content = content if isinstance(content, str) else json.dumps(content)
                return ModelResponse(
                    content=content, model=request.model,
                    finish_reason="stop", tool_calls=None, raw={},
                )
        raise AssertionError(f"no scripted response for: {user[:60]!r}")


@pytest.fixture
def store(tmp_path):
    from storage.persistence import Storage
    return Storage(root=tmp_path)


def slug_of(model_id):
    import re
    return re.sub(r"[^a-z0-9]+", "-", model_id.lower()).strip("-") + ".json"


# ---------------------------------------------------------------------------
# Validator guardrails (rejection branches)
# ---------------------------------------------------------------------------

class TestProbeValidators:
    BAD_PAYLOADS = {
        "journey_cards": {"topic": "t", "level": "beginner", "cards": []},
        "resume_generation": {"contact": {"name": "", "email": "nope"},
                              "summary": "", "skills": []},
        "bilingual_translation": {"target_text": "same", "translation_text": "same"},
        "grammar_explanations": {"point": "", "explanation": "", "example": ""},
        "podcast_dialogue": {"segments": [
            {"speaker": "A", "content": "hi"}, {"speaker": "A", "content": "ho"}]},
        "summarization": {"summary": "s", "key_takeaways": []},
    }

    def test_validators_reject_malformed_payloads(self):
        for name, payload in self.BAD_PAYLOADS.items():
            ok, errors = TASK_PROFILES[name].validator(payload)
            assert not ok and errors, name

    def test_validators_reject_non_dicts(self):
        for profile in TASK_PROFILES.values():
            ok, errors = profile.validator(["not an object"])
            assert not ok and errors


# ---------------------------------------------------------------------------
# Size estimation
# ---------------------------------------------------------------------------

class TestEstimateModelSize:
    @pytest.mark.parametrize("model_id,expected", [
        ("deepseek-r1-0528-qwen3-8b", 8.0),
        ("gemma-4-12B-it-QAT-GGUF", 12.0),
        ("qwen3:14b", 14.0),
        ("llama-3.2-3b-instruct", 3.0),
        ("qwen2.5-7b-instruct", 7.0),
        ("qwen-2.5-14b-instruct-1m", 14.0),
        ("granite-4.0-h-tiny", None),
        ("mistral-nemo", None),
        ("q4_k_m-mini", None),
    ])
    def test_parsing(self, model_id, expected):
        assert estimate_model_size(model_id) == expected


# ---------------------------------------------------------------------------
# Probe grading rules
# ---------------------------------------------------------------------------

class TestProbeGrading:
    def test_all_ready_on_recommended_driver(self, store):
        client = FakeProbeClient()  # gemma-4-12B
        verdict = probe_model_capabilities(client, storage=store)
        assert verdict["model_id"].endswith("QAT-GGUF")
        assert verdict["estimated_params_b"] == 12.0
        assert verdict["overall"] == "ready"
        assert {t["status"] for t in verdict["tasks"].values()} == {"ready"}

    def test_one_shot_no_feedback_retries(self, store):
        client = FakeProbeClient()
        probe_model_capabilities(client, storage=store)
        assert len(client.requests) == len(TASK_PROFILES)
        assert all(req.max_tokens == 512 for req in client.requests)
        assert all(req.temperature == 0.0 for req in client.requests)

    def test_bilingual_keeps_mandatory_verify_below_14b(self, store):
        verdict = probe_model_capabilities(FakeProbeClient(), storage=store)
        detail = verdict["tasks"]["bilingual_translation"]["detail"]
        assert "verification pass" in detail
        assert verdict["tasks"]["bilingual_translation"]["status"] == "ready"

    def test_small_model_degrades_everything_above_its_size(self, store):
        verdict = probe_model_capabilities(
            FakeProbeClient("Laocaicai/qwen2.5-3b-instruct"), storage=store)
        assert verdict["overall"] == "degraded"
        tasks = verdict["tasks"]
        assert tasks["summarization"]["status"] == "ready"      # 3B >= 3B
        for name in ("journey_cards", "resume_generation",
                     "bilingual_translation", "podcast_dialogue"):
            assert tasks[name]["status"] == "degraded", name
            assert "comfort threshold" in tasks[name]["detail"]
        assert tasks["grammar_explanations"]["status"] == "degraded"

    def test_unknown_size_degrades_but_never_fails(self, store):
        verdict = probe_model_capabilities(
            FakeProbeClient("lmstudio-community/granite-4.0-h-tiny-GGUF"),
            storage=store)
        assert verdict["estimated_params_b"] is None
        assert verdict["overall"] == "degraded"
        assert all(t["status"] == "degraded" for t in verdict["tasks"].values())
        assert "size unknown" in verdict["tasks"]["summarization"]["detail"]

    def test_garbage_output_marks_task_failed(self, store):
        client = FakeProbeClient(overrides={"clocks": "I prefer prose over JSON."})
        verdict = probe_model_capabilities(client, storage=store)
        assert verdict["tasks"]["journey_cards"]["status"] == "failed"
        assert verdict["tasks"]["journey_cards"]["detail"]
        assert verdict["overall"] == "failed"

    def test_api_error_during_probe_marks_task_failed(self, store):
        boom = ApiError("kaboom", status_code=500)
        client = FakeProbeClient(overrides={"Ada Lovelace": boom})
        verdict = probe_model_capabilities(client, storage=store)
        assert verdict["tasks"]["resume_generation"]["status"] == "failed"
        assert "kaboom" in verdict["tasks"]["resume_generation"]["detail"]
        assert verdict["overall"] == "failed"


# ---------------------------------------------------------------------------
# Error taxonomy + persistence
# ---------------------------------------------------------------------------

class TestProbeErrorsAndPersistence:
    def test_connection_error_propagates_and_stores_nothing(self, store):
        class Down:
            def list_models(self):
                raise ConnectionError("cannot reach LM Studio")

        with pytest.raises(ConnectionError):
            probe_model_capabilities(Down(), storage=store)
        assert store.list_artifacts("capabilities") == []

    def test_empty_model_list_raises_api_error(self, store):
        client = FakeProbeClient(models=[])
        with pytest.raises(ApiError, match="no model loaded"):
            probe_model_capabilities(client, storage=store)

    def test_verdict_saved_and_pointer_set(self, store):
        verdict = probe_model_capabilities(FakeProbeClient(), storage=store)
        name = slug_of(verdict["model_id"])
        assert store.list_artifacts("capabilities") == [name]
        assert store.load_artifact("capabilities", name) == verdict
        assert latest_verdict(store) == verdict

    def test_latest_verdict_none_when_never_probed(self, store):
        assert latest_verdict(store) is None

    def test_latest_verdict_none_when_artifact_vanished(self, store):
        store.set_preference("capability_verdict", "ghost.json")
        assert latest_verdict(store) is None


# ---------------------------------------------------------------------------
# Health-bar summarization
# ---------------------------------------------------------------------------

class TestSummarizeVerdict:
    def _verdict(self, store, model_id="gemma-4-12B-it-QAT-GGUF"):
        return probe_model_capabilities(FakeProbeClient(model_id), storage=store)

    def test_ready_line_has_no_problems(self, store):
        line = summarize_verdict(self._verdict(store))
        assert line.endswith(": ready")
        assert "—" not in line

    def test_small_model_line_names_review_notes(self, store):
        line = summarize_verdict(self._verdict(store, "qwen2.5-3b-instruct"))
        assert "degraded" in line
        assert "translations may need review" in line
        assert "grammar explanations may need review" in line
        assert "summaries may be shallow" not in line  # that profile stayed ready
