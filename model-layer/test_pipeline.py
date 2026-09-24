# model-layer/test_pipeline.py
#
# WHAT: Contract tests for the Generation Pipeline, exercised through its
#       public interface with a scripted fake LmStudioClient.
# WHY:  P1.2 of docs/PRODUCTION_PLAN.md — the pipeline is THE seam every
#       engine generates through, so one suite here proves retry counts,
#       feedback formatting, transient-error handling, and the typed error
#       taxonomy for all artifact types at once. The fake client implements
#       the REAL LmStudioClient interface (generate(ModelRequest) ->
#       ModelResponse), so a divergence like the old broken _call_model
#       copies now fails loudly here.
# BREAKS IF DELETED: The Guardrail Loop's behavior is unprotected; engines
#       could migrate onto a pipeline whose contract silently rots.

from __future__ import annotations

import pytest

from model_layer.client import (
    ApiError,
    ConnectionError,
    ModelNotFoundError,
    ModelResponse,
    ToolCall,
)
from model_layer.pipeline import DEFAULT_MODEL, generate
from model_layer.schema import SchemaValidationError


# ---------------------------------------------------------------------------
# Fake adapter — matches the real LmStudioClient interface exactly
# ---------------------------------------------------------------------------

class ScriptedClient:
    """Returns queued ModelResponses / raises queued exceptions in order."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def content_response(text: str) -> ModelResponse:
    return ModelResponse(
        content=text, model=DEFAULT_MODEL, finish_reason="stop",
        tool_calls=None, raw={},
    )


def tool_call_response() -> ModelResponse:
    tc = ToolCall(id="t1", name="some_tool", arguments={})
    return ModelResponse(content=None, model=DEFAULT_MODEL,
                         finish_reason="tool_calls", tool_calls=[tc], raw={})


GOOD_JSON = '{"topic": "t", "level": "beginner", "cards": []}'

REGISTRY_TEMPLATES = {
    "gen": ("SYS", "USER {topic}"),
    "retry": ("RETRY_SYS", "FIX {topic} errors:\n{errors}"),
}


class FakeRegistry:
    """Minimal PromptRegistry double honoring the render() contract."""

    def __init__(self, templates=None):
        self.templates = templates or dict(REGISTRY_TEMPLATES)
        self.rendered: list[tuple[str, dict]] = []

    def render(self, name, variables):
        self.rendered.append((name, dict(variables)))
        system, user = self.templates[name]
        return system.format(**variables), user.format(**variables), None


def always_valid(parsed):
    return True, []


def never_valid(parsed):
    return False, ["bad shape"]


@pytest.fixture
def registry():
    return FakeRegistry()


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------

class TestSuccess:
    def test_first_attempt_success_returns_parsed_data(self, registry):
        client = ScriptedClient(content_response(GOOD_JSON))
        result = generate(registry, client, template="gen",
                          variables={"topic": "t"}, validator=always_valid)
        assert result == {"topic": "t", "level": "beginner", "cards": []}
        assert len(client.requests) == 1

    def test_extracts_json_wrapped_in_prose(self, registry):
        client = ScriptedClient(content_response(f'Sure! Here you go:\n{GOOD_JSON}\nHope that helps.'))
        result = generate(registry, client, template="gen",
                          variables={"topic": "t"}, validator=always_valid)
        assert result["topic"] == "t"

    def test_request_carries_model_messages_and_params(self, registry):
        client = ScriptedClient(content_response(GOOD_JSON))
        generate(registry, client, template="gen", variables={"topic": "t"},
                 validator=always_valid, model="mymodel",
                 max_tokens=512, temperature=0.1)
        req = client.requests[0]
        assert req.model == "mymodel"
        assert req.max_tokens == 512
        assert req.temperature == 0.1
        assert [m["role"] for m in req.messages] == ["system", "user"]


# ---------------------------------------------------------------------------
# Validation failure + feedback retry
# ---------------------------------------------------------------------------

class TestRetryOnValidationFailure:
    def test_retries_with_feedback_and_succeeds(self, registry):
        client = ScriptedClient(
            content_response('{"broken": true}'),
            content_response(GOOD_JSON),
        )
        calls = {"n": 0}

        def valid_on_second(parsed):
            calls["n"] += 1
            return (True, []) if calls["n"] > 1 else (False, ["missing cards"])

        result = generate(registry, client, template="gen", variables={"topic": "t"},
                          retry_template="retry", validator=valid_on_second)
        assert result["topic"] == "t"
        # second request used the retry prompt carrying formatted errors
        assert client.requests[1].messages[1]["content"].startswith("FIX t")
        assert "- missing cards" in registry.rendered[-1][1]["errors"]
        # ...plus the pipeline's own urgency restatement (reasoning
        # models must not deliberate a second full budget away)
        assert "Begin the corrected JSON immediately" in \
            client.requests[1].messages[1]["content"]
        # ...and retry diversity: the re-roll temperature climbs per
        # attempt so loop replays break instead of repeating
        assert client.requests[0].temperature == 0.7
        assert client.requests[1].temperature == 0.85

    def test_raises_after_max_attempts_with_last_errors(self, registry):
        client = ScriptedClient(*[content_response(GOOD_JSON)] * 3)
        with pytest.raises(Exception) as excinfo:
            generate(registry, client, template="gen", variables={"topic": "t"},
                     retry_template="retry", validator=never_valid,
                     max_attempts=3)
        assert excinfo.value.attempt == 3
        assert excinfo.value.errors == ["bad shape"]
        assert len(client.requests) == 3

    def test_no_retry_template_raises_after_single_attempt(self, registry):
        client = ScriptedClient(content_response(GOOD_JSON))
        with pytest.raises(Exception) as excinfo:
            generate(registry, client, template="gen",
                     variables={"topic": "t"}, validator=never_valid)
        assert excinfo.value.attempt == 1
        assert len(client.requests) == 1

    def test_unparseable_json_consumes_an_attempt_then_recovers(self, registry):
        client = ScriptedClient(
            content_response("no json here at all"),
            content_response(GOOD_JSON),
        )
        result = generate(registry, client, template="gen", variables={"topic": "t"},
                          retry_template="retry", validator=always_valid)
        assert result["topic"] == "t"
        assert "could not extract JSON" in registry.rendered[1][1]["errors"]


# ---------------------------------------------------------------------------
# Client error taxonomy
# ---------------------------------------------------------------------------

class TestClientErrors:
    def test_tool_calls_instead_of_content_raise_immediately(self, registry):
        client = ScriptedClient(tool_call_response(), content_response(GOOD_JSON))
        with pytest.raises(ApiError, match="tool calls"):
            generate(registry, client, template="gen", variables={"topic": "t"},
                     retry_template="retry", validator=always_valid)
        assert len(client.requests) == 1  # not retried

    def test_retryable_connection_error_is_consumed_then_recovers(self, registry):
        client = ScriptedClient(
            ConnectionError("LM Studio down"),
            content_response(GOOD_JSON),
        )
        result = generate(registry, client, template="gen", variables={"topic": "t"},
                          retry_template="retry", validator=always_valid)
        assert result["topic"] == "t"
        assert len(client.requests) == 2

    def test_persistent_connection_errors_raise_the_connection_error(self, registry):
        # A dead server is NOT "invalid content": after retries exhaust,
        # the last transient ApiError surfaces verbatim so the UI can say
        # "start LM Studio" (E6 honesty).
        err = ConnectionError("still down")
        client = ScriptedClient(err, err)
        with pytest.raises(ConnectionError) as excinfo:
            generate(registry, client, template="gen", variables={"topic": "t"},
                     retry_template="retry", validator=always_valid,
                     max_attempts=2)
        assert "still down" in str(excinfo.value)
        assert len(client.requests) == 2

    def test_transient_then_validation_failure_still_schema_error(self, registry):
        # Mixed causes: the FINAL failure decides the exception type.
        client = ScriptedClient(
            ConnectionError("blip"),
            content_response("not json at all"),
            content_response("still not json"),
        )
        with pytest.raises(SchemaValidationError):
            generate(registry, client, template="gen", variables={"topic": "t"},
                     retry_template="retry", validator=always_valid,
                     max_attempts=3)

    def test_non_retryable_error_propagates_immediately(self, registry):
        client = ScriptedClient(
            ModelNotFoundError("model not loaded"),
            content_response(GOOD_JSON),
        )
        with pytest.raises(ModelNotFoundError):
            generate(registry, client, template="gen", variables={"topic": "t"},
                     retry_template="retry", validator=always_valid)
        assert len(client.requests) == 1


# ---------------------------------------------------------------------------
# 2026-09-05 hardening: truncation repair, JSON mode, discipline addendum
# ---------------------------------------------------------------------------

def truncated_response(text: str) -> ModelResponse:
    return ModelResponse(content=text, model=DEFAULT_MODEL,
                         finish_reason="length", tool_calls=None, raw={})


class TestTruncationRepair:
    def test_token_limit_output_is_repaired_not_failed(self, registry):
        # 12B/14B models producing a big artifact hit max_tokens mid-JSON;
        # the pipeline must salvage complete members instead of failing.
        truncated = '{"topic": "t", "level": "beginner", "cards": [{"id'
        client = ScriptedClient(truncated_response(truncated))
        result = generate(registry, client, template="gen",
                          variables={"topic": "t"}, validator=always_valid)
        assert result == {"topic": "t", "level": "beginner"}

    def test_truncation_without_salvage_feeds_actionable_feedback(self, registry):
        client = ScriptedClient(
            truncated_response("only prose before the cut, no JSON object"),
            content_response(GOOD_JSON),
        )
        result = generate(registry, client, template="gen",
                          variables={"topic": "t"}, retry_template="retry",
                          validator=always_valid)
        assert result["topic"] == "t"
        assert "token limit" in registry.rendered[1][1]["errors"]

    def test_stop_reason_unparseable_keeps_normal_feedback(self, registry):
        client = ScriptedClient(
            content_response("total garbage"),
            content_response(GOOD_JSON),
        )
        result = generate(registry, client, template="gen",
                          variables={"topic": "t"}, retry_template="retry",
                          validator=always_valid)
        assert result["topic"] == "t"
        assert "token limit" not in registry.rendered[1][1]["errors"]


class TestJsonMode:
    def test_request_carries_response_format(self, registry):
        client = ScriptedClient(content_response(GOOD_JSON))
        generate(registry, client, template="gen", variables={"topic": "t"},
                 validator=always_valid)
        assert client.requests[0].extra.get("response_format") == {
            "type": "json_object"}

    def test_runtime_rejection_falls_back_without_consuming_attempt(self, registry):
        # A runtime that does not support response_format answers 400;
        # the pipeline disables JSON mode and retries the SAME attempt.
        client = ScriptedClient(
            ApiError("response_format not supported by this model",
                     status_code=400),
            content_response(GOOD_JSON),
        )
        result = generate(registry, client, template="gen",
                          variables={"topic": "t"}, validator=always_valid)
        assert result["topic"] == "t"
        assert len(client.requests) == 2
        assert "response_format" not in client.requests[1].extra

    def test_unrelated_400_still_raises(self, registry):
        client = ScriptedClient(
            ApiError("temperature out of range", status_code=400),
            content_response(GOOD_JSON),
        )
        with pytest.raises(ApiError):
            generate(registry, client, template="gen",
                     variables={"topic": "t"}, validator=always_valid)


class TestDisciplineAddendum:
    def test_policy_addendum_appended_to_system_prompt(self, registry):
        client = ScriptedClient(content_response(GOOD_JSON))
        generate(registry, client, template="gen", variables={"topic": "t"},
                 validator=always_valid)
        system = client.requests[0].messages[0]["content"]
        assert system.startswith("SYS")
        assert "OUTPUT RULES" in system
        # The addendum is deliberately SHORT: measured live, long
        # rule lists trigger deliberation spirals in reasoning
        # models (4000+ thinking tokens, zero content). Formatting
        # edge cases (fences, literals, think blocks) are handled
        # by the extractor, not by more rules.
        assert "COMPLETELY" in system

    def test_small_model_gets_bigger_attempt_budget(self, registry):
        client = ScriptedClient(*[content_response("garbage")] * 4
                                + [content_response(GOOD_JSON)])
        result = generate(registry, client, template="gen",
                          variables={"topic": "t"}, retry_template="retry",
                          validator=always_valid, model="llama-3.2-3b-instruct")
        assert result["topic"] == "t"
        assert len(client.requests) == 5

    def test_large_model_keeps_default_budget(self, registry):
        client = ScriptedClient(*[content_response("garbage")] * 3)
        with pytest.raises(SchemaValidationError) as excinfo:
            generate(registry, client, template="gen",
                     variables={"topic": "t"}, retry_template="retry",
                     validator=always_valid, model="qwen3-14b")
        assert excinfo.value.attempt == 3


# ---------------------------------------------------------------------------
# 2026-09-24 hardening: thinking suppression + budget escalation
# ---------------------------------------------------------------------------

class TestThinkingSuppression:
    def test_request_carries_reasoning_effort_none(self, registry):
        client = ScriptedClient(content_response(GOOD_JSON))
        generate(registry, client, template="gen", variables={"topic": "t"},
                 validator=always_valid)
        assert client.requests[0].extra.get("reasoning_effort") == "none"

    def test_runtime_rejection_falls_back_without_consuming_attempt(
            self, registry):
        # A runtime that does not support reasoning_effort answers 400;
        # the pipeline drops the field and retries the SAME attempt.
        client = ScriptedClient(
            ApiError("reasoning_effort is not supported by this model",
                     status_code=400),
            content_response(GOOD_JSON),
        )
        result = generate(registry, client, template="gen",
                          variables={"topic": "t"}, validator=always_valid)
        assert result["topic"] == "t"
        assert len(client.requests) == 2
        assert "reasoning_effort" not in client.requests[1].extra

    def test_unrelated_400_still_raises_even_with_thinking_on(self, registry):
        client = ScriptedClient(
            ApiError("temperature out of range", status_code=400),
            content_response(GOOD_JSON),
        )
        with pytest.raises(ApiError):
            generate(registry, client, template="gen",
                     variables={"topic": "t"}, validator=always_valid)


class TestBudgetEscalation:
    def test_truncated_attempt_doubles_max_tokens_for_retry(self, registry):
        # The budget's failure, not the model's verbosity: a truncated
        # attempt escalates max_tokens for its retry.
        client = ScriptedClient(
            truncated_response("only prose before the cut, no JSON object"),
            content_response(GOOD_JSON),
        )
        result = generate(registry, client, template="gen",
                          variables={"topic": "t"}, retry_template="retry",
                          validator=always_valid)
        assert result["topic"] == "t"
        assert client.requests[0].max_tokens == 8192
        assert client.requests[1].max_tokens == 16384

    def test_repeated_truncation_climbs_to_ceiling(self, registry):
        client = ScriptedClient(
            truncated_response("no json"),
            truncated_response("no json"),
            content_response(GOOD_JSON),
        )
        result = generate(registry, client, template="gen",
                          variables={"topic": "t"}, retry_template="retry",
                          validator=always_valid, max_attempts=3)
        assert result["topic"] == "t"
        assert [r.max_tokens for r in client.requests] == [8192, 16384,
                                                           32768]

    def test_escalation_never_exceeds_ceiling(self, registry):
        from model_layer.pipeline import MAX_TOKENS_CEILING
        client = ScriptedClient(*[truncated_response("no json")] * 3)
        with pytest.raises(SchemaValidationError):
            generate(registry, client, template="gen",
                     variables={"topic": "t"}, retry_template="retry",
                     validator=always_valid, max_attempts=3,
                     max_tokens=MAX_TOKENS_CEILING)
        assert all(r.max_tokens == MAX_TOKENS_CEILING
                   for r in client.requests)

    def test_ceiling_truncation_feedback_asks_for_concision(self, registry):
        from model_layer.pipeline import MAX_TOKENS_CEILING
        client = ScriptedClient(
            truncated_response("no json"),
            content_response(GOOD_JSON),
        )
        generate(registry, client, template="gen",
                 variables={"topic": "t"}, retry_template="retry",
                 validator=always_valid, max_tokens=MAX_TOKENS_CEILING)
        assert "token limit" in registry.rendered[1][1]["errors"]
        assert "concise" in registry.rendered[1][1]["errors"]
