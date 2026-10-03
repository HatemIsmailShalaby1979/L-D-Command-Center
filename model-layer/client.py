# model-layer/client.py
#
# WHAT: Local inference client layer — the single entry point for all
#       LLM calls through a local OpenAI-compatible server (LM Studio at
#       :1234, Ollama at :11434, any other compatible runtime), plus the
#       endpoint-discovery layer that finds those servers on localhost.
# WHY:  Every engine (journey-core, export-engine, audio-engine, etc.)
#       sends generation requests through this module. It centralizes
#       connection management, request formatting, endpoint discovery,
#       and error taxonomy so schema validation and retry logic can
#       operate uniformly.
#       2026-10-03 (owner directive): discovery must find Ollama servers
#       the same way it finds LM Studio, list their models for the
#       picker, and probe them. The addition is additive — LmStudioClient
#       and scan_local_endpoints keep their exact signatures and
#       behaviour, so every engine that constructs a client with no
#       arguments is unaffected.
# BREAKS IF DELETED: No model inference is possible across any engine.
#       The entire generation pipeline halts.

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

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
    Contract: the canonical shape of every request sent to a local
    server. Mirrors the OpenAI chat completions request shape so it can
    be serialized directly into the HTTP body.
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
    Contract: the canonical shape of a successful local-server response.
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
    Contract: raised when a local server returns a non-2xx status or an
    unrecoverable error. Subclasses cover connection errors,
    rate-limit / quota errors, model-not-found, and malformed-input.
    """

    def __init__(self, message: str, status_code: Optional[int] = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class ConnectionError(ApiError):
    """The local server is unreachable -- check that it is running."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class ModelNotFoundError(ApiError):
    """The requested model is not loaded on the local server."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class RateLimitError(ApiError):
    """The local server reported a rate limit -- safe to retry with backoff."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


# ---------------------------------------------------------------------------
# Local server discovery — Ollama, LM Studio, generic OpenAI-compatible
# ---------------------------------------------------------------------------
#
# 2026-10-03 (owner directive): find Ollama servers on localhost, show
# their models in the picker, probe them — the same treatment LM Studio
# already gets. Discovery is strictly additive: it never replaces the
# legacy scan_local_endpoints path that LmStudioClient() still uses.

OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"
LM_STUDIO_DEFAULT_BASE_URL = "http://localhost:1234/v1"

PROVIDER_LABELS: dict[str, str] = {
    "ollama": "Ollama",
    "lm_studio": "LM Studio",
    "openai_compatible": "OpenAI-compatible server",
}

# Ports worth probing, each paired with the provider that usually owns it.
# The order matches the historical scan_local_endpoints order (11434 first),
# so default client construction keeps picking the endpoint it always did.
DEFAULT_ENDPOINT_PORTS: tuple[tuple[int, str], ...] = (
    (11434, "ollama"),
    (1234, "lm_studio"),
    (8080, "openai_compatible"),
    (5000, "openai_compatible"),
)


@dataclass(frozen=True)
class LocalServer:
    """
    Contract: one local inference server that answered a discovery probe.

    Fields:
        kind: "ollama" | "lm_studio" | "openai_compatible".
        base_url: the OpenAI-compatible base the engines talk to
            (Ollama: http://localhost:11434/v1).
        label: human text for the server picker.
        models: model ids the server reported, in the server's own order.
        native_url: the provider's non-OpenAI root when it has one
            (Ollama: http://localhost:11434); None otherwise.
    """
    kind: str
    base_url: str
    label: str
    models: tuple[str, ...] = ()
    native_url: Optional[str] = None

    @property
    def model_count(self) -> int:
        """How many models this server reported."""
        return len(self.models)

    def as_dict(self) -> dict[str, Any]:
        """Serializable shape for the controller/UI seam."""
        return {
            "kind": self.kind,
            "label": self.label,
            "base_url": self.base_url,
            "native_url": self.native_url,
            "models": list(self.models),
            "model_count": self.model_count,
        }


def provider_label(kind: str) -> str:
    """Human label for a provider kind; unknown kinds pass through."""
    return PROVIDER_LABELS.get(kind, kind.replace("_", " ").title())


def provider_kind_for_url(base_url: str) -> str:
    """
    Contract: best-effort provider kind for a base_url, by port
    heuristic. Used when a client was built from a bare URL (the legacy
    auto-scan path) so the UI can still name the runtime honestly.
    """
    url = (base_url or "").lower()
    if ":11434" in url:
        return "ollama"
    if ":1234" in url:
        return "lm_studio"
    return "openai_compatible"


