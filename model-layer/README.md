# Model Layer

The model-layer provides the AI inference foundation for the entire system. It
discovers the local inference servers running on the machine, manages the client
connection to whichever one is selected, loads and renders prompt templates,
performs schema validation on model outputs, and implements retry logic with
failover to ensure reliability. It is the guardrail layer that ensures all
generated content is accurate, structured, and aligned with quality standards —
not dependent on model size alone. If this engine is deleted, no AI generation,
validation, or prompt processing is possible across any other engine.

## Inference backends

`client.py` owns two responsibilities that are deliberately separate:

1. **Discovery** — `discover_local_servers()` probes localhost and returns a
   `LocalServer` for every runtime that answered, with the models it reported:

   | Probe | Endpoint | Used for |
   |---|---|---|
   | Ollama native | `GET /api/tags` | Detecting Ollama, and listing models on older builds |
   | OpenAI-compatible | `GET /v1/models` | Detecting every runtime, including LM Studio |

   Ports probed: `11434` (Ollama), `1234` (LM Studio), `8080`, `5000`. The
   `OLLAMA_HOST` environment variable adds a candidate when Ollama was moved.

2. **Clients** — every runtime speaks the OpenAI chat-completions protocol, so
   one base class carries generation and health:

   | Class | Default base URL | Notes |
   |---|---|---|
   | `OpenAICompatibleClient` | — | `generate()`, `is_available()`, `list_models()` |
   | `LmStudioClient` | `http://localhost:1234/v1` | Historical name; auto-scans when given no URL |
   | `OllamaClient` | `http://localhost:11434/v1` | Falls back to native `/api/tags` for model listing |

   `client_for_server(LocalServer)` picks the right class for a detected server.

The discovery layer is strictly additive. `LmStudioClient()` and
`scan_local_endpoints()` keep their original signatures and behaviour, so every
engine that constructs a client with no arguments is unaffected — a change
verified by `test_client.py::TestLegacyLmStudioPathUnchanged`.

## Generation contract

Whatever the backend, generation goes through the same path:
`pipeline.py` renders the prompt, calls the client once per attempt, extracts
JSON, validates against the schema, and retries with feedback. `policy.py`
injects the JSON-discipline addendum, JSON mode, thinking suppression, and the
size-aware attempt budget. Because both backends are OpenAI-compatible, none of
that needed to change to support Ollama.

## Probe

`capabilities.py` grades the loaded model one shot per task family and records
`provider` and `endpoint` in the verdict, so a stored verdict says which runtime
produced it. `summarize_verdict()` prefixes the provider label when present and
is unchanged for verdicts written before 2026-10-03.

---

UPDATE 2026-10-03 — Ollama servers are detected, listed, and probed exactly like
LM Studio: `discover_local_servers()`, `OllamaClient` with a native `/api/tags`
fallback, a Server dropdown in the shell, and provider attribution in capability
verdicts. Additive only — the LM Studio path is unchanged and pinned by
regression tests. Release note: `RELEASE_NOTE_2026_10_03.md`.
