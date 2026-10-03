# model-layer/test_client.py
#
# WHAT: Contract tests for local-server discovery (Ollama, LM Studio,
#       generic OpenAI-compatible) and the OllamaClient model-listing
#       fallback.
# WHY:  2026-10-03 owner directive — the app must find Ollama servers on
#       localhost, list their models in the picker, and probe them the
#       same way it already treats LM Studio. These tests pin the two
#       things that can silently break that promise: the discovery
#       heuristic (which port is which runtime, and what happens when a
#       runtime answers only on its native API) and the guarantee that
#       the legacy LM Studio path is unchanged. No sockets are opened —
#       the single HTTP seam (_http_get_json) is injected.
# BREAKS IF DELETED: Endpoint detection could regress to "LM Studio
#       only" without any test noticing, and the Ollama /api/tags
#       fallback could break silently on older builds.

from __future__ import annotations

import httpx
import pytest

from model_layer import client as client_mod
from model_layer.client import (
    DEFAULT_ENDPOINT_PORTS,
    LM_STUDIO_DEFAULT_BASE_URL,
    OLLAMA_DEFAULT_BASE_URL,
    LocalServer,
    LmStudioClient,
    OllamaClient,
    OpenAICompatibleClient,
    client_for_server,
    discover_local_servers,
    provider_kind_for_url,
    provider_label,
    server_for_kind,
)


# ---------------------------------------------------------------------------
# Fakes — one injected HTTP seam, no sockets
# ---------------------------------------------------------------------------

def fake_http_get(mapping):
    """http_get stand-in: url -> parsed JSON payload (missing = absent)."""
    def _get(url, timeout):
        return mapping.get(url)
    return _get


OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
OLLAMA_MODELS_URL = "http://localhost:11434/v1/models"
LMSTUDIO_MODELS_URL = "http://localhost:1234/v1/models"


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class _FakeSession:
    """Minimal httpx.Client stand-in: scripted get/post, optionally raising."""

    def __init__(self, *, get=None, post=None):
        self._get = get or {}
        self._post = post or {}
        self.is_closed = False
        self.calls = []

    def get(self, path):
        self.calls.append(("get", path))
        result = self._get.get(path)
        if isinstance(result, Exception):
            raise result
        return result if result is not None else _FakeResponse(404, None, "nope")

    def post(self, path, json=None):
        self.calls.append(("post", path))
        result = self._post.get(path)
        if isinstance(result, Exception):
            raise result
        return result if result is not None else _FakeResponse(404, None, "nope")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

