<div align="center">

# L&D Command Center

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
- `model-layer/client.py` — local server discovery and the inference clients.

## Inference backends

One local model is the sole generation brain. Which runtime hosts it is the
user's choice, and the app detects it rather than assuming:

| Backend | Default endpoint | Detection | Model listing | Probe |
|---|---|---|---|---|
| Ollama | `http://localhost:11434/v1` | `/api/tags` + `/v1/models` | `/v1/models`, falling back to native `/api/tags` | Yes |
| LM Studio | `http://localhost:1234/v1` | `/v1/models` | `/v1/models` | Yes |
| Any OpenAI-compatible server | port 8080 / 5000, or `OLLAMA_HOST` | `/v1/models` | `/v1/models` | Yes |

Both runtimes speak the OpenAI chat-completions protocol, so generation,
the Guardrail Loop, the model policy levers, and the capability probe are
identical whichever one is running. On startup the app probes localhost,
fills the **Server** dropdown with every runtime that answered, fills the
**Model** dropdown from the selected server's own listing, and probes the
chosen model on demand. `OLLAMA_HOST` is honoured when Ollama was moved
off its default port.

## Production status & test coverage

Stated plainly and dated. Last measured 2026-10-03; not re-measured since.

| Item | State | Evidence |
|---|---|---|
| Ollama auto-detect | Active | `discover_local_servers()` + `/api/tags` fallback; `model-layer/test_client.py` |
| LM Studio auto-detect | Active | Port 1234, `scan_local_endpoints` unchanged |
| Server + model pickers | Active | `desktop_shell/app.py` header dropdowns |
| Capability probe (both runtimes) | Active | `probe_model_capabilities` records provider + endpoint |
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

Requires Python 3.10+ and one local inference server with a model loaded —
Ollama at `http://localhost:11434/v1` (e.g. `granite4.2:latest`) or LM Studio
at `http://localhost:1234/v1` (e.g. `google/gemma-4-12b-qat`) — plus
`tkinter` and `httpx` to boot cleanly. Start whichever you prefer; the app
detects it and lists its models in the Model dropdown.

## Related work

- [Full portfolio](https://github.com/HatemIsmailShalaby1979/HatemIsmailShalaby1979) — how this project fits the wider work
- [Release notes](./RELEASE_NOTE_2026_10_03.md) — what changed in the Ollama endpoint release

## Author

Built by Hatem Ismail Shalaby, Contact Centre Operations & AI Implementation Lead | WFM & CX Transformation. Background: https://github.com/HatemIsmailShalaby1979

## Licence

MIT

---
UPDATE 2026-10-03 — Ollama is a first-class inference backend: local servers are discovered (`discover_local_servers`), their models fill a new Server + Model picker pair in the shell, and the capability probe grades and attributes either runtime (Ollama or LM Studio). Additive only — `LmStudioClient` and `scan_local_endpoints` are unchanged and pinned by regression tests. Offline suite: 1114 passed / 7 live deselected. Release note: RELEASE_NOTE_2026_10_03.md.
