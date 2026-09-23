# Project notes — L&D Command Center

## Running the app
- Always launch with `RUN_LDCC.bat` (double-click, or from cmd.exe).
  **Never** run the python entry point from PowerShell — it injects null bytes
  into argv and Python dies with
  `ValueError: source code string cannot contain null bytes`.
- Interpreter with the deps installed:
  `C:\Users\Thomas\AppData\Local\Programs\Python\Python312\python.exe`
  A bare `python` may resolve to an unrelated install with no deps; the
  launchers probe for a working interpreter for this reason.

## Conventions
- Engine dirs are **hyphenated** (`engines/language-lab`) and cannot be
  imported directly. `conftest.py` and `desktop_shell/app.py` register
  underscore aliases (`engines.language_lab`). Any new script that imports
  engines must `import conftest` (or replicate the alias block) first.
- Python package dir is `desktop_shell` (underscore). Hyphenated variants in
  scripts/config are wrong and have caused silent failures before
  (`pytest.ini` testpaths, `run-app.bat`).

## Test baseline
- Offline gate: `run_checks.bat` (Windows) / `run_checks.sh` (bash) ->
  285 files compile, **1041 passed, 7 deselected**, coverage 92% (floor 90).
- Live: `python -m pytest -m live` (needs LM Studio). **Not a reliable gate** —
  ~2 of 7 fail per run and it is a different 2 each time (schema drift +
  token-limit truncation from the local model). Use it as a smoke check only.
- Pin a model with `LDCC_LIVE_MODEL=google/gemma-4-12b-qat`; selection logic
  lives in `conftest.select_live_model`.

## Export determinism (exit criterion E4)
All OOXML exports must be byte-identical across runs. Wall-clock metadata leaks
in two ways: ZIP member timestamps (every library stamps at save time) and
`docProps/core.xml` `dcterms:modified` (openpyxl writes it regardless of what
the caller pinned). Both are handled by
`engines/export-engine/zip_stability.py::stabilize_zip` — route any new OOXML
export through it instead of hand-rolling a normalizer.

## Frozen features
Journey topic generation and Audio Studio are frozen by owner directive
(2026-09-05); those tabs stay visible for browsing/export but their generate
buttons are disabled.
