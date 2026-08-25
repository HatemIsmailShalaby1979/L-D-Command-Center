# L&D Command Center

A free, offline-first, desktop-only Learning & Development command center.
One local model (via LM Studio) powers every generation: learning journeys,
language-learning lesson packs with interactive drills, career development
with automatic job-board search, and a universal media playground — no cloud,
no subscription. See `MASTER_STORY.md` for the product vision and
`docs/PRODUCTION_PLAN.md` for the v1 ship plan.

## What it does

- **Learning Journeys** — generate interactive HTML lessons on any topic,
  quiz + evaluation, export to PDF/DOCX/PPTX/XLSX/TXT/audio.
- **Language Lab** — flagship lesson packs with two-voice dialogue, vocab
  flashcards, grammar drills, listening comprehension, evaluations, and
  spaced repetition. Interactive HTML renderer with in-browser grading.
- **Career Development** — resume generate/enhance with inspectable changes,
  upload existing PDF/DOCX/TXT, GitHub/LinkedIn connections. Automatic
  job-board search (Greenhouse, Ashby, RemoteOK) with keyword ranking,
  cover letter generation, and full application package preparation.
- **Playground** — media workspace (ffmpeg-based editing), import inbox,
  keyless connectors (Hugging Face Spaces, Pollinations, Figma).
- **Audio Studio** — audiobook narration, two-voice podcast generation.
- **Export** — any artifact to PDF, DOCX, TXT, PPTX, XLSX, or audio.

## Fresh-machine setup (E8)

1. Python **3.10+** (3.14 verified on Ubuntu 26.04 via uv).
2. Install [LM Studio](https://lmstudio.ai/), load a tool-calling-capable
   model (3B+ recommended; gemma-4-12B-it-QAT Q4_0 verified), start the
   local server (`http://localhost:1234/v1`).
3. `pip install -r requirements.txt` or `uv venv && uv pip install -r requirements.txt`
4. Optional audio: install `piper-tts`, then fetch voices while online:
   ```python
   from pathlib import Path
   from engines.audio_engine import provisioning
   for item in provisioning.missing_voices(models_dir=Path("models/tts")):
       provisioning.download_voice(item.voice_id, models_dir=Path("models/tts"))
   ```
5. Third-party credentials (GitHub/LinkedIn/YouTube/Figma) go in git-ignored
   `secrets/*.secrets` files as `KEY=VALUE` — see `storage/secrets.py`.
6. Job-board search is keyless (no credentials needed) — Greenhouse, Ashby,
   and RemoteOK public APIs are used directly.

## Run

```bash
python -m pytest                 # full offline suite, live tests deselected (E1)
./run_checks.sh                  # release gate: syntax + suite + 90% coverage floor
python desktop-shell/app.py      # launch the desktop app
```

## Layout & governance

- `engines/` — independently deletable subsystems (journey-core,
  export-engine, audio-engine, language-lab, career-engine, playground-bridge).
- `model-layer/` — LM Studio client, prompt registry, Generation Pipeline
  (the one Guardrail Loop), TTS.
- `storage/` — artifact persistence + the secrets adapter.
- `desktop-shell/` — thin Tkinter UI over the tested controller.
- Governance: `CONSTITUTION.md` (read first), `BOOT_ROOT.md`,
  `MASTER_STORY.md`, `CONTEXT.md` (domain glossary), `FILE_MANIFEST.md`
  (every file + reason), `TASKS.md` (claimable queue), `AGENT_LOG.md`.