class TestDiscoverLocalServers:
    def test_finds_ollama_with_its_models(self):
        servers = discover_local_servers(http_get=fake_http_get({
            OLLAMA_TAGS_URL: {"models": [{"name": "granite4.2:latest"}]},
            OLLAMA_MODELS_URL: {"data": [{"id": "granite4.2:latest"},
                                         {"id": "qwen2.5:7b"}]},
        }))
        assert len(servers) == 1
        server = servers[0]
        assert server.kind == "ollama"
        assert server.label == "Ollama"
        assert server.base_url == "http://localhost:11434/v1"
        assert server.native_url == "http://localhost:11434"
        # The OpenAI-compatible listing wins when both answer.
        assert server.models == ("granite4.2:latest", "qwen2.5:7b")
        assert server.model_count == 2

    def test_finds_lm_studio(self):
        servers = discover_local_servers(http_get=fake_http_get({
            LMSTUDIO_MODELS_URL: {"data": [{"id": "google/gemma-4-12b-qat"}]},
        }))
        assert len(servers) == 1
        assert servers[0].kind == "lm_studio"
        assert servers[0].label == "LM Studio"
        assert servers[0].native_url is None
        assert servers[0].models == ("google/gemma-4-12b-qat",)

    def test_ollama_native_only_still_lists_models(self):
        """Older builds expose only /api/tags — discovery must not need /v1."""
        servers = discover_local_servers(http_get=fake_http_get({
            OLLAMA_TAGS_URL: {"models": [{"model": "llama3:8b"},
                                         {"name": "mistral:7b"}]},
        }))
        assert len(servers) == 1
        assert servers[0].kind == "ollama"
        assert servers[0].models == ("llama3:8b", "mistral:7b")

    def test_both_runtimes_are_reported_ollama_first(self):
        servers = discover_local_servers(http_get=fake_http_get({
            OLLAMA_MODELS_URL: {"data": [{"id": "granite4.2:latest"}]},
            LMSTUDIO_MODELS_URL: {"data": [{"id": "gemma-4-12b"}]},
        }))
        assert [s.kind for s in servers] == ["ollama", "lm_studio"]

    def test_nothing_running_returns_empty(self):
        assert discover_local_servers(http_get=fake_http_get({})) == []

    def test_junk_payloads_are_ignored(self):
        servers = discover_local_servers(http_get=fake_http_get({
            OLLAMA_TAGS_URL: {"models": "not-a-list"},
            OLLAMA_MODELS_URL: {"data": "not-a-list"},
            LMSTUDIO_MODELS_URL: {"unexpected": True},
        }))
        assert servers == []

    def test_entries_without_ids_are_dropped(self):
        servers = discover_local_servers(http_get=fake_http_get({
            LMSTUDIO_MODELS_URL: {"data": [{"id": "ok"}, {"nope": 1}, "junk"]},
        }))
        assert servers[0].models == ("ok",)

    def test_extra_roots_are_probed(self):
        servers = discover_local_servers(
            http_get=fake_http_get({
                "http://127.0.0.1:9000/v1/models": {"data": [{"id": "remote"}]},
            }),
            extra_roots=["http://127.0.0.1:9000"],
        )
        assert [s.kind for s in servers] == ["openai_compatible"]
        assert servers[0].base_url == "http://127.0.0.1:9000/v1"

    def test_ollama_host_env_is_honoured(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:11999")
        servers = discover_local_servers(http_get=fake_http_get({
            "http://127.0.0.1:11999/api/tags": {"models": [{"name": "custom"}]},
        }))
        assert len(servers) == 1
        assert servers[0].kind == "ollama"
        assert servers[0].base_url == "http://127.0.0.1:11999/v1"

    def test_ports_argument_overrides_defaults(self):
        servers = discover_local_servers(
            ports=((1240, "lm_studio"),),
            http_get=fake_http_get({
                "http://localhost:1240/v1/models": {"data": [{"id": "m"}]},
            }),
        )
        assert len(servers) == 1
        assert servers[0].base_url == "http://localhost:1240/v1"

    def test_as_dict_is_json_ready(self):
        server = LocalServer(kind="ollama",
                             base_url=OLLAMA_DEFAULT_BASE_URL,
                             label="Ollama",
                             models=("a", "b"),
                             native_url="http://localhost:11434")
        payload = server.as_dict()
        assert payload["models"] == ["a", "b"]
        assert payload["model_count"] == 2
        assert payload["native_url"] == "http://localhost:11434"

    def test_ollama_host_aliasing_a_default_port_does_not_duplicate(
            self, monkeypatch):
        """Measured live 2026-10-03: OLLAMA_HOST=127.0.0.1:11434 made the
        same running Ollama appear twice, once per host spelling."""
        monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:11434")
        servers = discover_local_servers(http_get=fake_http_get({
            OLLAMA_TAGS_URL: {"models": [{"name": "granite4.2:latest"}]},
            OLLAMA_MODELS_URL: {"data": [{"id": "granite4.2:latest"}]},
        }))
        assert len(servers) == 1
        assert servers[0].base_url == "http://localhost:11434/v1"

    def test_ollama_host_relabels_a_default_port(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:8080")
        servers = discover_local_servers(http_get=fake_http_get({
            "http://localhost:8080/api/tags": {"models": [{"name": "custom"}]},
        }))
        assert len(servers) == 1
        assert servers[0].kind == "ollama"
        assert servers[0].base_url == "http://localhost:8080/v1"

    def test_each_candidate_is_probed_exactly_once(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        seen: list[str] = []

        def counting_get(url, timeout):
            seen.append(url)
            return None

        assert discover_local_servers(http_get=counting_get) == []
        assert len(seen) == len(set(seen))
        assert len(seen) == 2 * len(DEFAULT_ENDPOINT_PORTS)

    def test_a_failing_probe_never_breaks_discovery(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_HOST", raising=False)

        def exploding_get(url, timeout):
            if url.startswith("http://localhost:11434"):
                raise RuntimeError("boom")
            return {"data": [{"id": "survivor"}]} if url.endswith("/models") else None

        servers = discover_local_servers(http_get=exploding_get)
        assert [s.kind for s in servers] == ["lm_studio",
                                             "openai_compatible",
                                             "openai_compatible"]


class TestProviderHelpers:
    @pytest.mark.parametrize("kind,expected", [
        ("ollama", "Ollama"),
        ("lm_studio", "LM Studio"),
        ("openai_compatible", "OpenAI-compatible server"),
        ("vllm", "Vllm"),
    ])
    def test_provider_label(self, kind, expected):
        assert provider_label(kind) == expected

    @pytest.mark.parametrize("url,expected", [
        ("http://localhost:11434/v1", "ollama"),
        ("http://127.0.0.1:11434/v1", "ollama"),
        ("http://localhost:1234/v1", "lm_studio"),
        ("http://localhost:8080/v1", "openai_compatible"),
        ("", "openai_compatible"),
    ])
    def test_provider_kind_for_url(self, url, expected):
        assert provider_kind_for_url(url) == expected

    def test_server_for_kind(self):
        servers = [
            LocalServer(kind="lm_studio", base_url="http://localhost:1234/v1",
                        label="LM Studio"),
            LocalServer(kind="ollama", base_url="http://localhost:11434/v1",
                        label="Ollama"),
        ]
        assert server_for_kind(servers, "ollama").label == "Ollama"
        assert server_for_kind(servers, "OLLAMA").label == "Ollama"
        assert server_for_kind(servers, "vllm") is None

    def test_client_for_server_picks_the_right_runtime(self):
        ollama = LocalServer(kind="ollama",
                             base_url="http://localhost:11434/v1",
                             label="Ollama")
        lmstudio = LocalServer(kind="lm_studio",
                               base_url="http://localhost:1234/v1",
                               label="LM Studio")
        assert isinstance(client_for_server(ollama), OllamaClient)
        assert isinstance(client_for_server(lmstudio), LmStudioClient)
        assert client_for_server(ollama).base_url == "http://localhost:11434/v1"


# ---------------------------------------------------------------------------
# OllamaClient
# ---------------------------------------------------------------------------

class TestOllamaClient:
    def test_defaults_to_the_ollama_port(self):
        c = OllamaClient()
        assert c.base_url == OLLAMA_DEFAULT_BASE_URL
        assert c.provider_name == "Ollama"
        assert c.provider_kind == "ollama"

    @pytest.mark.parametrize("base_url,expected", [
        ("http://localhost:11434/v1", "http://localhost:11434/api/tags"),
        ("http://localhost:11434", "http://localhost:11434/api/tags"),
        ("http://192.168.1.9:11434/v1/", "http://192.168.1.9:11434/api/tags"),
    ])
    def test_native_tags_url_derivation(self, base_url, expected):
        assert OllamaClient(base_url=base_url).native_tags_url == expected

    def test_list_models_prefers_openai_listing(self):
        c = OllamaClient()
        c._client = _FakeSession(get={"/models": _FakeResponse(
            200, {"data": [{"id": "granite4.2:latest"}]})})
        assert c.list_models() == ["granite4.2:latest"]

    def test_list_models_falls_back_to_native_tags(self, monkeypatch):
        c = OllamaClient()
        c._client = _FakeSession(
            get={"/models": httpx.ConnectError("no /v1 here")})
        monkeypatch.setattr(
            client_mod, "_http_get_json",
            lambda url, timeout: {"models": [{"name": "llama3:8b"}]}
            if url.endswith("/api/tags") else None)
        assert c.list_models() == ["llama3:8b"]

    def test_list_models_raises_when_both_endpoints_fail(self, monkeypatch):
        c = OllamaClient()
        c._client = _FakeSession(
            get={"/models": httpx.ConnectError("down")})
        monkeypatch.setattr(client_mod, "_http_get_json",
                            lambda url, timeout: None)
        with pytest.raises(client_mod.ApiError):
            c.list_models()

    def test_list_models_raises_when_both_endpoints_are_empty(self,
                                                              monkeypatch):
        c = OllamaClient()
        c._client = _FakeSession(get={"/models": _FakeResponse(200, {"data": []})})
        monkeypatch.setattr(client_mod, "_http_get_json",
                            lambda url, timeout: {"models": []})
        with pytest.raises(client_mod.ApiError, match="no models"):
            c.list_models()

    def test_is_available_falls_back_to_native_tags(self, monkeypatch):
        c = OllamaClient()
        c._client = _FakeSession(get={"/models": _FakeResponse(404)})
        monkeypatch.setattr(client_mod, "_http_get_json",
                            lambda url, timeout: {"models": []})
        assert c.is_available() is True

    def test_is_available_false_when_nothing_answers(self, monkeypatch):
        c = OllamaClient()
        c._client = _FakeSession(get={"/models": _FakeResponse(404)})
        monkeypatch.setattr(client_mod, "_http_get_json",
                            lambda url, timeout: None)
        assert c.is_available() is False


# ---------------------------------------------------------------------------
# Regression guard: the legacy LM Studio path is unchanged
# ---------------------------------------------------------------------------

class TestLegacyLmStudioPathUnchanged:
    def test_default_falls_back_to_the_lm_studio_port(self, monkeypatch):
        monkeypatch.setattr(client_mod, "scan_local_endpoints",
                            lambda timeout=2.0: [])
        assert LmStudioClient().base_url == LM_STUDIO_DEFAULT_BASE_URL

    def test_default_still_takes_the_first_scanned_endpoint(self, monkeypatch):
        monkeypatch.setattr(
            client_mod, "scan_local_endpoints",
            lambda timeout=2.0: ["http://localhost:11434/v1"])
        assert LmStudioClient().base_url == "http://localhost:11434/v1"

    def test_provider_metadata(self, monkeypatch):
        monkeypatch.setattr(client_mod, "scan_local_endpoints",
                            lambda timeout=2.0: [])
        c = LmStudioClient()
        assert c.provider_name == "LM Studio"
        assert c.provider_kind == "lm_studio"
        assert isinstance(c, OpenAICompatibleClient)

    def test_error_text_still_names_lm_studio(self):
        c = LmStudioClient(base_url="http://localhost:1234/v1")
        c._client = _FakeSession(
            get={"/models": httpx.ConnectError("refused")})
        with pytest.raises(client_mod.ConnectionError,
                           match="Cannot reach LM Studio"):
            c.list_models()

    def test_scan_local_endpoints_is_still_exported(self):
        assert callable(client_mod.scan_local_endpoints)