def _http_get_json(url: str, timeout: float) -> Optional[dict[str, Any]]:
    """
    Contract: GET `url`, return the parsed JSON object body, or None when
    the server is absent, slow, non-2xx, or not speaking JSON.

    This is the single HTTP seam for discovery — tests monkeypatch it
    instead of opening sockets.
    """
    try:
        response = httpx.get(url, timeout=timeout)
    except Exception:  # noqa: BLE001 — every transport failure means "absent"
        return None
    if response.status_code != 200:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _models_from_openai_payload(payload: Any) -> list[str]:
    """Model ids from an OpenAI-compatible GET /v1/models body."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    return [entry["id"] for entry in data
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)]


def _models_from_ollama_tags(payload: Any) -> list[str]:
    """Model names from an Ollama native GET /api/tags body."""
    if not isinstance(payload, dict):
        return []
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    names: list[str] = []
    for entry in models:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("model")
        if isinstance(name, str) and name:
            names.append(name)
    return names


def _ollama_host_roots() -> list[str]:
    """Extra Ollama candidates from OLLAMA_HOST (default 127.0.0.1:11434).

    Ollama's own CLI reads OLLAMA_HOST, so a user who moved the server
    has already told the machine where it lives — discovery honours it
    instead of assuming 11434.
    """
    import os

    raw = (os.environ.get("OLLAMA_HOST") or "").strip()
    if not raw:
        return []
    if "://" not in raw:
        raw = "http://" + raw
    return [raw.rstrip("/")]


def _endpoint_key(root: str) -> str:
    """
    Contract: a dedup key that treats localhost, 127.0.0.1 and ::1 as one
    host. Measured live 2026-10-03: OLLAMA_HOST=127.0.0.1:11434 otherwise
    reported the same running Ollama twice, once per host spelling.
    """
    parts = urlsplit(root)
    host = (parts.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0", "[::1]"}:
        host = "localhost"
    return f"{host}:{parts.port or ''}"


def _candidate_roots(
    ports: tuple[tuple[int, str], ...],
    extra_roots: list[str],
) -> list[tuple[str, str]]:
    """Ordered, de-duplicated (root, declared_kind) probe candidates.

    A later, more specific declaration wins: when OLLAMA_HOST names a port
    already in the default list, that port is relabelled Ollama rather
    than probed twice.
    """
    ordered: list[tuple[str, str]] = []
    index_by_key: dict[str, int] = {}

    def add(root: str, kind: str) -> None:
        root = root.rstrip("/")
        key = _endpoint_key(root)
        if key in index_by_key:
            position = index_by_key[key]
            if kind == "ollama":
                ordered[position] = (ordered[position][0], "ollama")
            return
        index_by_key[key] = len(ordered)
        ordered.append((root, kind))

    for port, kind in ports:
        add(f"http://localhost:{port}", kind)
    for root in extra_roots:
        add(root, "openai_compatible")
    for root in _ollama_host_roots():
        add(root, "ollama")
    return ordered


def _probe_root(
    root: str,
    declared_kind: str,
    get: Callable[[str, float], Optional[dict[str, Any]]],
    timeout: float,
) -> Optional[LocalServer]:
    """Probe one candidate root; None when neither API lists models."""
    native_models: list[str] = []
    openai_models: list[str] = []
    is_ollama_native = False

    tags = get(f"{root}/api/tags", timeout)
    if isinstance(tags, dict) and isinstance(tags.get("models"), list):
        is_ollama_native = True
        native_models = _models_from_ollama_tags(tags)

    listing = get(f"{root}/v1/models", timeout)
    if isinstance(listing, dict):
        openai_models = _models_from_openai_payload(listing)

    if not is_ollama_native and not openai_models:
        return None

    kind = "ollama" if is_ollama_native else declared_kind
    return LocalServer(
        kind=kind,
        base_url=f"{root}/v1",
        label=provider_label(kind),
        models=tuple(openai_models or native_models),
        native_url=root if kind == "ollama" else None,
    )


def discover_local_servers(
    *,
    timeout: float = 1.0,
    ports: Optional[tuple[tuple[int, str], ...]] = None,
    http_get: Optional[Callable[[str, float], Optional[dict[str, Any]]]] = None,
    extra_roots: Optional[list[str]] = None,
) -> list[LocalServer]:
    """
    Contract: probe localhost for inference servers and return every one
    that answered, together with the models it reported, in candidate
    order.

    Two probes per candidate, in this order:
      1. Ollama native        GET <root>/api/tags   -> models[].name
      2. OpenAI-compatible    GET <root>/v1/models  -> data[].id
    A server is reported when either probe returns a usable model list.
    `kind` is the candidate's declared provider, upgraded to "ollama"
    when the native tags endpoint answered. Candidates are de-duplicated
    by host+port before probing, so an OLLAMA_HOST that repeats a default
    port yields one server, not two.

    Candidates are probed concurrently. Measured live 2026-10-03: on
    Windows an unbound localhost port hangs until the timeout rather than
    refusing, so a sequential sweep cost 10.4 s; concurrent probing
    brings that to roughly one timeout.

    `timeout` is a localhost budget — raise it only when OLLAMA_HOST
    points at a remote machine.

    Raises nothing: an unreachable port is simply absent from the result.
    """
    get = http_get or _http_get_json
    candidates = _candidate_roots(
        ports if ports is not None else DEFAULT_ENDPOINT_PORTS,
        list(extra_roots or []),
    )
    if not candidates:
        return []

    servers: list[Optional[LocalServer]] = [None] * len(candidates)
    with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as pool:
        futures = [
            pool.submit(_probe_root, root, kind, get, timeout)
            for root, kind in candidates
        ]
        for position, future in enumerate(futures):
            try:
                servers[position] = future.result()
            except Exception:  # noqa: BLE001 — a probe never breaks discovery
                logger.debug("Endpoint probe failed for %s", candidates[position][0],
                             exc_info=True)
    return [server for server in servers if server is not None]


def server_for_kind(servers: list[LocalServer],
                    kind: str) -> Optional[LocalServer]:
    """First detected server of `kind` (e.g. 'ollama'), else None."""
    wanted = (kind or "").strip().lower()
    for server in servers:
        if server.kind == wanted:
            return server
    return None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def scan_local_endpoints(
    timeout: float = 2.0,
    *,
    opener: Optional[Callable[[str, float], bool]] = None,
) -> list[str]:
    """
    Contract: detect Ollama (11434) and LM Studio (1234) plus common locals,
    returning the OpenAI-compatible base URL of each port that answered, in
    port order.

    Same three paths per port, same "first path that answers wins" rule, same
    return shape as the original sequential scan — only the mechanism changed.
    Probes now run concurrently. Measured 2026-10-03: the sequential version
    cost **18.7 s of a 21.5 s application start**, because an unbound localhost
    port on Windows hangs until the timeout instead of refusing, and the scan
    paid that timeout once per port/path pair in series. Concurrency removes
    the cost without changing which endpoint is chosen.

    `opener` is the test seam: callable(url, timeout) -> reachable?. Defaults
    to urllib.request.urlopen.
    """
    def _default_opener(url: str, probe_timeout: float) -> bool:
        import urllib.request
        try:
            urllib.request.urlopen(url, timeout=probe_timeout)
            return True
        except Exception:  # noqa: BLE001 — any failure means "not there"
            return False

    probe = opener or _default_opener
    ports = (11434, 1234, 8080, 5000)
    paths = ("/v1/models", "/", "/api/tags")
    urls = [f"http://localhost:{port}{path}" for port in ports for path in paths]

    with ThreadPoolExecutor(max_workers=len(urls)) as pool:
        reachable = list(pool.map(lambda url: probe(url, timeout), urls))

    endpoints: list[str] = []
    for index, port in enumerate(ports):
        first = index * len(paths)
        if any(reachable[first:first + len(paths)]):
            endpoints.append(f"http://localhost:{port}/v1")
    return endpoints


class OpenAICompatibleClient:
    """
    Contract: wraps all HTTP communication with one local server that
    speaks the OpenAI chat completions protocol. Provides a single
    synchronous generate() method that accepts a ModelRequest and
    returns a ModelResponse.

    Responsibilities:
      - POST to {base_url}/chat/completions
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

    #: Used in user-facing error text. Subclasses name their runtime.
    provider_name: str = "the local model server"
    #: Machine-readable provider key ("ollama" / "lm_studio" /
    #: "openai_compatible"); recorded in capability verdicts.
    provider_kind: str = "openai_compatible"

    def __init__(self, base_url: str, timeout: int = 600) -> None:
        # 600s: escalated token budgets (up to MAX_TOKENS_CEILING=32768)
        # at ~40 tok/s local generation can exceed the old 300s cap.
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
        Contract: send request to the local server and return a
        structured response. Performs exactly one HTTP attempt; callers
        should wrap in retry logic for transient failures.

        Endpoint: POST {base_url}/chat/completions

        Raises:
            ConnectionError: the server is unreachable.
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
            raise ConnectionError(f"Cannot reach {self.provider_name} at {self.base_url}: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise ApiError(f"Request to {self.provider_name} timed out after {self.timeout}s: {exc}", retryable=True) from exc

        if response.status_code == 404:
            raise ModelNotFoundError(
                f"Model '{request.model}' not found or not loaded in {self.provider_name}. "
                f"Load the model first in the {self.provider_name} UI."
            )
        if response.status_code == 429:
            raise RateLimitError(f"{self.provider_name} rate-limited the request (HTTP 429)")

        if response.status_code != 200:
            raise ApiError(
                f"{self.provider_name} returned HTTP {response.status_code}: {response.text}",
                status_code=response.status_code,
                retryable=response.status_code >= 500,
            )

        try:
            return ModelResponse.from_dict(response.json())
        except (ValueError, KeyError) as exc:
            raise ApiError(f"Malformed response from {self.provider_name}: {exc}") from exc

    def is_available(self) -> bool:
        """
        Contract: returns True if the server is reachable and responding
        on the configured base_url. Used for health checks before
        attempting generation.
        """
        try:
            session = self._get_session()
            resp = session.get("/models")
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
            return False

    def list_models(self) -> list[str]:
        """
        Contract: return the ids of the models the server currently has
        available (loaded or load-on-demand), via GET /models.

        Raises:
            ConnectionError: the server is unreachable.
            ApiError: non-200 response or malformed body.
        """
        session = self._get_session()
        logger.info("Listing models from %s/models", self.base_url)
        try:
            resp = session.get("/models")
        except httpx.ConnectError as exc:
            raise ConnectionError(f"Cannot reach {self.provider_name} at {self.base_url}: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise ApiError(f"Request to {self.provider_name} timed out after {self.timeout}s: {exc}", retryable=True) from exc
        if resp.status_code != 200:
            raise ApiError(
                f"{self.provider_name} returned HTTP {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
                retryable=resp.status_code >= 500,
            )
        try:
            data = resp.json()
            return [entry["id"] for entry in data.get("data", []) if "id" in entry]
        except (ValueError, KeyError, TypeError) as exc:
            raise ApiError(f"Malformed model list from {self.provider_name}: {exc}") from exc


class LmStudioClient(OpenAICompatibleClient):
    """
    Contract: the LM Studio client — and, historically, the project's
    single auto-detecting client. The LM Studio local server exposes an
    OpenAI-compatible API at http://localhost:1234/v1 by default (port
    configurable via Settings > Server in the LM Studio UI).

    When constructed with no base_url it keeps the original behaviour:
    scan localhost (11434, 1234, 8080, 5000) and take the first endpoint
    that answers, falling back to http://localhost:1234/v1. Callers that
    need a specific provider should use discover_local_servers() plus
    client_for_server() instead.
    """

    provider_name = "LM Studio"
    provider_kind = "lm_studio"

    def __init__(self, base_url: str = None, timeout: int = 600) -> None:
        if base_url is None:
            scanned = scan_local_endpoints()
            base_url = scanned[0] if scanned else LM_STUDIO_DEFAULT_BASE_URL
        super().__init__(base_url, timeout)


class OllamaClient(OpenAICompatibleClient):
    """
    Contract: the Ollama client. Ollama serves an OpenAI-compatible API
    under http://localhost:11434/v1 (since 0.1.24) and its native API at
    http://localhost:11434 (/api/tags, /api/chat).

    Model listing is belt-and-braces: it prefers the OpenAI-compatible
    /v1/models listing and falls back to the native /api/tags listing,
    so older Ollama builds still populate the picker. Generation goes
    through the same OpenAI-compatible path as every other runtime, so
    the Guardrail Loop, policy levers, and probe behave identically.
    """

    provider_name = "Ollama"
    provider_kind = "ollama"

    def __init__(self, base_url: str = None, timeout: int = 600) -> None:
        super().__init__(base_url or OLLAMA_DEFAULT_BASE_URL, timeout)

    @property
    def native_tags_url(self) -> str:
        """Ollama's native model listing, derived from the base_url."""
        root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        return f"{root}/api/tags"

    def list_models(self) -> list[str]:
        """
        Contract: model ids Ollama can serve, preferring GET /v1/models
        and falling back to the native GET /api/tags.

        Raises:
            ConnectionError: Ollama is unreachable on both endpoints.
            ApiError: both endpoints answered but neither listed models.
        """
        failure: Optional[ApiError] = None
        try:
            models = super().list_models()
            if models:
                return models
        except ApiError as exc:
            failure = exc

        native = _models_from_ollama_tags(
            _http_get_json(self.native_tags_url, 2.0))
        if native:
            return native
        if failure is not None:
            raise failure
        raise ApiError(
            "Ollama returned no models from /v1/models or /api/tags — "
            "pull a model first (ollama pull <name>)."
        )

    def is_available(self) -> bool:
        """Contract: True when either the OpenAI-compatible endpoint or
        the native tags endpoint answers."""
        if super().is_available():
            return True
        return _http_get_json(self.native_tags_url, 2.0) is not None


def client_for_server(server: LocalServer,
                      *, timeout: int = 600) -> OpenAICompatibleClient:
    """
    Contract: the client that talks to one detected server. Ollama gets
    OllamaClient (native /api/tags fallback); everything else gets
    LmStudioClient, which is a plain OpenAI-compatible client despite
    the historical name.
    """
    if server.kind == "ollama":
        return OllamaClient(base_url=server.base_url, timeout=timeout)
    return LmStudioClient(base_url=server.base_url, timeout=timeout)
