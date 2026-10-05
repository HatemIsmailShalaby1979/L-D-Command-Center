<div align="center">

# L&D Command Center


<!-- badges:start -->

[![CI](https://github.com/HatemIsmailShalaby1979/L-D-Command-Center/actions/workflows/Python%20application/badge.svg)](https://github.com/HatemIsmailShalaby1979/L-D-Command-Center/actions)
![licence](https://img.shields.io/badge/licence-MIT-blue)
[![last commit](https://img.shields.io/github/last-commit/HatemIsmailShalaby1979/L-D-Command-Center)](https://github.com/HatemIsmailShalaby1979/L-D-Command-Center/commits/main)
![status](https://img.shields.io/badge/ci-success-brightgreen?label=success%20(2026-10-05))

*Measured 2026-10-06 — CI **success**; head `2002afe` (2026-10-05); Python.*

<!-- No static test or coverage count is shown here: a frozen
     number decays silently. Run the suite for a current figure;
     the CI badge above is the live status. -->
<!-- badges:end -->

**A desktop learning, language, and career workstation that runs on your machine.**

![Status](https://img.shields.io/badge/status-V1%20ship%20in%20progress-yellow)
![Licence](https://img.shields.io/badge/licence-MIT-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-3776ab)

</div>

## One-line identity

L&D Command Center is a desktop learning, language, and career workstation that runs
on the user's own machine — a tool for building skills, not a platform that manages
people.

> [!NOTE]
> **Operating principle.** A workstation should do one thing per screen and never pretend to be a platform. The parts that are frozen are frozen for a reason; the parts still moving say so. A language-lab drill and a resume builder are different jobs and are built as different, named sections rather than one dashboard pretending to be a system of record.

## What it does

- **Language Lab**: 30 curated lesson packs (Spanish, Japanese, German) with audio, flashcards, and grammar drills.
- **E.T. Conversation**: voice chat with persona-driven tutors, microphone input and accent feedback.
- **Level Exams**: A1 to C1 final tests with recommendations.
- **Career Development**: resume builder, GitHub and LinkedIn import, job search, cover letters, interview prep.
- **Skills Arena**: reading, writing, listening practice built from the user's own files.
- **Placement Quiz**: 12-item adaptive placement test (A1 to B1).

Feature counts above are as of 2026-09-23.

## How it fits Helix Codex

L&D Command Center is a **component** — a desktop learning, language, and career
workstation. It is an **independent repository with no shared codebase** with Helix
Prime. No data pipeline is wired to the core today. It is portfolio-adjacent and
technically independent.

## Architecture

- `desktop_shell/app.py` — the PyWebView shell entry point.
- `model-layer/quality_guard.py` — the quality guard and humor/tips layer.
- Section modules — Language Lab, Career, Playground, Audio, Journey, each with its own frozen/unfrozen state.
- `dist/archive` — the rollback target for the policy gate.
- Endpoint auto-detect for Ollama (`11434`) / LM Studio (`1234`).

## Production status & test coverage

Stated plainly and dated. Last measured 2026-09-23; not re-measured since.

| Item | State | Evidence |
|---|---|---|
| Endpoint auto-detect | Active | Ollama 11434 / LM Studio 1234 |
| Quality guard + humor/tips layer | Active | `model-layer/quality_guard.py` |
| Frozen sections | Correct | Journey and Audio |
| Unfrozen sections | In progress | Language Lab, Career, Playground |
| E2E smoke | **Mixed** — see below | `E2E_SMOKE_REPORT.md` |
| Policy gate | Pass | Rollback restores a previous archive from `dist/archive` |

> [!WARNING]
> What the E2E smoke run actually recorded (one run, not a continuous suite): endpoint and client auto-scan, pipeline policy, and export layers PASS. The UI window launch was **BLOCKED** by a tkinter Tcl environment problem. Direct generation **TIMEOUT** at 60 s on that hardware. Audio/Journey/Studio were **FROZEN BY DESIGN**, not broken. GitHub/LinkedIn connection was **UNVERIFIED** in that session. No external audit, no certified data isolation, no signed security review, no revenue. The pricing tiers on `index.html` are a plan, not an offer: no payment path, no account system, no customer.

## Run it

Do not run from PowerShell (a PowerShell limitation injects null bytes into Python
arguments). Use the launcher or cmd.exe.

```cmd
RUN_LDCC.bat
```

or from cmd.exe:

```cmd
cd /d E:\LD_Command_Center
python -c "import sys; sys.path.insert(0, r'E:\LD_Command_Center'); import desktop_shell.app as app; app.run()"
```

Requires Python 3.10+, LM Studio at `http://localhost:1234/v1` with a model loaded
(e.g. `google/gemma-4-12b-qat`), and `tkinter` + `httpx` to boot cleanly.

## Related work

- [Full portfolio](https://github.com/HatemIsmailShalaby1979/HatemIsmailShalaby1979) — how this project fits the wider work

## Author

Built by Hatem Ismail Shalaby, Contact Centre Operations & AI Implementation Lead | WFM & CX Transformation. Background: https://github.com/HatemIsmailShalaby1979

## Licence

MIT
