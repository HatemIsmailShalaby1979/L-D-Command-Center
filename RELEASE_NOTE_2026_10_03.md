# App Owner — Release Note 2026-10-03 (One-Pager)

**What:** Ollama becomes a first-class inference backend, exactly as LM Studio
already was. Local servers are auto-detected, their models fill a new Server +
Model picker pair in the shell, and the capability probe grades and attributes
whichever runtime is selected.

**Why:** The app claimed "local model" but behaved like "LM Studio only" in every
user-facing string, in the model picker, and in the probe. Measured on this
machine: Ollama was running with three models loaded, and the shell still said
`LM Studio: not reachable` and showed nothing. Root cause was not a broken
client — `LmStudioClient` was already talking to Ollama's OpenAI-compatible
endpoint over the legacy auto-scan — it was that the runtime was never
*identified*, so the UI could not name it, list it, or let the user choose it.

**When:** Released now (branch `release-2026-10-03`). Additive only — no
previously implemented option was disabled, removed, or renamed.

**Cost:** Zero new dependencies. `concurrent.futures` and `urllib.parse` are
standard library. Rollback: `git revert` the release commit (the LM Studio path
is unchanged, so an older build keeps working exactly as it did).

**Named owner:** This session (Codex, App Owner role).

## What changed

| Area | Change |
|---|---|
| `model-layer/client.py` | `discover_local_servers()` + `LocalServer` + `_endpoint_key`/`_candidate_roots`/`_probe_root`; `OllamaClient` (native `/api/tags` listing fallback); `provider_label`, `provider_kind_for_url`, `server_for_kind`, `client_for_server`; `provider_name`/`provider_kind` on the clients. `LmStudioClient` and `scan_local_endpoints` byte-identical in behaviour. |
| `model-layer/capabilities.py` | Verdict records `provider` + `endpoint`; `summarize_verdict` prefixes the provider label when present. |
| `desktop_shell/controller.py` | `list_local_servers()` (cached detection), `select_endpoint()`, `active_provider_label()`, `active_endpoint()`; provider-neutral `no_model` copy; an injected client is never replaced. |
| `desktop_shell/app.py` | Header **Server** dropdown (detected off the UI thread on startup and on Reload), provider-named health bar, provider-neutral error dialogs and Audio Studio copy. |
| Tests | `model-layer/test_client.py` (new, 41 tests), 5 provider-attribution tests in `test_capabilities.py`, 8 endpoint tests in `test_controller.py`. |
| Docs | README, model-layer/README, desktop_shell/README, CONTEXT (5 new glossary terms), MASTER_STORY, index.html, governance UPDATE lines, FILE_MANIFEST, TASKS, E2E_SMOKE_REPORT. |

## Evidence

**Executed and measured (this machine, 2026-10-03):**

- Offline suite: **1114 passed, 7 live deselected, 0 failed** (baseline 1060;
  +50 new tests). Run with `python -m pytest -q`.
- Live discovery against the running Ollama (`OLLAMA_HOST=127.0.0.1:11434`):
  `discover_local_servers()` → **1 server**, `kind='ollama'`,
  `base_url=http://localhost:11434/v1`, 3 models
  (`granite4.2:latest`, `gemma4:31b-cloud`, `lfm2.5:8b`), in **2.29 s**.
- Live controller round-trip: `list_local_servers()` → `['Ollama']`;
  `select_endpoint('ollama')` → ok; `list_available_models()` → the 3 real
  model ids; `check_model_health()` → `ready`; `active_provider_label()` →
  `Ollama`.

**Two real defects found by that live run, and fixed:**

1. `OLLAMA_HOST=127.0.0.1:11434` made the same Ollama appear **twice** in the
   picker (`localhost` and `127.0.0.1` spellings). Fixed with a host-alias
   dedup key; pinned by `test_ollama_host_aliasing_a_default_port_does_not_duplicate`.
2. Discovery took **10.4 s** because on Windows an unbound localhost port hangs
   until the timeout instead of refusing. Fixed by probing candidates
   concurrently (2.29 s measured, ~1 timeout worst case); pinned by
   `test_each_candidate_is_probed_exactly_once`.

**Reasoned, not executed:**

- LM Studio was not running in this session, so the LM Studio path was verified
  by tests and by code inspection only, not live. `TestLegacyLmStudioPathUnchanged`
  pins its behaviour.
- A full live six-profile capability probe against a real Ollama model was not
  completed in this session (CPU-bound generation; see `E2E_SMOKE_REPORT.md`).
  The probe path itself is unchanged and covered by the existing scripted-client
  suite; what is unverified is its wall-clock behaviour on this hardware.
- The packaged `.exe` was not rebuilt in this session. The Release workflow
  (`release.yml`, manual dispatch, behind the `release` environment approval
  gate) rebuilds it from this commit.

## What broke / what users saw before this change

- A running Ollama was invisible: the Model dropdown was empty and the health
  bar read `LM Studio: not reachable`, even with a model loaded and ready.
- There was no way to choose a runtime at all.

## Next

- Run a full live capability probe against a loaded Ollama model and record the
  verdict document (provider + endpoint now appear in it).
- Rebuild and verify `dist/ldcc.exe` through `build_release.bat`, then publish
  via the `Release` workflow's approval gate.
- Confirm the Server dropdown renders correctly in a real windowed session
  (tkinter Tcl environment permitting on this machine).
