# CONTEXT.md — L&D Command Center Domain Glossary

Canonical names for the things this product talks about. Use these terms in
code, docs, tasks, and conversation. When a term sharpens or a new concept
earns a name, update this file in the same session (CONSTITUTION.md §2 log
applies). Source of truth for the vision itself is `MASTER_STORY.md`.

## Learning side (Pillar 1)

- **Journey** — a generated learning experience on one topic at one Level:
  topic, level, and an ordered list of Cards. The core artifact; flows into
  rendering, export, and audio.
- **Card** — one unit of a Journey: title, content, a Quiz question,
  Options, the Correct Option, and an Explanation.
- **Quiz / Evaluation** — the check-yourself step on a Card; correctness is
  a right/wrong problem, so it is validated, never trusted.
- **Level** — beginner | intermediate | advanced.
- **SOP** — a captured, reusable procedure extracted from Journey content
  and stored in Notion (opt-in). Not yet implemented.

## Language Lab (Pillar 2)

- **Bilingual Pair** — a lesson as sentence-level pairs: each Segment has a
  target-language sentence and its faithful translation in the known
  language. Translation accuracy is a *correctness* problem (CONSTITUTION §3).
- **Immersion Podcast** — the same lesson/level rendered entirely in the
  target language with two voices; no translation track.
- **Podcast Script** — ordered Segments (intro/monologue/dialogue/conclusion)
  assigned to named Speakers.
- **Segment** — one spoken turn: speaker, content, estimated duration.
- **Speaker / Voice** — a script Speaker maps to exactly one TTS Voice;
  distinct Speakers get distinct Voices.

## Career side (Pillar 3)

- **Resume** — structured CV data: contact, summary, experience[],
  education[], skills[], projects[].
- **Enhancement** — a model rewrite of a Resume toward a target role,
  returned together with a human-inspectable changes list (field, change,
  reason) per CONSTITUTION §3.
- **Confidence Flag** — parser output marking how surely a Resume field was
  extracted from an uploaded file (high/medium/low/unknown); gaps are shown,
  never invented.

## Platform concepts

- **Model Layer** — the guardrail tier: LM Studio client, prompt templates,
  schema validation, retry logic. Correctness comes from here, not model size.
- **Generation Pipeline** — the single deep module in the Model Layer that
  owns the whole Guardrail Loop for every artifact type; engines register a
  template + validator, never hand-roll the loop.
- **Voice Catalog** — the one table mapping (language, role) to a concrete
  TTS voice; Narration and podcast rendering resolve voices only through it.
- **Guardrail Loop** — render prompt → call model → extract JSON → validate
  against schema → retry with feedback → typed error. The mandated shape for
  every generation.
- **Engine** — one independently deletable/rebuildable subsystem under
  `/engines/` (journey-core, export-engine, audio-engine, language-lab,
  career-engine, playground-bridge), per BOOT_ROOT.md.
- **Narration** — plain text → single-voice audio (WAV + optional MP3).
- **Export** — deterministic conversion of an existing artifact (Journey,
  Resume) to txt/PDF/DOCX/PPTX/XLSX/audio. Export never calls the model;
  producing new content is generation, not export.
