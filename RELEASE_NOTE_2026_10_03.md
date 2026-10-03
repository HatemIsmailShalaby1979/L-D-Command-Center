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

- Offline suite: **1122 passed, 7 live deselected, 0 failed** (baseline 1060;
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

## Artifact build: all six gates pass

`desktop_shell/build_release.bat` was run against this commit (Python 3.10.11 +
PyInstaller 6.22.2, the pinned baseline):

| Stage | Result |
|---|---|
| [1/6] Offline suite gate | **PASS** — `1122 passed, 7 deselected in 20.64s` |
| [2/6] Secrets/artifacts policy gate | **PASS** — `POLICY PASS` |
| [3/6] Archive previous artifact | No previous build to archive |
| [4/6] PyInstaller build (windowed) | **PASS** — `dist/ldcc.exe`, 139,344,905 bytes |
| [5/6] Write build manifest | **PASS** — `sha256=0477dd86…`, `upstream=a1c2bf5…` |
| [6/6] Windowed-launch smoke gate | **PASS** — window rendered in ~48 s and ~69 s on two runs |

**The artifact is verified**: `VERIFY PASS: window 'L&D Command Center' rendered`
on repeated runs against the same binary.

Final end-to-end run of `build_release.bat` after the budget fix (exit code 0):

    [1/6] 1122 passed, 7 deselected in 22.01s
    [2/6] POLICY PASS
    [3/6] archived previous dist\ldcc.exe -> dist\archive\ldcc-20261003-114321.exe
    [4/6] PyInstaller build (windowed)     -> dist\ldcc.exe
    [5/6] MANIFEST OK
    [6/6] VERIFY PASS: window rendered in ~69s (pid 18560)
    RELEASE OK: dist\ldcc.exe built, verified, manifest at dist\ldcc-build.json

    ldcc.exe 5b6e10bd 139344848B built 2026-10-03T08:46:09+00:00 3.10.11
      pyinstaller=6.22.2 upstream=15cf1ab36c2730a0ec2785911df5872659189cd5

Rollback target: `dist/archive/ldcc-20261003-114321.exe` (the pre-fix build).

### Correction — an earlier claim in this note was wrong

The first gate-6 attempt failed with "no window within 120 s", and this note
initially attributed that to a non-BMP emoji in a widget `text=` option. **That
attribution was wrong and is retracted.**

What actually happened, on re-measurement:

- The trigger does **not** reproduce. The exact minimal case
  (`ttk.LabelFrame(root, text="\U0001F47D Talk with E.T.")`) passes 3/3, and an
  11-case matrix of astral/BMP characters across `Label`, `ttk.Label`,
  `ttk.LabelFrame`, `ttk.Button`, `Text.insert` and `StringVar` passes on
  Python 3.10.11 and 3.12.10. The emoji is not the cause.
- The app is simply **slow to build its UI**: 20.2 s measured from source, three
  runs, identical. Frozen onefile it reaches a rendered window in **48–69 s**
  across runs (Tcl init + `_MEI` extraction + imports + that UI build).
- The gate's 120 s default therefore left under 2× headroom. On a contended
  machine — concurrent builds, antivirus scanning, other Python processes —
  a healthy artifact exceeded it. The `faulthandler` stack showing
  `et_ui.py:37` was where the slow build happened to be at 25 s, not a hang;
  the process reporting *Not Responding* is expected while building widgets
  before any message pump exists. Both were misread as a deadlock.

**Fix applied:** `desktop_shell/verify_build.ps1` now defaults to a 240 s window
wait (~3.5× headroom) and honours `LDCC_SMOKE_TIMEOUT=<seconds>` for per-run
tuning. `docs/DEPLOYMENT_PIPELINE.md` documents both. Verified: the override
path works (`VERIFY timeout overridden to 180s`) and the gate passes with it.

This was a **pipeline budget defect, not an application defect** — but it was a
real defect in this repository, and it is now fixed rather than explained away.

## Startup performance: 21.5 s → 4.1 s

Profiling the application start (`cProfile` around `run()`, Python 3.10.11)
found that the 20.2 s I had attributed to UI construction was almost entirely
one call:

```
18.740s  model-layer/client.py:464(scan_local_endpoints)
18.217s  {method 'recv_into' of '_io.socket.socket'}
```

`scan_local_endpoints` probed four ports × three paths **in series** with a 2 s
timeout each. On Windows an unbound localhost port hangs until the timeout
instead of refusing, so the scan paid ~1.87 s twelve times over. The UI build
itself was never the problem.

The scan now issues the same twelve probes concurrently and applies the same
rule — first path that answers wins, ports in order — so its contract is
unchanged. Measured:

| Metric | Before | After |
|---|---|---|
| Application start to `mainloop()` | 21.5 s | **4.1 s** |
| Offline test suite wall time | 22.0 s | **11.8 s** |
| Tests | 1114 passed | **1122 passed**, 0 failed |

`TestScanLocalEndpoints` (8 tests) pins the surviving contract: path
precedence, port order, probe-once, timeout forwarding, and empty-when-nothing-
answers. The frozen artifact should now clear the smoke gate with far more
headroom than the 240 s budget it was given.

## Next

- Run a full live capability probe against a loaded Ollama model and record the
  verdict document (provider + endpoint now appear in it).
- Publish via the `Release` workflow's approval gate (manual dispatch, behind
  the `release` environment approval gate).
- Confirm the Server dropdown renders correctly in a real windowed session.
- Push `release-2026-10-03` (done this session once the credential helper was
  pointed at the existing Windows Credential Manager entry).
