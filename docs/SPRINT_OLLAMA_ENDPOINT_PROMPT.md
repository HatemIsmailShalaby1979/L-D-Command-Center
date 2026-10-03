# Sprint prompt — Ollama endpoint support for L&D Command Center

**How to use this file.** Everything below the horizontal rule is the prompt.
Paste it whole into the local coding agent (Codex CLI / opencode / Claude Code)
running on this machine, from the repository root. It is self-contained: the
agent needs no other context from the session that wrote it.

**State it assumes.** The implementation is already committed on branch
`release-2026-10-03` (see `RELEASE_NOTE_2026_10_03.md`). If that branch exists,
the agent's job is verification and completion — Phases 3–6 are the work. If it
does not exist, the agent implements Phases 1–2 as well. Phase 0 tells it which
case it is in.

---

# SPRINT: Make Ollama a first-class inference backend in L&D Command Center

You are working in the **L&D Command Center** repository
(`https://github.com/HatemIsmailShalaby1979/L-D-Command-Center`), a local-first
desktop learning / language / career workstation. One local model is the sole
generation brain; today the app detects and drives **LM Studio** on port 1234.
The owner's directive is: **find Ollama servers on localhost too, list their
models in the model dropdown, and probe those models exactly the way LM Studio
is already probed.**

**This is an additive sprint.** No already-implemented option may be disabled,
renamed, removed, or made harder to reach. The LM Studio path must end up
byte-for-byte equivalent in behaviour to what it is now.

## Phase 0 — Reconnaissance (do this first, in this order)

1. `git rev-parse --abbrev-ref HEAD && git log --oneline -5`
2. Read, in this order: `CONSTITUTION.md`, `MASTER_STORY.md`, `BOOT_ROOT.md`,
   `FILE_MANIFEST.md`, `TASKS.md`, `CONTEXT.md`, `AGENT_LOG.md` (last 200 lines).
   These are binding. `CONSTITUTION.md` outranks your own judgement.
3. `git branch -a` — does `release-2026-10-03` exist?
   - **Yes** → the implementation is done. Skip Phase 1 and Phase 2, run Phase 3.
   - **No** → implement Phase 1 and Phase 2 before Phase 3.
4. Confirm the environment:
   - `python -c "import httpx, pytest; print(httpx.__version__, pytest.__version__)"`
     (needs httpx 0.28.1, pytest 9.1.1 per `requirements.txt`)
   - `python -m pytest -q` — record the pass count. This is your baseline.
     Expect **1114 passed, 7 deselected** on the release branch; **1060 passed,
     7 deselected** on `main` before this sprint.
5. Check what local runtimes are actually running:
   `curl -s http://localhost:11434/api/tags` (Ollama) and
   `curl -s http://localhost:1234/v1/models` (LM Studio).
   Note which answered — Phase 3 depends on it.

**Do not skip step 2.** A session that edits files without reading the
constitution is treated as unverified work by this repository.

## Phase 1 — Implementation (only if `release-2026-10-03` is absent)

Read `model-layer/client.py` first. It already contains
`scan_local_endpoints()` — a crude probe that returns the first responding
localhost port. Do **not** delete it and do not change its signature: ~20 call
sites across `engines/` construct `LmStudioClient()` with no arguments and
depend on its behaviour.

### 1.1 `model-layer/client.py` — discovery

Add, without altering anything existing:

- `LocalServer` — a frozen dataclass: `kind` (`"ollama"` | `"lm_studio"` |
  `"openai_compatible"`), `base_url`, `label`, `models: tuple[str, ...]`,
  `native_url: Optional[str]`; plus `model_count` and `as_dict()`.
- `PROVIDER_LABELS`, `OLLAMA_DEFAULT_BASE_URL` (`http://localhost:11434/v1`),
  `LM_STUDIO_DEFAULT_BASE_URL`, `DEFAULT_ENDPOINT_PORTS`
  (`11434` ollama, `1234` lm_studio, `8080`, `5000`).
- `_http_get_json(url, timeout)` — the single HTTP seam; returns a parsed dict
  or `None` on any failure. Tests monkeypatch this instead of opening sockets.
