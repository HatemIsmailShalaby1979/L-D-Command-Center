# L&D Command Center`n`n> **Built solo, self-learning, while switching careers. No team. No funding. Just a local-first system that refuses to forget what it learns.**`n`nA local-first Learning & Development command center with Language Lab, Career Development, and Skills Arena � governed, not promised. Every endpoint is verified against real model outputs; every section has a freeze/unfreeze policy; every rollback points to `dist/archive`.`n`nThis is part of the Helix Codex family of solo-built systems. It does not claim to replace a corporate L&D platform. It claims to do one thing well: run locally, test honestly, and keep the evidence.

## Release Status — 2026-09-23 (App Owner)
- Endpoint auto-detect (ollama 11434 / LM Studio 1234) active.
- Quality guard + humor/tips layer active (`model-layer/quality_guard.py`).
- Frozen sections correct (Journey/Audio); Language Lab, Career, Playground unfrozen.
- E2E smoke report: `E2E_SMOKE_REPORT.md`.
- Policy gate pass; rollback path: restore previous archive from `dist/archive`.
- Owner: this session; changelog in `AGENT_LOG.md` / `INVESTIGATOR_NOTE_PHASE1.md`.

## Quick Start

### Prerequisites
- Python 3.10+ 
- LM Studio running at `http://localhost:1234/v1` with a compatible model loaded (e.g., `google/gemma-4-12b-qat`)
- Windows 10/11

### Running the App

**IMPORTANT**: Due to a PowerShell limitation that injects null bytes into Python command arguments, **do not run the app from PowerShell**. Use one of these methods instead:

#### Method 1: Double-click the launcher (Recommended)
```cmd
RUN_LDCC.bat
```
Simply double-click `RUN_LDCC.bat` in Windows Explorer.

#### Method 2: Command Prompt (cmd.exe)
```cmd
cd /d E:\LD_Command_Center
python -c "import sys; sys.path.insert(0, r'E:\LD_Command_Center'); import desktop_shell.app as app; app.run()"
```

#### Method 3: Using the PyInstaller executable
```cmd
dist\ldcc.exe
```

#### Method 4: Direct Python execution (from cmd.exe, NOT PowerShell)
```cmd
cd /d E:\LD_Command_Center
python -c "import sys; sys.path.insert(0, r'E:\LD_Command_Center'); import desktop_shell.app as app; app.run()"
```

### ⚠️ IMPORTANT: Do NOT run from PowerShell
PowerShell injects null bytes into command-line arguments, causing `ValueError: source code string cannot contain null bytes` when Python tries to import modules. Always run from `cmd.exe` or double-click the `.bat` launcher.

### Features
- **Language Lab**: 30 curated lesson packs (Spanish, Japanese, German) with audio, flashcards, grammar drills
- **E.T. Conversation**: Live voice chat with Mr. & Mrs. E.T. (persona-driven, mic input, accent feedback)
- **Level Exams**: A1→C1 inclusive final tests with recommendations
- **Career Development**: Resume builder, GitHub/LinkedIn import, job search, cover letters, interview prep
- **Skills Arena**: Reading, writing, listening practice with your own files
- **Placement Quiz**: 12-item adaptive placement test (A1→B1)

### Requirements
- LM Studio at `http://localhost:1234/v1` with a model loaded (e.g., `google/gemma-4-12b-qat`)
- Python 3.10+ with packages from `requirements.txt`
- Windows 10/11

### Running Tests
```cmd
python -m pytest --tb=line -q
```
Expected offline result: 1041 passed, 7 live tests deselected (run the live
suite explicitly with `python -m pytest -m live` when LM Studio has a model
loaded).

> The 1041 total includes the 121 `desktop_shell` controller tests. Those were
> silently skipped until the `testpaths` entry in `pytest.ini` was corrected
> from `desktop-shell` (never existed) to `desktop_shell`.

### Full quality gate
```cmd
run_checks.bat            :: Windows (syntax gate + suite + 90% coverage floor)
run_checks.bat --no-pause :: same, for scripted/CI runs
bash run_checks.sh        :: Linux/macOS twin
```
`run_checks.bat` exists because `run_checks.sh` calls `python3`, which a stock
Windows install does not provide, so the documented gate could not run here.

### Live tests (require LM Studio)
```cmd
set LDCC_LIVE_MODEL=google/gemma-4-12b-qat
python -m pytest -m live
```
Model selection order is `LDCC_LIVE_MODEL` > a preferred-model list in
`conftest.py` > `list_models()[0]`. Pin the model explicitly: LM Studio's
ordering is arbitrary, and the first entry is often a small/uncensored model
that cannot hold the strict-JSON guardrail contract, which surfaces as
`could not extract JSON from model output` and looks like a product bug.

Even with a strong 12B model the live suite is **not reliably green**: roughly
2 of 7 fail per run, and it is a *different* 2 each time, from schema drift
(the model invents field names) and token-limit truncation. Treat the offline
suite as the real gate and the live suite as a smoke check. Select
`google/gemma-4-12b-qat` in the app's model picker for day-to-day generation.

### Building Executable
Build with the CPython 3.10 interpreter that has a complete Tcl/Tk (Python 3.12
on this machine ships a broken/unbundled Tcl and no PyInstaller), then PyInstaller
6.22.2 on the spec that self-stages the hyphenated engine dirs:
```cmd
cd /d E:\LD_Command_Center
"%LOCALAPPDATA%\Programs\Python\Python310\python.exe" -m PyInstaller desktop_shell\ldcc.spec --noconfirm
```
Output: `dist\ldcc.exe`

**Use `desktop_shell\build_release.bat` for any real ship.** It runs the same
build inside a full gated pipeline: offline suite → secrets policy gate →
archive previous build → PyInstaller → manifest (`dist\ldcc-build.json`) →
windowed-launch smoke gate. See `docs/DEPLOYMENT_PIPELINE.md` for stages,
rollback (`desktop_shell\rollback_release.bat`), verification protocol, and
CI (`windows-build.yml`, gated `release.yml`).

Debug tip: the console twin `desktop_shell\_ldcc_console.spec`
(`--distpath dist_console`) produces a console-attached exe that prints the real
traceback when a frozen app crashes — windowed builds only show PyInstaller's
"Unhandled exception in script" dialog.

### Troubleshooting
- **"No module named desktop_shell"**: Run from `E:\LD_Command_Center` directory or ensure `E:\LD_Command_Center` is in `PYTHONPATH`
- **"ValueError: source code string cannot contain null bytes"**: You're running from PowerShell. Use `cmd.exe` instead.
- **"No module named desktop_shell"**: Run from `E:\LD_Command_Center` directory or add it to `PYTHONPATH`
- **LM Studio connection failed**: Ensure LM Studio is running at `http://localhost:1234/v1` with a model loaded
- **Audio not working**: Install `piper-tts` and ensure Piper voices are in `models/tts/`

### License
MIT

---
UPDATE 2026-09-23 — Endpoint auto-detect (ollama/LM Studio) applied; quality guard (non-robotic + humor/tips) active; e2e smoke report: E2E_SMOKE_REPORT.md. Release judgment: small boring change shipped; rollback via previous archive in build/.
--- UI REDESIGN UPDATE 2026-09-23 ---
Dark interactive theme applied (dark background #0d1b2e, blue accent #76a9ff, scrollable canvas, interactive tabs). Humor/tips layer active (model-layer/quality_guard.py). Full experience requires running RUN_LDCC_FIXED.bat with TCLLIBRARY set.

