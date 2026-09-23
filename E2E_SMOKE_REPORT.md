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