- `discover_local_servers(*, timeout=1.0, ports=None, http_get=None, extra_roots=None) -> list[LocalServer]`.
  Per candidate root, in order: (1) Ollama native `GET <root>/api/tags`
  (`models[].name` or `models[].model`), (2) OpenAI-compatible
  `GET <root>/v1/models` (`data[].id`). Report the candidate when either
  answers with a usable model list; upgrade `kind` to `"ollama"` when the
  native endpoint answered. Never raise — an unreachable port is simply absent.
  - Honour `OLLAMA_HOST` (add `http://` when the scheme is missing).
  - **De-duplicate candidates by host+port, treating `localhost`, `127.0.0.1`
    and `::1` as one host.** This is not theoretical: on the owner's machine
    `OLLAMA_HOST=127.0.0.1:11434`, and without this the same Ollama is
    reported twice and appears twice in the dropdown.
  - **Probe candidates concurrently** (`concurrent.futures.ThreadPoolExecutor`,
    standard library only). On Windows an unbound localhost port *hangs* until
    the timeout instead of refusing, so a sequential sweep costs
    ~10 s; concurrent probing costs ~1 timeout (~2.3 s measured).
  - Return results in candidate order.
- `provider_label(kind)`, `provider_kind_for_url(base_url)` (port heuristic:
  `:11434` → ollama, `:1234` → lm_studio, else openai_compatible),
  `server_for_kind(servers, kind)`, `client_for_server(server)`.

### 1.2 `model-layer/client.py` — clients

- Extract `OpenAICompatibleClient` holding the existing `__init__`,
  `_get_session`, `generate`, `is_available`, `list_models` verbatim. Add class
  attributes `provider_name` (used in error text) and `provider_kind`.
- `LmStudioClient(OpenAICompatibleClient)` — `provider_name = "LM Studio"`,
  `provider_kind = "lm_studio"`; when `base_url is None` keep the **exact**
  existing behaviour: `scan_local_endpoints()` first, else
  `http://localhost:1234/v1`. Every error string it produces must be
  character-identical to today's (`"Cannot reach LM Studio at ..."`, etc.).
- `OllamaClient(OpenAICompatibleClient)` — `provider_name = "Ollama"`,
  `provider_kind = "ollama"`, default base `http://localhost:11434/v1`.
  `native_tags_url` property derives `<root>/api/tags` from `base_url`.
  `list_models()` prefers `/v1/models` and **falls back to native `/api/tags`**
  so older Ollama builds still populate the picker; raise a clear `ApiError`
  when both answer but neither lists models. `is_available()` falls back to the
  native endpoint too.

### 1.3 `model-layer/capabilities.py` — provider attribution

- `probe_model_capabilities(client, *, storage=None, provider=None, endpoint=None)`.
  Keep the existing positional/keyword contract intact — tests call it as
  `probe_model_capabilities(client, storage=store)`.
- Record `provider` and `endpoint` in the verdict document, derived from
  `getattr(client, "provider_kind", None)` and `getattr(client, "base_url", None)`,
  with `"local"` as the last-resort provider.
- `summarize_verdict()` prefixes the provider label (`"Ollama · granite4.2:latest …"`)
  **only when the verdict carries one**, so pre-existing verdicts summarize
  unchanged.
- Keep the substring `"no model loaded"` in the empty-model error — a test
  matches on it.

### 1.4 `desktop_shell/controller.py` — the endpoint seam

- `__init__`: record whether the client was injected
  (`self._client_injected = client is not None`); keep a
  `self._detected: list[LocalServer]` plus a `self._detection_done: bool` flag
  (the flag, not the list — an empty result is a real answer and must not
  trigger a re-probe); infer `self.active_server` from the client's `base_url`
  for free.
  **The URL wins over the class.** `LmStudioClient()` with no arguments
  auto-scans and can legitimately land on port 11434; the UI must then say
  "Ollama", not "LM Studio". Verify this specific case.
- Add `active_provider_label()`, `active_endpoint()`,
  `list_local_servers(*, refresh=False)` (cached; `refresh=True` re-probes),
  `select_endpoint(kind_or_url)` (match exact base_url first, then provider
  kind, then display label; refuse politely with `error_kind="no_model"` when
  nothing matches — never guess), and the private helpers
  `_server_from_client`, `_match_server`.
- `select_endpoint` must **never** replace a caller-injected client. That seam
  is what keeps the headless controller tests honest.
- Make the `ConnectionError` → `no_model` detail mention **both** ports; an
  existing test asserts the string `"localhost:1234"` appears in it.
- Leave `list_available_models`, `check_model_health`, `run_capability_probe`,
  and every other public method's contract unchanged.

### 1.5 `desktop_shell/app.py` — the UI

- Add a **Server** combobox in the header, to the left of the existing Model
  combobox, plus `_server_options`, `_server_combos`, `_apply_servers`,
  `refresh_servers`, `on_server_selected`, and a `reload_all` that re-detects
  servers *and* refills the model list.
