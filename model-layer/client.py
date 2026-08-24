# model-layer/client.py
#
# WHAT: LM Studio HTTP client wrapper — the single entry point for all
#       LLM inference calls through LM Studio's local API.
# WHY:  Every engine (journey-core, export-engine, audio-engine, etc.)
#       sends generation requests through this wrapper. It centralizes
#       connection management, request formatting, and error taxonomy
#       so schema validation and retry logic can operate uniformly.
# BREAKS IF DELETED: No model inference is possible across any engine.
#       The entire generation pipeline halts.

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass
class ToolDefinition:
    """
    Contract: describes a single tool (function) the model may call.
    Follows the OpenAI-compatible format LM Studio accepts.
    """
    type: str = "function"
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    """
    Contract: a single tool-call invocation returned by the model.
    """
    id: str
    name: str
    type: str = "function"
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelRequest:
    """
    Contract: the canonical shape of every request sent to LM Studio.
    Mirrors the OpenAI chat completions request shape so it can be
    serialized directly into the HTTP body.
    """
    model: str
    messages: list[dict[str, Any]]
    max_tokens: int = 4096
    temperature: float = 0.7
    tools: Optional[list[ToolDefinition]] = None
    tool_choice: Optional[str | dict] = None
    stop: Optional[list[str]] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the dict shape expected by the OpenAI-compatible API."""
        result: dict[str, Any] = {
            "model": self.model,
            "messages": self.messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if self.tools:
            result["tools"] = [asdict(t) for t in self.tools]
        if self.tool_choice is not None:
            result["tool_choice"] = self.tool_choice
        if self.stop:
            result["stop"] = self.stop
        result.update(self.extra)
        return result


@dataclass
class ModelResponse:
    """
    Contract: the canonical shape of a successful LM Studio response.
    Extracts the fields downstream engines need; raw is kept for
    debugging and any fields not yet surfaced.
    """
    content: Optional[str]
    model: str
    finish_reason: Optional[str]
    tool_calls: Optional[list[ToolCall]]
    raw: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelResponse":
        """Parse the OpenAI-compatible chat completions response shape."""
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        tool_calls_raw = message.get("tool_calls") or []
        tool_calls = [
            ToolCall(
                id=tc.get("id", ""),
                type=tc.get("type", "function"),
                name=tc.get("function", {}).get("name", ""),
                arguments=tc.get("function", {}).get("arguments", {}),
            )
            for tc in tool_calls_raw
        ]
        return cls(
            content=message.get("content"),
            model=data.get("model", ""),
            finish_reason=choice.get("finish_reason"),
            tool_calls=tool_calls if tool_calls else None,
            raw=data,
        )


class ApiError(Exception):
    """
    Contract: raised when LM Studio returns a non-2xx status or an
    unrecoverable error. Subclasses cover connection errors,
    rate-limit / quota errors, model-not-found, and malformed-input.
    """

    def __init__(self, message: str, status_code: Optional[int] = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class ConnectionError(ApiError):
    """LM Studio is unreachable -- check that the server is running."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class ModelNotFoundError(ApiError):
    """The requested model is not loaded in LM Studio."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class RateLimitError(ApiError):
    """LM Studio reported a rate limit -- safe to retry with backoff."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class LmStudioClient:
    """
    Contract: wraps all HTTP communication with a local LM Studio
    instance. Provides a single synchronous generate() method that
    accepts a ModelRequest and returns a ModelResponse.

    The LM Studio local server exposes an OpenAI-compatible API at
    http://localhost:1234/v1 by default (port configurable via
    Settings > Server in the LM Studio UI).

    Responsibilities:
      - Connect to LM Studio's /v1/chat/completions endpoint
      - Serialize ModelRequest to the OpenAI-compatible JSON body
      - Deserialize the response to ModelResponse
      - Raise typed ApiError subclasses on failure
      - Never swallow exceptions silently; log at INFO for recoverable
        errors, WARNING for unexpected failures

    Non-responsibilities (out of scope):
      - Schema validation of the output (handled by schema.py)
      - Retry logic (handled by the caller)
      - Prompt rendering (handled by prompts.py)
    """

    def __init__(self, base_url: str = "http://localhost:1234/v1", timeout: int = 120) -> None:
        """
        Args:
            base_url: LM Studio server base URL including /v1.
                      Default matches LM Studio's out-of-the-box setting.
            timeout: per-request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None

    def _get_session(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
        return self._client

    def generate(self, request: ModelRequest) -> ModelResponse:
        """
        Contract: send request to LM Studio and return structured response.
        Performs exactly one HTTP attempt; callers should wrap in retry
        logic for transient failures.

        Endpoint: POST {base_url}/chat/completions

        Raises:
            ConnectionError: LM Studio is unreachable.
            ModelNotFoundError: the requested model is not loaded.
            RateLimitError: server is rate-limiting (retryable).
            ApiError: other non-2xx responses.
            ApiError: malformed response body from the server.
        """
        session = self._get_session()
        payload = request.to_dict()
        logger.info("Sending chat completion request to %s/chat/completions", self.base_url)
        try:
            response = session.post("/chat/completions", json=payload)
        except httpx.ConnectError as exc:
            raise ConnectionError(f"Cannot reach LM Studio at {self.base_url}: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise ApiError(f"Request to LM Studio timed out after {self.timeout}s: {exc}", retryable=True) from exc

        if response.status_code == 404:
            raise ModelNotFoundError(
                f"Model '{request.model}' not found or not loaded in LM Studio. "
                "Load the model first in the LM Studio UI."
            )
        if response.status_code == 429:
            raise RateLimitError(f"LM Studio rate-limited the request (HTTP 429)")

        if response.status_code != 200:
            raise ApiError(
                f"LM Studio returned HTTP {response.status_code}: {response.text}",
                status_code=response.status_code,
                retryable=response.status_code >= 500,
            )

        try:
            return ModelResponse.from_dict(response.json())
        except (ValueError, KeyError) as exc:
            raise ApiError(f"Malformed response from LM Studio: {exc}") from exc

    def is_available(self) -> bool:
        """
        Contract: returns True if LM Studio is reachable and responding
        on the configured base_url. Used for health checks before
        attempting generation.
        """
        try:
            session = self._get_session()
            resp = session.get("/models")
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
            return False
