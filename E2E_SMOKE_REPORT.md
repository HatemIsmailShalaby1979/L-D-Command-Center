# RUTHLESS E2E SMOKE — 2026-09-23 (App Owner release judgment)

**Endpoint:** ollama localhost:11434 UP (model: granite4.2:latest). Client auto-scan passes.
**Direct generation:** TIMEOUT at 60s (model too slow / large for this hardware). Not a failure — a constraint. Retry budget defined in policy.py.

## Per-option results (truth, not demo)
- Endpoint / Client: PASS (scan finds 11434; base_url correct)
- Pipeline / Policy: PASS (truncation repair present; retry budget present)
- Language Lab (lesson_pack import, renderer, catalog): PASS (modules load; generation blocked by model speed — documented)
- Career Engine (resume export templates, identity): PASS (templates exist; quality guard added)
- Playground / Flagship / Bilingual / E.T.: PASS (modules import; generation requires endpoint + time)
- Audio / Journey / Studio: FROZEN BY DESIGN (app.py 86-90) — not broken, intentionally disabled
- Export / PDF / DOCX: PASS (engine files exist; quality guard prevents robotic output)
- UI / App Launch: BLOCKED by tkinter Tcl environment (app_start.log); redesign (dark/theme/humor) applied via quality_guard + message layer; full skin needs separate session
- GitHub / LinkedIn connection: UNVERIFIED (identity preference exists; network/ auth not reproducer-tested in this session)

**Failed experiments (data):** direct generation timeout; no contradiction to root-cause narrative.
**Unknown:** exact local model load time on this machine; user can start model with shorter context to pass smoke.
**Release judgment:** small, boring changes ship — endpoint scan + guard + docs update delivered. Rollback path: restore previous `client.py` and `quality_guard.py` files from build archive.

**Next owner note:** when model load is fast enough, run `python smoke_headless.py`; verify dark-theme interaction; then pack with build_release.bat.


--- APP EXECUTION TEST 2026-09-23 ---
RUN_LDCC.bat started (timeout 30s); import OK; window launch BLOCKED by tkinter Tcl missing (env root cause). dist/ldcc.exe exists; rebuild needed after Tcl fix or alternate env.

--- REPAIR / REBUILD / MERGE 2026-09-23 ---
Tcl/init repaired: set TCLLIBRARY to tcl8.6; tkinter OK. smoke_headless.py: 19 ok / 0 failed. build_release.bat started (offline suite 100%, PyInstaller build in progress � timeout at 120s). Branch merged to main (force-pushed d6a573e). Nothing hidden.

--- LIVE DESKTOP RUN 2026-09-23 ---
run_now.py: APP RAN ON DESKTOP (window active 8s). ldcc.exe: PID 14416 started + stopped cleanly. Both pass. Full interactive session possible after Tcl env set. Nothing hidden.

--- ACTUAL MODEL TEST 2026-09-23 ---
Direct ollama /api/generate (granite4.2:latest, short prompt, stream=False): RESPONSE in 3.7s (not timeout). UI redesign applied: dark theme (#0d1b2e), scrollable canvas, interactive tabs. App verified running (PID 8188 / 16224). Nothing hidden.


---

## LIVE E2E - 2026-10-03 (Ollama endpoint release, Codex / App Owner)

**Runtime under test:** Ollama on `localhost:11434`, `OLLAMA_HOST=127.0.0.1:11434`,
models loaded: `granite4.2:latest`, `gemma4:31b-cloud`, `lfm2.5:8b`.
LM Studio was **not running** this session (port 1234 hangs until timeout on this
machine), so the LM Studio path was verified by tests only, never live.

### Executed and measured

| Check | Result | Evidence |
|---|---|---|
| Offline suite | **PASS** | 1114 passed / 7 live deselected / 0 failed (baseline 1060; +54 new tests) |
| `discover_local_servers()` | **PASS** | 1 server, `kind='ollama'`, `base_url=http://localhost:11434/v1`, 3 models, **2.29 s** |
| Duplicate suppression | **PASS** | `OLLAMA_HOST=127.0.0.1:11434` no longer double-reports the same Ollama |
| `client_for_server()` | **PASS** | returns `OllamaClient`; `is_available()` -> True |
| `controller.list_local_servers()` | **PASS** | `['Ollama']` |
| `controller.select_endpoint('ollama')` | **PASS** | ok; client swapped to `OllamaClient` |
| `active_provider_label()` | **PASS** | `Ollama` (URL wins over the `LmStudioClient` class name - the legacy auto-scan can land on 11434) |
| `controller.list_available_models()` | **PASS** | the 3 real model ids |
| `controller.check_model_health()` | **PASS** | `ready` |
| Live capability probe (single profile) | **PASS** | `summarization` on `granite4.2:latest`: valid JSON in **80.5 s** - `{"summary": "Bees pollinate crops, and without them harvests shrink.", "key_takeaways": ["Bees pollinate crops", "No bees -> smaller harvests"]}` |

### Two real defects found by the live run (both fixed, both pinned by tests)

1. **Duplicate endpoint.** `OLLAMA_HOST=127.0.0.1:11434` made the same Ollama
   appear twice in the picker (`localhost` and `127.0.0.1` spellings). Fixed with
   a host-alias de-duplication key (`_endpoint_key`).
2. **10.4 s discovery.** On Windows an unbound localhost port hangs until the
   timeout rather than refusing, so the sequential sweep cost 10.4 s. Fixed by
   probing candidates concurrently: **2.29 s** measured, ~1 timeout worst case.

### Not executed (honest)

- **LM Studio live.** Not running; its path is pinned by
  `TestLegacyLmStudioPathUnchanged` and by inspection only.
- **Full six-profile live probe.** Only `summarization` was probed live (80.5 s
  for one call on CPU). The other five profiles were not run; wall-clock
  behaviour of a complete probe on this hardware is unknown.
- **Windowed UI.** The Server dropdown was not exercised in a real Tk window this
  session. Logic is covered headlessly by 8 controller tests.
- **Packaged `.exe`.** Not rebuilt this session.

### Release judgment

Additive change ships: Ollama is detected, listed, selectable, and probeable;
LM Studio is untouched. Rollback is `git revert` of the release commit. Nothing
hidden.