- Run startup detection **off the UI thread** (`run_async`): the worker calls
  `ctrl.list_local_servers(refresh=True)`; the `done` callback does the Tk work.
  Never touch Tk widgets from the worker thread.
- `refresh_health()` must name the active provider
  (`Ollama: ready` / `LM Studio: ready`) instead of hardcoding "LM Studio".
- Replace the hardcoded "LM Studio" strings in `ERROR_TITLES["no_model"]`,
  `ERROR_ACTIONS["no_model"]`, the startup status, and the Audio Studio
  "Generation model" label with provider-neutral copy.
- `reload_all` replaces `refresh_model_picker` as the header Reload command;
  the Audio Studio "Reload list" button keeps refreshing models only.

**Gotcha:** the file is UTF-8 and already contains mojibake in unrelated
strings (e.g. `â€¦`). Do not "fix" those — out of scope. Prefer ASCII-only
anchors when editing, and assert your edit landed (see Phase 2).

## Phase 2 — Tests (only if you implemented Phase 1)

- New file `model-layer/test_client.py`. Required coverage: discovery of Ollama
  (`/api/tags` + `/v1/models`), LM Studio, Ollama-native-only builds, both
  runtimes together (Ollama first), nothing running, junk payloads, entries
  without ids, `extra_roots`, `OLLAMA_HOST`, the host-alias de-duplication, the
  probe-once guarantee, a raising probe never breaking discovery,
  `provider_label`, `provider_kind_for_url`, `server_for_kind`,
  `client_for_server`, `OllamaClient.native_tags_url` derivation, the
  `/api/tags` listing fallback, the availability fallback, and a
  `TestLegacyLmStudioPathUnchanged` class proving `scan_local_endpoints` still
  exists and `LmStudioClient()` still defaults to port 1234.
  **No sockets.** Inject `http_get`; use a fake session object for client tests.
- Add provider-attribution tests to `model-layer/test_capabilities.py`.
- Add an endpoint class to `desktop_shell/test_controller.py` covering listing,
  switching by kind and by base_url, refusal on an unknown endpoint, the
  injected-client guarantee, empty detection, caching, and the
  auto-scanned-onto-11434 labelling case.
- Run `python -m pytest -q` and record the count. Every previously passing test
  must still pass.

## Phase 3 — Live verification (the part that cannot be faked)

Scripted clients prove the logic; only a real server proves the integration.
Do all of this against the runtime(s) Phase 0 found.

1. **Discovery.** Call `discover_local_servers()` and print the count, the
   elapsed seconds, and each server's `kind`, `base_url`, `native_url`, and
   model list. Acceptance: the running runtime appears **exactly once**, with
   its real models, in **under 5 seconds**.
2. **Controller round-trip.** With a real `ShellController()`:
   `list_local_servers()` → `select_endpoint(<kind>)` →
   `list_available_models()` → `check_model_health()`. Acceptance: the model
   list matches the runtime's own listing and health is `ready`.
3. **Label correctness.** Assert `active_provider_label()` names the runtime
   that is actually running. If you have `OLLAMA_HOST` set to a `127.0.0.1`
   address, confirm it did not create a duplicate entry.
4. **Probe.** Run a real capability probe against a loaded model. A full
   six-profile probe on CPU is slow — run it in the background with a generous
   budget and report wall-clock time per profile. If it does not finish,
   record that honestly; do not report it as passing. Confirm the stored
   verdict document contains `provider` and `endpoint`.
5. **Windowed UI.** Launch the app (`RUN_LDCC.bat` — never the Python entry
   point from PowerShell; it injects null bytes into argv and Python dies with
   `ValueError: source code string cannot contain null bytes`). Confirm the
   Server dropdown lists the detected runtime, that choosing it refills the
   Model dropdown, and that Probe model completes. If the tkinter Tcl
   environment blocks the window on this machine, say so — that is a known
   pre-existing condition, not a regression.

## Phase 4 — Documentation

Update, in this order: `README.md` (Architecture + an inference-backends table
+ status table + Run-it requirements), `model-layer/README.md`,
`desktop_shell/README.md`, `CONTEXT.md` (glossary: **Local Server**,
**Endpoint Discovery**, **Server Picker**, **Provider Attribution**),
`MASTER_STORY.md` (it still says "via LM Studio" in the Vision and Core Engine
Philosophy sections), `index.html` (status snapshot), `FILE_MANIFEST.md` (a
one-line reason for every new file — `CONSTITUTION.md` §1), `TASKS.md`,
`E2E_SMOKE_REPORT.md` (append, dated), and `AGENT_LOG.md` (append an entry in
the mandated format).

Each of these files already carries a trailing `UPDATE <date> — …` line.
**Append** a new one dated today; do not rewrite history.

