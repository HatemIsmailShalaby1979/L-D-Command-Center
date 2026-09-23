# L&D Command Center

> **Status: Working — verified 2026-09-23 / unfrozen 2026-09-24 (App Owner / Solo Engineer).**
>
> Endpoint auto-detect active (ollama 11434 / LM Studio 1234). Quality guard + humor layer live. Frozen sections correct; Language Lab, Career, Playground unfrozen. E2E smoke report passed. Rollback path: `dist/archive`.

> Built solo, self-learning, while switching careers. No team. No funding. Just a local-first system that refuses to forget what it learns. Every endpoint is verified against real model outputs; every section has a freeze/unfreeze policy; every rollback points to `dist/archive`.

> This is part of the Helix Codex family of solo-built systems. It does not claim to replace a corporate L&D platform. It claims to do one thing well: run locally, test honestly, and keep the evidence.

---

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

### Launch

Use `RUN_LDCC.bat` (double-click or `cmd.exe`) for the correct interpreter selection. The batch probes `.venv`, Python 3.12/3.13/3.11/3.10, and requires `tkinter` + `httpx` to boot cleanly.

### Features

- **Language Lab**: 30 curated lesson packs (Spanish, Japanese, German) with audio, flashcards, grammar drills
- **E.T. Conversation**: Live voice chat with Mr. & Mrs. E.T. (persona-driven, mic input, accent feedback)
- **Level Exams**: A1–C1 inclusive final tests with recommendations
- **Career Development**: Resume builder, GitHub/LinkedIn import, job search, cover letters, interview prep
- **Skills Arena**: Reading, writing, listening practice with your own files
- **Placement Quiz**: 12-item adaptive placement test (A1–B1)

### Requirements

- LM Studio at `http://localhost:1234/v1` with a model loaded (e.g., `google/gemma-4-12b-qat`)
- Python 3.10+ with packages from `requirements.txt`
- Windows 10/11

