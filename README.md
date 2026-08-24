# L&D Command Center

A free, offline-first, desktop-only Learning & Development command center.
One local model (via LM Studio) powers every generation: learning journeys,
language-learning podcasts, resume work, and audio narration — no cloud, no
subscription. See `MASTER_STORY.md` for the product vision and
`docs/PRODUCTION_PLAN.md` for the v1 ship plan.

## Fresh-machine setup (E8)

1. Python **3.10+** (3.11 recommended).
2. Install [LM Studio](https://lmstudio.ai/), load a tool-calling-capable
   model (3B+), start the local server (`http://localhost:1234/v1`).
3. `pip install -r requirements.txt`
4. Optional audio: install `piper-tts`, then fetch voices while online:
   ```python
   from pathlib import Path
   from engines.audio_engine import provisioning
   for item in provisioning.missing_voices(models_dir=Path("models/tts")):
       provisioning.download_voice(item.voice_id, models_dir=Path("models/tts"))
   ```
5. Third-party credentials (GitHub/LinkedIn/YouTube) go in git-ignored
   `secrets/*.secrets` files as `KEY=VALUE` — see `storage/secrets.py`.

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
