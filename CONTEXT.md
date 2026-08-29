> **Internal development artifact** — documents the AI-assisted build process for this project.

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
- **Job Listing** — a unified record from keyless job boards (Greenhouse,
  Ashby, RemoteOK): company, title, location, URL, source, snippet.
- **Cover Letter** — a grounded, role-specific letter generated from a
  Resume and listing details; schema-validated (non-empty, mentions
  company).
- **Application Package** — the prepared bundle for one job: tailored
  resume (PDF + DOCX), cover letter (TXT), and listing reference (TXT),
  stored under `exports/applications/<company>-<role>/`.
- **Watchlist** — a saved job-search configuration (role, filters,
  company lists) plus a seen-URL set that enables diff-based polling:
  the agent checks periodically and reports only NEW listings.

## Language Lab flagship (Pillar 2, Phase 7)

- **LessonPack** — one validated generation per (topic, target language,
  level): two-voice dialogue Segments, vocab cards (term/reading/
  translation/example), grammar cards with drills, and mixed evaluation
  items. The Language Lab's core artifact; rendered to interactive HTML
  by LanguageLabRenderer.
- **Evaluation Item** — one gradable question inside a LessonPack:
  multiple_choice, fill_in_blank, translation, or transformation.
  Grading is deterministic-first; the model judge is fallback only.

## Playground (Pillar 4)

- **Media Workspace** — local ffmpeg-based editing core: pure plan
  functions (trim/concat/mix/overlay/scale/pad/convert) plus probe and
  ingest. Editing is offline; cloud only for generation.
- **Import Inbox** — a watch-folder: files dropped from any no-API
  service land as `media/<subkind>` Storage artifacts.
- **Connector Hub** — the single adapter seam to external generation
  services: `capabilities()` (file types, ops, quota notes, auth kind),
  `send(artifact, op) -> Job`, `poll(job) -> Result`. Keyless services
  before accounts. The Hub never learns individual vendors.
- **Capability Verdict** — the stored result of grading the loaded model
  against task profiles: per-task ready/degraded/failed plus review
  notes; surfaces in the shell health bar.

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