Also write `RELEASE_NOTE_<today>.md` in the shape of
`RELEASE_NOTE_2026_10_03.md`: What / Why / When / Cost / Named owner / What
changed / **Evidence** / What broke / Next. In the Evidence section, separate
what you executed and measured from what you reasoned. State failures and
unknowns in the same breath as successes.

## Phase 5 — Release

- Commit on a `release-<YYYY-MM-DD>` branch. Commits inside this workspace are
  pre-authorized; **pushes are not** — stop and ask the owner before pushing.
- Rebuild the Windows artifact through `desktop_shell/build_release.bat` and
  report the Build Manifest (`dist/ldcc-build.json`). The pipeline gates in
  order: offline suite → `check_deployment_policy.py` → archive previous exe →
  PyInstaller → manifest → windowed-launch smoke. Report the stage you reached
  if it fails.
- `dist/archive/` is the rollback target (`rollback_release.bat`).

### Known blocker at gate 6 (found 2026-10-03, pre-existing)

Gates 1–5 pass; gate 6 (windowed-launch smoke) fails because the app hangs
before rendering. Root cause is already isolated — do not re-derive it:

- The hang is `desktop_shell/et_ui.py:37`, `ttk.LabelFrame(parent,
  text="👽 Talk with E.T. — live voice conversation practice")`, reached from
  `app.py` in `run()`. The process shows as *Not Responding*, window title `N/A`.
- Minimal reproduction: `ttk.LabelFrame(root, text="plain ascii label")` is
  fine; `ttk.LabelFrame(root, text="\U0001F47D …")` hangs Tcl. On this machine's
  Tcl-Tk 8.6, a **non-BMP (astral-plane) character in a widget `text=` option
  hangs the interpreter**.
- It reproduces on `main` without this sprint's changes, so it is not a
  regression. 66 non-BMP characters exist across `desktop_shell/*.py` and
  `engines/language-lab/et_persona.py`; `et_ui.py:37` is merely the first one
  reached.

**Your task here is to confirm the diagnosis and then escalate, not to invent a
fix.** Confirm by running the two-line minimal reproduction above. Then report
to the owner with both candidate fixes and their trade-offs: (a) strip or
transliterate astral-plane characters from widget `text=` options — small and
contained, but changes visible UI copy; (b) move the build to a Tcl/Tk version
that handles surrogate pairs (8.7/9) — no copy change, but a toolchain change
that touches the packaging baseline. Do not pick one silently; `CONSTITUTION.md`
§3 requires the owner to choose.

Note also: if you run the pipeline under an agent sandbox, stage [1/6] can
false-fail with the suite fully green because the sandbox's delete guard trips
on pytest's `tmp_path` garbage collection. Verify the suite's real exit code
(`python -m pytest -q; echo $?`) before believing a gate-1 failure.

## Phase 6 — Report

Report in the repository's register: findings first, then mechanism, then
evidence. Use a table for per-item results. Include, without exception:

1. The exact commands you ran and their measured output (test counts, timings,
   model ids).
2. Which claims are **verified** (you ran it and saw it) versus **reasoned**
   (you inferred it).
3. Anything that failed, regressed, or remains unknown.
4. The `AGENT_LOG.md` entry you appended.
5. Confirmation that nothing temporary was left behind
   (`CONSTITUTION.md` §1.2).

## Hard constraints

- **Additive only.** If your change makes any existing option unreachable, you
  have failed the sprint. `scan_local_endpoints`, `LmStudioClient`,
  `list_available_models`, `check_model_health`, and the `no_model` error kind
  all keep their current names and behaviour.
- **Standard library only** for the new code, beyond what `requirements.txt`
  already pins. No new dependencies.
- Python 3.10+ compatible; fully typed; no commentary outside docstrings.
- **No credentials, tokens, or API keys** in code or commits
  (`CONSTITUTION.md` §3).
- **No temp files.** Anything transient lives in a git-ignored `/tmp` and is
  deleted before you finish.
- Every new file gets a one-line reason in `FILE_MANIFEST.md` **when it is
  created**, not at the end.
- If a spec here is ambiguous, **stop and ask** — do not ship a plausible
  guess (`CONSTITUTION.md` §3).
- Do not edit `CONSTITUTION.md` to make your own task easier (§5).

## Definition of done

Works; has tests or a documented manual verification step; `AGENT_LOG.md` has
an entry; `FILE_MANIFEST.md` is current; nothing temporary left behind; the full
offline suite is green; and the live verification in Phase 3 was actually run,
with its real numbers reported — including any part that did not pass.
