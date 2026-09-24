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
  Audio length is determined by the segment's **word count** (TTS ~205
  WPM measured on Piper), never by the model-invented `duration_seconds`
  metadata alone.
- **Length Compliance** — the podcast length contract (2026-09-24,
  calibrated live on granite4.2): generation word-budgets content at
  `TARGET_SPEAKING_WPM` (200) for the requested minutes,
  `make_length_validator` rejects scripts below `MIN_CONTENT_WPM ×
  tolerance` (100×0.9 = 90 WPM — lowered from 170×0.9 after 12-min
  podcasts plateaued at 1083–1597 words and failed every time),
  and both the controller and the immersion path re-render once at
  ≤0.70× speed if actual audio is under 92% of target. Audiobook
  duration excludes the 44-byte WAV header. The validator is a
  borrowed constraint, not a wall — degraded models still pass and
  the UI shows actual vs target length honestly.
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
- **Career Identity** — the app's memory of the user's accounts (2026-09-05):
  GitHub username + imported projects, LinkedIn basics, last target role.
  Persisted in the `career_identity` preference; connections survive
  restarts and offline days (cached data serves when a network fetch
  fails); cleared only by explicit user action.
- **LinkedIn Post Draft** — a human-sounding first-person post grounded in
  the Resume, deterministically validated (word budget, banned AI-tell
  phrases, hashtag cap), always saved locally first. **Publishing** is a
  separate flow with an explicit confirm gate — nothing ever posts without
  the human's deliberate confirmation.
- **Campaign** (Campaign tier) — the apply-tracking pipeline: every
  prepared application becomes a tracked record that advances along the
  **Status Ladder** (prepared → submitted → screening → interviewing →
  offer → rejected | withdrawn). Tracking and the dashboard are free on
  every tier; the advance tooling and **Interview Prep** (per-listing
  likely questions + a story bank grounded in the real resume +
  questions to ask) are the Campaign-tier features. The user's own
  history is never paywalled (PROFIT_PLAN §7).
- **Flagship Pack** — one of the 30 curated marketing artifacts (10 stable-
  keyed topics × es/ja/de): generated from the flagship catalog, footered
  with the app credit, shared as a landing page. Batch-generated by
  `flagship_batch` (idempotent — keys never drift so shared links keep
  working).

## Language Lab flagship (Pillar 2, Phase 7 + Project E.T. 2026-09-06)

- **LessonPack** — one validated generation per (topic, target language,
  level): two-voice dialogue Segments, vocab cards (term/reading/
  translation/example), grammar cards with drills, and mixed evaluation
  items. The Language Lab's core artifact; rendered to interactive HTML
  by LanguageLabRenderer.
- **Evaluation Item** — one gradable question inside a LessonPack:
  multiple_choice, fill_in_blank, translation, or transformation.
  Grading is deterministic-first; the model judge is fallback only.
- **E.T.** — the alien conversation partner (Project E.T.). Two
  personas: **Mr. E.T.** (male voice, explorer humor) and **Mrs. E.T.**
  (female voice, sharper wit). A live voice/typed conversation where
  each turn is transcribed (STT), evaluated (grammar/vocabulary/
  structure/relevance 1-5), and answered in-character by the local
  model, spoken through the persona's voice. Unclear audio triggers a
  kind re-ask that consumes nothing. Free tier: 10 turns/week;
  unlimited is the Pro headline.
- **Scenario** — one of 33 curated conversation situations (10 everyday
  domains × 3 contexts, plus mock job interview / support-call
  roleplay / free talk), each in short/medium/long lengths.
- **Curriculum Slot** — one cell of the ready-made catalogue:
  `<level>-<domain>` (e.g. b1-work_school), 6 per level, 30 per
  language, deterministic keys forever. Status ladder:
  todo → generated → done (done never downgrades).
