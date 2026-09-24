# L&D Command Center

**Status: working, V1 ship in progress. Snapshot 2026-09-23.**

Verified on 2026-09-23: endpoint auto-detect is active (Ollama 11434 / LM Studio 1234), the quality guard and humor/tips layer are live, the E2E smoke report passed, and the rollback path is `dist/archive`. Not verified: no external audit, no client deployment, and no revenue.

L&D Command Center is a component of **Helix Codex**, the accountable AI operating organization. It is a desktop learning, language, and career workstation that runs on the user's own machine.

## Release status, snapshot 2026-09-23

| Item | State | Evidence |
|---|---|---|
| Endpoint auto-detect | Active | Ollama 11434 / LM Studio 1234 |
| Quality guard + humor/tips layer | Active | `model-layer/quality_guard.py` |
| Frozen sections | Correct | Journey and Audio |
| Unfrozen sections | In progress | Language Lab, Career, Playground |
| E2E smoke | Passed | `E2E_SMOKE_REPORT.md` |
| Policy gate | Pass | Rollback restores a previous archive from `dist/archive` |
| Changelog | Current | `AGENT_LOG.md`, `INVESTIGATOR_NOTE_PHASE1.md` |

Every row above is dated 2026-09-23 and has not been re-measured since.

## Quick start

### Prerequisites

- Python 3.10+
- LM Studio running at `http://localhost:1234/v1` with a compatible model loaded (for example `google/gemma-4-12b-qat`)
- Windows 10/11

### Running the app

**Do not run the app from PowerShell.** A PowerShell limitation injects null bytes into Python command arguments. Use one of the methods below instead.

#### Method 1: the launcher (recommended)

```cmd
RUN_LDCC.bat
```

Double-click `RUN_LDCC.bat` in Windows Explorer.

#### Method 2: Command Prompt (cmd.exe)

```cmd
cd /d E:\LD_Command_Center
python -c "import sys; sys.path.insert(0, r'E:\LD_Command_Center'); import desktop_shell.app as app; app.run()"
```

#### Method 3: the PyInstaller executable

```cmd
dist\ldcc.exe
```

#### Method 4: direct Python execution (from cmd.exe, not PowerShell)

```cmd
cd /d E:\LD_Command_Center
python -c "import sys; sys.path.insert(0, r'E:\LD_Command_Center'); import desktop_shell.app as app; app.run()"
```

### Launch notes

Use `RUN_LDCC.bat` for interpreter selection. The batch probes `.venv` and Python 3.12/3.13/3.11/3.10, and requires `tkinter` and `httpx` to boot cleanly.

## Features

- **Language Lab**: 30 curated lesson packs (Spanish, Japanese, German) with audio, flashcards, and grammar drills
- **E.T. Conversation**: voice chat with Mr. & Mrs. E.T., persona-driven, with microphone input and accent feedback
- **Level Exams**: A1 to C1 final tests with recommendations
- **Career Development**: resume builder, GitHub and LinkedIn import, job search, cover letters, and interview prep
- **Skills Arena**: reading, writing, and listening practice built from the user's own files
- **Placement Quiz**: 12-item adaptive placement test (A1 to B1)

Feature counts above are as of 2026-09-23.

## Requirements

- LM Studio at `http://localhost:1234/v1` with a model loaded (for example `google/gemma-4-12b-qat`)
- Python 3.10+ with the packages listed in `requirements.txt`
- Windows 10/11

## Honest boundary

L&D Command Center does not replace a corporate learning and development platform, and it is not a production deployment. The Language Lab, Career, and Playground sections are unfrozen and still changing. The E2E smoke report records one pass, not a continuous suite. There is no external audit of the endpoint handling.

This is not a production deployment claim. There is no external audit, no certified data isolation, and no signed security review. No revenue has been realised.

## The founder's story

I spent twenty-eight years in operations. The first fourteen were the
foundation: ground operations and real-time traffic management at Hurghada
International Airport, then Air Berlin, where I directed ground operations
through the 2011 regional transition and held SLA compliance under conditions
that had no playbook. Alongside that, international logistics at Shorouk
International Bookshop and hybrid IT operations at Nefertari American School.

The second fourteen were about automation. I built AI-driven automation for
contact centres at ByteDance, Vodafone and Uber: NLP pipelines that turn
unstructured customer language into signal, Erlang C forecasting that turns
volume into staffing, and the reporting layers that made both usable by people
on the floor. The hard part was never the model. It was the handover — who owns
the decision, what evidence supports it, and what happens when the system is
wrong.

In April 2026 I left that career and started building full time — alone, and
teaching myself to write software as I went. The first four tools were published
six weeks later, in May and June 2026. Each one took a single operational problem
and solved it properly. They were not impressive. They were correct.

Those four tools converged into one idea: **Helix Codex**, an accountable AI
operating organization. Not an autonomous agent. An organization with a
constitution, named roles with bounded authority, evidence trails, and a human at
every consequential boundary. Helix Prime is its operations core.

L&D Command Center is a component of Helix Codex. It is maintained by one person, with no team and
no funding. It has not been externally audited and it has not made revenue. Where
it is unfinished, this document says so.

## Related work

- [Helix Prime](https://github.com/HatemIsmailShalaby1979/Helix-Prime) — the operations core
- [Helix Education](https://github.com/HatemIsmailShalaby1979/Helix-Education) — event-sourced learning engine
- [Study Studio](https://github.com/HatemIsmailShalaby1979/Study-Studio) — local-first AI tutor
- [Blue Waves](https://github.com/HatemIsmailShalaby1979/Blue-Waves-) — content studio
- [LIVE Support Assistant](https://github.com/HatemIsmailShalaby1979/LIVE-Support-Assistant) — explainable support prototype
- [Full portfolio](https://github.com/HatemIsmailShalaby1979) — the front door

### The 2026 building attempts

- [WFM Forecasting Calculator](https://github.com/HatemIsmailShalaby1979/wfm-forecasting-calculator)
- [RTA Command Center](https://github.com/HatemIsmailShalaby1979/RTA_command_center)
- [CX Sentiment Sentinel](https://github.com/HatemIsmailShalaby1979/cx-sentiment-sentinel)
- [Dynamic Ops Automation Engine](https://github.com/HatemIsmailShalaby1979/Dynamic-Ops-Automation-Engine)

## Author

**Hatem Ismail Shalaby** — Operations Architect · AI Systems Engineer · Founder

- GitHub: [HatemIsmailShalaby1979](https://github.com/HatemIsmailShalaby1979)
- LinkedIn: [hatem-shalaby-202902127](https://www.linkedin.com/in/hatem-shalaby-202902127/)
- Email: hatemshalaby2025@gmail.com
- Education: BSc Managerial Sciences (Computer Section), Sadat Academy for Management Sciences; Business Analytics Nanodegree, Udacity

Based in Al Obour City, Al-Qalyubia Governorate, Egypt.

## Licence

MIT
