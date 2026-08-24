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

    def test_persistent_connection_errors_exhaust_and_raise(self, registry):
        err = ConnectionError("still down")
        client = ScriptedClient(err, err)
        with pytest.raises(Exception) as excinfo:
            generate(registry, client, template="gen", variables={"topic": "t"},
                     retry_template="retry", validator=always_valid,
                     max_attempts=2)
        assert "transient error" in excinfo.value.errors[0]
        assert len(client.requests) == 2

    def test_non_retryable_error_propagates_immediately(self, registry):
        client = ScriptedClient(
            ModelNotFoundError("model not loaded"),
            content_response(GOOD_JSON),
        )
        with pytest.raises(ModelNotFoundError):
            generate(registry, client, template="gen", variables={"topic": "t"},
                     retry_template="retry", validator=always_valid)
        assert len(client.requests) == 1
