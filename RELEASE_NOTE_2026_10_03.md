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

## What broke / what users saw before this change

- A running Ollama was invisible: the Model dropdown was empty and the health
  bar read `LM Studio: not reachable`, even with a model loaded and ready.
- There was no way to choose a runtime at all.

## Artifact build: gates 1-5 pass, gate 6 blocked by a pre-existing defect

`desktop_shell/build_release.bat` was run against this commit (Python 3.10.11 +
PyInstaller 6.22.2, the pinned baseline):

| Stage | Result |
|---|---|
| [1/6] Offline suite gate | **PASS** — `1114 passed, 7 deselected in 20.64s` |
| [2/6] Secrets/artifacts policy gate | **PASS** — `POLICY PASS` |
| [3/6] Archive previous artifact | No previous build to archive |
| [4/6] PyInstaller build (windowed) | **PASS** — `dist/ldcc.exe`, 139,344,905 bytes |
| [5/6] Write build manifest | **PASS** — `sha256=0477dd86…`, `upstream=a1c2bf5…` |
| [6/6] Windowed-launch smoke gate | **FAIL** — no window within 120 s |

**The artifact is built and traceable to this commit, but it is NOT a verified
release**: the pipeline's own contract stops the release when the smoke gate
fails, and that is the correct outcome here.

**Root cause of gate 6, isolated and proven — and it is not this change:**

- The app hangs during widget construction, before the main window renders.
  A stack dump (`faulthandler.dump_traceback_later`) puts the main thread in
  `desktop_shell/et_ui.py:37` → `ttk.LabelFrame(parent, text="👽 Talk with E.T. …")`
  → `tkinter/ttk.py:773` → `tkinter/__init__.py:2601`. The process shows as
  *Not Responding* with window title `N/A`.
- **Reproduced identically on `main` (2386ca5) without any of this sprint's
  changes** — same file, same line. The defect pre-exists.
- **Minimal reproduction:** with Python 3.10.11 / Tcl-Tk 8.6 on this machine,
  `ttk.LabelFrame(root, text="plain ascii label")` succeeds, while
  `ttk.LabelFrame(root, text="\U0001F47D Talk with E.T.")` hangs the Tcl
  interpreter. The trigger is the non-BMP (astral-plane) emoji in a widget
  `text=` option.
- **Blast radius:** 66 non-BMP characters across `desktop_shell/*.py` and
  `engines/language-lab/et_persona.py`. `et_ui.py:37` is simply the first one
  reached at startup; `exams_ui.py:33`, `lab_ui.py:32`, `skills_ui.py:33/73/173/212`
  and `et_ui.py:171/179` pass the same kind of character to `text=`.

**Not fixed here, deliberately.** It is outside the additive scope of this
sprint, it touches the E.T. / Language Lab UI owned by a different concern, and
`CONSTITUTION.md` §3 says an ambiguous spec escalates rather than gets silently
guessed. Two candidate fixes, for the owner to choose: strip or transliterate
astral-plane characters from widget `text=` options (a small, contained change),
or move to a Tcl/Tk build that handles surrogate pairs (8.7/9). The first is
what the sprint prompt asks the local agent to confirm and apply.

## Next

- Decide the astral-emoji fix above, then re-run `build_release.bat` so gate 6
  can actually verify the window.
- Run a full live capability probe against a loaded Ollama model and record the
  verdict document (provider + endpoint now appear in it).
- Publish via the `Release` workflow's approval gate (manual dispatch, behind
  the `release` environment approval gate).
- Confirm the Server dropdown renders correctly in a real windowed session —
  which is blocked until the emoji hang is resolved.