- **Curriculum Library** — the A1..C1 catalogue per language (C2 ships
  as an honest locked "coming soon" badge), ten everyday-life domains,
  instant browsing for all 15 languages, generation on demand.
- **Level Exam** — the inclusive final test per level: vocabulary,
  grammar, reading, writing, listening (audio rendered), speaking
  (voice or typed), 70% to pass. Produces per-section scores,
  per-skill band estimates, and recommendations pointing at real
  curriculum slots.
- **Placement Quiz** — the 10-minute front door: 12 escalating items
  (A1→B1), deterministic grading, honest banding, and a
  recommended-first-slot pointer into the library.
- **Skills Arena** — the Playground's four-skills practice area:
  Reading packs from imported documents, Writing evaluation with a
  corrected version, Listening packs from imported audio (STT +
  questions); Speaking lives with E.T. The legacy media canvas and
  Connector Hub stay untouched below it.

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
- **Model Policy** — the injected skills tier (2026-09-05, hardened
  2026-09-24): the JSON discipline addendum appended to every system
  prompt, response_format JSON-mode with runtime-rejection fallback,
  thinking suppression (`reasoning_effort=none` with the same
  capability-mismatch fallback — reasoning models must not burn the
  token budget on chain-of-thought), and the size-aware attempt budget
  (<7B models get more retries, never a failure wall). Lives in
  model-layer/policy.py.
- **Truncation Repair** — when the model hits the token limit mid-JSON
  (finish_reason == 'length'), the extractor salvages every complete
  member and closes the structure instead of failing the attempt. If
  salvage fails, the pipeline DOUBLES `max_tokens` for the retry
  (up to `MAX_TOKENS_CEILING` = 32768) and feeds completeness-oriented
  feedback — concision advice appears only once the ceiling is reached.
  The "unaccepted format" wall for 7B-14B models is closed by repair +
  escalation + the 8192-token starting budget.
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
- **Frozen Section** — a UI surface whose GENERATION is disabled because
  another portfolio app owns the feature (Journey topic generation and
  Audio Studio generation are frozen as of 2026-09-05; Study Studio ships
  them). Frozen tabs keep browsing/exporting existing artifacts; the
  banner names the owning app.
- **Release Pipeline** — the gated path from source to a verifiable Windows
  artifact (2026-09-13, `desktop_shell/build_release.bat`): offline suite →
  policy gate → archive previous exe → PyInstaller build → Build Manifest →
  windowed-launch smoke gate. Fail-fast, one command, mirrored in CI
  (`windows-build.yml`); **Release** adds a human `environment: release`
  approval gate before publishing. Any earlier build is one command away
  via **Rollback** (`rollback_release.bat` restores the newest
  `dist/archive/ldcc-<ts>.exe`).
- **Build Manifest** — the observability record written next to the artifact
  (`dist/ldcc-build.json` + one-line `ldcc-build.txt`): sha256, bytes, build
  UTC, python/PyInstaller versions, `ldcc.spec` sha, upstream commit. The
  primary way to tell which build a machine is running.
- **Policy Gate** — the mechanical secrets guard in the Release Pipeline
  (`desktop_shell/check_deployment_policy.py`): forbidden names
  (`secrets/`, `models/`, `.env`, `*.secrets`, `.onnx`, `.gguf`, `.bin`) in
  the staged tree or as spec `datas`/`binaries` references abort the
  release. The bundle is offline-first but never carries credentials or
  voice-model weights; standalone voice ships as an opt-in download.

---
UPDATE 2026-09-24 — Podcast/audiobook length compliance: word-budget validation + prompt budget + stretch re-render in controller AND immersion path (Segment/Length Compliance above). Live e2e: granite4.2 via ollama generated a 1-min podcast at 143s actual (LENGTH_OK). Endpoint auto-detect (ollama/LM Studio) applied; quality guard (non-robotic + humor/tips) active; e2e smoke report: E2E_SMOKE_REPORT.md. Release judgment: small boring change shipped; rollback via previous archive in build/.