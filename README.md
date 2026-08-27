# L&D Command Center

Desktop-first learning & development toolkit. One local model (LM Studio) powers everything — learning journeys, language labs, career tools, media playground. No cloud, no subscription.

## What's inside

**Learning Journeys** — Generate interactive HTML lessons on any topic. Quiz + evaluation. Export to PDF, DOCX, PPTX, XLSX, TXT, audio.

**Language Lab** — The flagship. Full lesson packs with two-voice dialogues, vocab flashcards, grammar drills, listening comprehension, spaced repetition. In-browser grading.

**Career Development** — Resume generation/enhancement with inspectable changes. Upload existing PDF/DOCX/TXT. GitHub/LinkedIn import. Auto job-board search (Greenhouse, Ashby, RemoteOK) with keyword ranking. Cover letters. Full application packages.

**Playground** — Media workspace (ffmpeg-based), import inbox, keyless connectors (Hugging Face Spaces, Pollinations, Figma).

**Audio Studio** — Audiobook narration, two-voice podcast generation.

**Export** — Any artifact to PDF, DOCX, TXT, PPTX, XLSX, or audio.

## Fresh machine setup

1. Python **3.10+** (tested on 3.14 via uv on Ubuntu 26.04)
2. Install [LM Studio](https://lmstudio.ai/), load a tool-calling model (3B+ — gemma-4-12B-it-QAT Q4_0 verified), start server at `http://localhost:1234/v1`
3. `pip install -r requirements.txt` or `uv venv && uv pip install -r requirements.txt`
4. Optional audio: `pip install piper-tts`, then fetch voices:

```python
from pathlib import Path
from engines.audio_engine import provisioning
for item in provisioning.missing_voices(models_dir=Path("models/tts")):
    provisioning.download_voice(item, models_dir=Path("models/tts"))
```

## Honest status

**V1 ship in progress.** Core engines work. Test suite: 730+ tests, 93.6% coverage. Some UI rough edges. Job board connectors need API keys for production use.

Download the latest release — it's a standalone executable.

## Why this exists

L&D tools are either expensive SaaS or disjointed scripts. I wanted one desktop app that does the whole loop: create content — deliver it — track it — help people get jobs. All local.

## Stack

- Python + LM Studio (local LLM)
- ffmpeg for media
- Piper TTS for audio
- pytest for confidence (730+ tests)

## Part of the ecosystem

Learning engine for [Helix Prime](https://github.com/HatemIsmailShalaby1979/Helix-Prime). Sibling to [Study Studio](https://github.com/HatemIsmailShalaby1979/Study-Studio) and [Helix Education](https://github.com/HatemIsmailShalaby1979/Helix-Education).

## License

MIT