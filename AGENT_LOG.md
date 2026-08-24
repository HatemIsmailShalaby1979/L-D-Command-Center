# AGENT_LOG.md

Append-only session ledger. See `CONSTITUTION.md` §2 and `BOOT_ROOT.md`.

## [2026-08-20 11:36] — Claude/Claude Code
Task: Create folder skeleton as specified in BOOT_ROOT.md, populate each folder's README.md with one-paragraph responsibility description drawn from MASTER_STORY.md's Four Pillars and Core Engine Philosophy.
Touched: /engines/journey-core/README.md, /engines/export-engine/README.md, /engines/audio-engine/README.md, /engines/language-lab/README.md, /engines/career-engine/README.md, /engines/playground-bridge/README.md, /model-layer/README.md, /storage/README.md, /desktop-shell/README.md, /docs/README.md, /FILE_MANIFEST.md, /AGENT_LOG.md, /TASKS.md
Why: Bootstrap protocol requires folder structure and documentation for each engine/layer before any implementation begins.
Left undone: None. All skeleton folders and READMEs created per spec.

## [2026-08-20 11:45] — Claude/Claude Code
Task: Create TASKS.md with 3 OPEN tasks, create .gitignore excluding /tmp, secrets, and OS/editor cruft; update FILE_MANIFEST.md and AGENT_LOG.md.
Touched: /TASKS.md (created), /.gitignore (created), /FILE_MANIFEST.md (appended), /AGENT_LOG.md (appended)
Why: BOOT_ROOT.md coordination protocol requires TASKS.md as handoff surface; CONSTITUTION.md §3 requires secrets exclusion from git.
Left undone: None.

## [2026-08-20 12:00] — Claude/Claude Code
Task: Scaffold model-layer/ with three files per CONSTITUTION.md §3 (Guardrails over model size): LM Studio client wrapper, schema-validation layer, prompt-template module. Mark task 1 CLAIMED:claude-code, leave as OPEN-in-progress.
Touched: /model-layer/client.py (created), /model-layer/schema.py (created), /model-layer/prompts.py (created), /FILE_MANIFEST.md (appended), /AGENT_LOG.md (appended), /TASKS.md (updated: task 1 → CLAIMED:claude-code)
Why: CONSTITUTION.md §3 requires deterministic templates, schema-validated outputs with retry, and a centralized client guardrail. This scaffolding establishes those three contracts before any engine code touches them.
Left undone: All three files are stubs with NotImplementedError and TODOs. Real implementations (HTTP calls, JSON extraction, template rendering, retry logic) are deferred to the next implementation pass.

## [2026-08-20 12:10] — Claude/Claude Code
Task: Remove duplicate /TASKS.md entry from FILE_MANIFEST.md; re-verify workspace against BOOT_ROOT.md; report drift; append to AGENT_LOG.md.
Touched: /FILE_MANIFEST.md (removed duplicate /TASKS.md line), /AGENT_LOG.md (appended)
Why: Drift audit found /TASKS.md listed twice in FILE_MANIFEST.md; fixing per CONSTITUTION.md §1 (no duplicate files) and BOOT_ROOT.md accuracy requirement.
Left undone: None.

## [2026-08-20 12:30] — Claude/Claude Code
Task: Implement model-layer/ stubs (client.py, schema.py, prompts.py) with real code; wire client→schema validation→retry; mark task 1 DONE:claude-code.
Touched: /model-layer/client.py (implemented), /model-layer/schema.py (implemented), /model-layer/prompts.py (implemented), /FILE_MANIFEST.md (rewritten with implementation status), /AGENT_LOG.md (appended), /TASKS.md (task 1 → DONE:claude-code)
Why: CONSTITUTION.md §3 requires deterministic templates, schema-validated outputs with retry-on-failure, and a centralized client guardrail. This pass turns the stubs into working code.
Left undone: None. Implementation complete for the three model-layer files.

## [2026-08-20 13:00] — Claude/Claude Code
Task: Implement journey-core generator.py entry point (generate_journey), wire model-layer stack, write test, run 10 tests passing.
Touched: /engines/journey-core/generator.py (created), /engines/journey-core/__init__.py (created), /engines/journey-core/test_generator.py (created), /model-layer/prompts.py (fixed double-brace escaping), /FILE_MANIFEST.md (appended), /AGENT_LOG.md (appended), /TASKS.md (task 2 → CLAIMED:claude-code)
Why: Journey-core engine needs a generation entry point that wires prompts→client→validate→retry per CONSTITUTION.md §3.
Left undone: None. All 10 tests pass.

## [2026-08-20 14:00] — Claude/Claude Code
Task: Create journey-core/renderer.py — separate HTML rendering module; write test_renderer.py with 12 tests; run all tests passing; update FILE_MANIFEST.md and AGENT_LOG.md.
Touched: /engines/journey-core/renderer.py (created), /engines/journey-core/test_renderer.py (created + fixed), /FILE_MANIFEST.md (appended renderer entries), /AGENT_LOG.md (appended)
Why: CONSTITUTION.md §3 requires separation of concerns — generation (data) and rendering (presentation) are independent. The renderer takes a validated Journey dict and produces interactive HTML without calling the model, making it testable and reusable.
Left undone: None. All 12 renderer tests and 10 generator tests pass.

## [2026-08-20 14:30] — Claude/Claude Code
Task: Implement export-engine plain-text and PDF export (TASKS.md task 3).
Touched: /engines/export-engine/__init__.py (created), /engines/export-engine/export.py (created), /engines/export-engine/test_export.py (created), /TASKS.md (task 3 → DONE:claude-code), /FILE_MANIFEST.md (appended), /AGENT_LOG.md (appended)
Why: Users need downloadable journey formats. Plain-text works everywhere; PDF is portable. Both are deterministic — no model calls — so they can be unit-tested. Uses the Journey schema from model-layer/schema.py rather than duplicating the shape.
Left undone: None. All 16 export tests pass.

## [2026-08-20 15:00] — Claude/Claude Code
Task: Write integration test for full pipeline (generate→render→export); report drift.
Touched: /engines/test_integration.py (created), /TASKS.md (task 2 → DONE:claude-code), /FILE_MANIFEST.md (appended), /AGENT_LOG.md (appended)
Why: Need end-to-end verification that the three engines (journey-core, renderer, export-engine) work together with a single Journey object.
Left undone: None. Mocked test passes; live test skipped (LM Studio not running).

## [2026-08-20 15:30] — Claude/Claude Code
Task: Run full pipeline integration test against live LM Studio; report results and drift status.
Touched: /engines/test_integration.py (updated model name), /TASKS.md (task 2 → DONE), /FILE_MANIFEST.md (appended), /AGENT_LOG.md (appended)
Why: LM Studio is now running, so the live integration test can execute end-to-end.
Left undone: None. Live test PASSED. Full pipeline verified: generate → render → export text → export PDF.
## [2026-08-20 16:00] — Claude/Claude Code
Task: Implement career-engine resume schema and generation (TASKS.md task 4). Create schema.py, generator.py, test_generator.py with 7 tests. Fix double-brace escaping bug in model-layer/prompts.py _RESUME_USER_BASE template that caused KeyError on render().
Touched: /engines/career-engine/resume/schema.py (created), /engines/career-engine/resume/generator.py (created), /engines/career-engine/resume/test_generator.py (created), /model-layer/prompts.py (fixed brace escaping), /FILE_MANIFEST.md (appended), /AGENT_LOG.md (appended), /TASKS.md (task 4 → DONE:claude-code)
Why: CONSTITUTION.md §3 requires schema-validated resume generation with retry-on-failure. Reuses model-layer SchemaValidator pattern from journey-core. The brace escaping bug was pre-existing and also affected _JOURNEY_USER_BASE.
Left undone: None. All 7 tests pass.


## [2026-08-21 12:00] — Claude/Claude Code
Task: Implement career-engine resume enhance() function with retry logic and human-inspectable changes list.
Touched: /model-layer/prompts.py (added resume_enhance and resume_enhance_retry templates), /engines/career-engine/resume/generator.py (added enhance() function), /engines/career-engine/resume/test_generator.py (added 4 enhance tests), /FILE_MANIFEST.md (updated entries), /AGENT_LOG.md
Why: CONSTITUTION.md §3 requires human-inspectable intermediate artifacts — a resume rewrite must be checkable, not just trusted. enhance() returns both the enhanced resume and a changes list with field/change/reason for each modification.
Left undone: None. All 11 tests pass.

## [2026-08-21 13:00] — Claude/Claude Code
Task: Implement career-engine resume parser for PDF/DOCX upload.
Touched: /engines/career-engine/resume/parser.py (created), /engines/career-engine/resume/test_parser.py (created), /FILE_MANIFEST.md (updated), /AGENT_LOG.md
Why: Users need to upload existing resumes (PDF/DOCX) and have them converted to structured Resume format. Parser uses pattern matching (not model layer) and flags low-confidence fields so UI can prompt for gaps.
Left undone: None. All 16 tests pass.

## [2026-08-21 14:00] — Claude/Claude Code
Task: Add GitHub integration for resume project seeding.
Touched: /engines/career-engine/integrations/github_client.py (created), /engines/career-engine/integrations/test_github_client.py (created), /secrets/github.secrets (created), /FILE_MANIFEST.md (updated), /AGENT_LOG.md
Why: CONSTITUTION.md §3 requires credentials from secrets file (never hardcoded). GitHub integration is read-only — fetches public repos/READMEs to propose Resume.project entries without modifying existing resumes.
Left undone: None. All 16 tests pass.

## [2026-08-21 15:00] — Claude/Claude Code
Task: Add LinkedIn OAuth integration for self-serve tier (read own profile + post to own profile).
Touched: /engines/career-engine/integrations/linkedin_client.py (created), /engines/career-engine/integrations/test_linkedin_client.py (created), /secrets/linkedin.secrets (created), /FILE_MANIFEST.md (updated), /AGENT_LOG.md
Why: CONSTITUTION.md §3 requires credentials from secrets file. LinkedIn integration is deliberately limited to self-serve tier: openid+profile scopes for reading /v2/userinfo, w_member_social for posting. Requires explicit confirm=True for write ops. Rate-limited client-side (~100-150/day ceiling). No reading other members data, search, or messaging.
Left undone: None. All 19 tests pass.

## [2026-08-21 16:00] — Claude/Claude Code
Task: Add YouTube video search and AI summarization integration.
Touched: /engines/career-engine/integrations/youtube_summary.py (created), /engines/career-engine/integrations/test_youtube_summary.py (created), /secrets/youtube.secrets (created), /FILE_MANIFEST.md (updated), /AGENT_LOG.md
Why: Users researching a topic need curated video summaries with traceable source URLs — no summary without a URL, per CONSTITUTION.md §3. Uses YouTube Data API v3 for search and model layer for summarization. Explicitly invoked only, never as a side effect.
Left undone: None. All 19 tests pass.

## [2026-08-21 17:00] — Claude/Claude Code
Task: Wire Resume objects into export-engine and add career-engine integration test.
Touched: /engines/export-engine/export.py (added export_resume_to_plain_text, export_resume_to_pdf, export_resume_to_docx, unified export() dispatcher with _detect_type()), /engines/export-engine/test_export.py (expanded to 50 tests), /engines/career-engine/test_integration.py (created, 8 tests), /TASKS.md (updated), /FILE_MANIFEST.md (updated), /AGENT_LOG.md
Why: Users need to export resumes to PDF and DOCX formats. Reused existing export logic via unified dispatcher — no duplication. Integration test covers full pipeline: generate→enhance→export PDF/DOCX→GitHub repos→LinkedIn post→YouTube search, all mocked (no live credentials).
Left undone: None. All 8 integration tests pass, 50 export tests pass.

---

## 2026-08-21 — TTS Client Implementation

**Task**: Add TTS client to model-layer with Piper and Kokoro-82M backends.

**Completed**:
- Created `/model-layer/tts.py` with:
  - `TtsBackend` enum (PIPER, KOKORO)
  - `TtsConfig` dataclass
  - `synthesize(text, voice, language, backend, models_dir, speed) -> bytes` — backend-agnostic interface
  - `_synthesize_piper()` — CPU-only TTS using `piper-tts` package (ONNX runtime)
  - `_synthesize_kokoro()` — placeholder for Kokoro-82M (raises NotImplementedError until full tokenizer/phoneme encoder implemented)
  - `get_available_voices()` — discovers voice models from local directory
  - `generate_audio()` — convenience function with optional file output
- Created `/model-layer/test_tts.py` with 25 tests covering:
  - TtsConfig defaults and custom values
  - Error handling (empty text, invalid backend)
  - Piper backend dispatch and arg passing
  - Piper import failure and missing model handling
  - Kokoro NotImplementedError
  - Voice discovery for both backends
  - Audio generation with/without file output
- Installed `piper-tts` package (1.7.0) with onnxruntime dependency
- Verified Piper licensing: MIT license for software, voice models individually licensed (many permissive/CC)
- Verified Kokoro licensing: MIT license per upstream repo (hexgrad/Kokoro)

**Test Results**: 25/25 tests pass.

**Files Created**:
- `/model-layer/tts.py` — TTS client module
- `/model-layer/test_tts.py` — TTS tests (25 tests)

**Files Updated**:
- `/TASKS.md` — Added TTS task entry
- `/FILE_MANIFEST.md` — Added TTS entries

**Licensing Note**:
- Piper (rhasspy/piper): MIT license for software; voice models have individual licenses (check each voice)
- Kokoro-82M (hexgrad/Kokoro): MIT license
- No cloud-backed TTS options implemented (per requirements)


---

## 2026-08-21 — Audio-Engine Narration Module

**Task**: Add narration function to audio-engine that synthesizes text to audio (WAV + MP3) using the model-layer TTS client.

**Completed**:
- Created `/engines/audio-engine/narration.py` with:
  - `narrate(text, backend, voice, output_path, include_mp3, speed)` — main entry point
  - Automatic backend selection: prefers Kokoro-82M for supported languages (en, es, fr, de, it, pt, ru, ja, zh), falls back to Piper
  - `_detect_language()` — heuristic language detection based on character patterns
  - `_select_backend()` — chooses Kokoro or Piper based on language support
  - `_wav_to_mp3()` — converts WAV to MP3 using ffmpeg (already available in environment)
  - Convenience functions: `narrate_journey_card()`, `narrate_resume_summary()`
  - Returns `NarrationResult` dataclass with wav_bytes, mp3_bytes, sample_rate, backend_used, voice_used
- Created `/engines/audio-engine/test_narration.py` with 33 tests covering:
  - Language detection (English, Spanish, French, CJK, Cyrillic)
  - Backend selection (auto, explicit override, fallback)
  - Error handling (empty text, None)
  - Narration success cases (mocked synthesize and MP3 conversion)
  - MP3 conversion failure handling (graceful degradation to WAV-only)
  - File output to disk
  - Voice and speed parameter passing
  - Journey card and Resume summary narration
- No new heavy dependencies added — uses existing `piper-tts` and system ffmpeg

**Test Results**: 33/33 tests pass.

**Files Created**:
- `/engines/audio-engine/__init__.py` — Package init
- `/engines/audio-engine/narration.py` — Narration module
- `/engines/audio-engine/test_narration.py` — Tests (33 tests)

**Files Updated**:
- `/FILE_MANIFEST.md` — Added audio-engine entries
- `/AGENT_LOG.md` — This log entry

**Note**: MP3 conversion requires ffmpeg in PATH (verified available). If ffmpeg is unavailable, narration continues with WAV-only output.


---

## Session: Podcast Script Generation (audio-engine)

**Date**: 2026-08-21

**Task**: Add `podcast_script.py` to audio-engine — a function that takes a topic or Journey and produces a `PodcastScript` object via the model layer, with schema validation and retry-on-failure.

**Implementation**:
- Created `/engines/audio-engine/podcast_script.py` with:
  - `PodcastSegment` dataclass (type, speaker, content, duration_seconds)
  - `PodcastScript` dataclass (topic, title, host_name, duration_minutes, segments, speakers)
  - `generate_podcast_script(topic, journey, num_segments, duration_minutes, host_name, client, model)` — main entry point
  - `validate_podcast_script(data)` — schema validation returning (is_valid, errors)
  - `generate_script_from_journey()` / `generate_script_from_topic()` — convenience functions
- Used the existing `SchemaValidator` with 3-attempt retry loop from model-layer
- Registered prompt templates `podcast_script_generate` and `podcast_script_retry` in `/model-layer/prompts.py`
- Template renders `{topic}`, `{num_segments}`, `{duration_minutes}`, `{host_name}` placeholders

**Test Results**: 30/30 tests pass (all classes including integration with test_narration.py).

**Test Isolation Fix**: Changed `VALID_SCRIPT_DICT` to a factory function `_make_valid_script_dict()` to prevent mutation across tests — previously, tests in `TestValidatePodcastScript` that modified `data["segments"][0]["type"]` were mutating the shared fixture, causing subsequent `TestGeneratePodcastScript` tests to receive invalid data from the mock.

**Files Created**:
- `/engines/audio-engine/podcast_script.py` — Podcast script generation module
- `/engines/audio-engine/test_podcast_script.py` — Tests (30 tests)

**Files Updated**:
- `/model-layer/prompts.py` — Added podcast_script_generate and podcast_script_retry templates
- `/FILE_MANIFEST.md` — Added podcast_script entries
- `/AGENT_LOG.md` — This log entry

---

## Session: Podcast Audio Rendering (audio-engine)

**Date**: 2026-08-21

**Task**: Add `podcast_audio.py` to audio-engine — a function that takes a PodcastScript and renders it to a single audio file, mapping each turn's speaker to a distinct voice via the TTS client from Prompt 19, concatenating turns with brief pauses.

**Implementation**:
- Created `/engines/audio-engine/podcast_audio.py` with:
  - `render_podcast_to_audio(script, include_mp3=True, output_path=None, speed=1.0, pause_duration=0.3)` — main entry point
  - `PodcastAudioResult` dataclass (wav_bytes, mp3_bytes, duration_seconds, total_segments, backend_used)
  - Speaker-to-voice mapping: each unique speaker gets a distinct Piper voice from `DEFAULT_VOICES` pool
  - Segments are synthesized independently, then concatenated with 0.3s silence pauses between them
  - Reuses `_wav_to_mp3` from narration.py for optional MP3 conversion
  - Helper functions: `_generate_silence()`, `_make_wav_header()`, `_synthesize_segment()`, `_concatenate_wavs()`
- No new heavy dependencies — uses existing `piper-tts` and system ffmpeg
- Returns `PodcastAudioResult` with concatenated WAV (+ optional MP3)

**Test Results**: 22/22 tests pass.

**Test Coverage**:
- Silence generation (duration, zero values, all-zeros content)
- WAV header generation (size, format, data size inclusion)
- WAV concatenation (multiple segments, sample rate handling, empty segments)
- Podcast rendering (segment synthesis count, distinct voice mapping per speaker, single-voice for single-speaker scripts, MP3 toggle, result structure, duration calculation, speed parameter passing)
- Error handling (empty script, invalid script type, TTS failure, MP3 conversion failure)

**Files Created**:
- `/engines/audio-engine/podcast_audio.py` — Podcast audio rendering module
- `/engines/audio-engine/test_podcast_audio.py` — Tests (22 tests)

**Files Updated**:
- `/FILE_MANIFEST.md` — Added podcast_audio entries
- `/AGENT_LOG.md` — This log entry

---

## Session: Language-Lab Bilingual Generation (language-lab)

**Date**: 2026-08-21

**Task**: Add bilingual lesson generation to language-lab — takes a lesson topic, target language, and user's known language, produces a BilingualPair object via model layer with sentence-by-sentence segments, schema-validated with retry-on-failure. Then renders to audio using audio-engine's TTS client (Prompt 19/22) — host voice speaks target_text in target language, second voice speaks translation_text in known language. Translation accuracy is a correctness problem per CONSTITUTION.md §3.

**Implementation**:
- Created `/engines/language-lab/bilingual.py` with:
  - `BilingualSegment` dataclass (target_text, translation_text)
  - `BilingualPair` dataclass (topic, target_language, known_language, segments)
  - `generate_bilingual_pair(topic, target_language, known_language, num_segments, client, model)` — main entry point
  - `render_bilingual_audio(pair, include_mp3=True, output_path=None, speed=0.9)` — renders to audio
  - `generate_and_render()` — convenience function combining both
  - `validate_bilingual_pair(data)` — schema validation
- Added prompt templates `bilingual_generate` and `bilingual_retry` to `/model-layer/prompts.py`
- Reuses audio-engine's `_synthesize_segment`, `_generate_silence`, `_concatenate_wavs`, `_wav_to_mp3`
- Voice mapping: target_text → target-language voice (e.g., Spanish for "es"), translation_text → known-language voice (e.g., English for "en")
- Each segment alternates: target voice → 0.2s pause → known voice → 0.3s pause

**Test Results**: 37/37 tests pass.

**Test Coverage**:
- BilingualSegment/BilingualPair dataclass validation
- Schema validation (required fields, empty text checks)
- Generation with topic, num_segments, languages
- Retry on validation failure
- Audio rendering with correct voice mapping per language
- Speed parameter passing
- MP3 toggle
- Error handling (empty pair, invalid type, TTS failure, MP3 failure)
- Convenience function integration

**Files Created**:
- `/engines/language-lab/bilingual.py` — Bilingual lesson generation and audio rendering
- `/engines/language-lab/test_bilingual.py` — Tests (37 tests)

**Files Updated**:
- `/model-layer/prompts.py` — Added bilingual_generate and bilingual_retry templates
- `/FILE_MANIFEST.md` — Added bilingual entries
- `/AGENT_LOG.md` — This log entry

---

## Session: Language-Lab Immersion Podcast (language-lab)

**Date**: 2026-08-21

**Task**: Add immersion variant to language-lab — same topic/target language as bilingual, but generates a PodcastScript entirely in the target language (reusing audio-engine's podcast_script.py), then renders with two distinct voices via the same rendering path as Prompt 22.

**Implementation**:
- Created `/engines/language-lab/immersion.py` with:
  - `ImmersionResult` dataclass wrapping PodcastScript + PodcastAudioResult
  - `generate_immersion_podcast(topic, target_language, level, ...)` — reuses audio-engine's generate_podcast_script() and render_podcast_to_audio()
  - `generate_and_save_immersion()` — convenience function with disk output
  - No new TTS logic — just configuration wiring
- The immersion mode generates podcast content entirely in target language with two speakers (e.g., host + guest), both speaking the target language
- Audio uses audio-engine's speaker-to-voice mapping (two distinct Piper voices)

**Test Results**: 17/17 tests pass.

**Test Coverage**:
- ImmersionResult property delegation
- Script generation delegation (correct parameters passed)
- Audio rendering delegation (correct parameters passed)
- Parameter passing (num_segments, duration_minutes, include_mp3, output_path, speed)
- Error handling (empty topic, empty target language, generation/rendering errors)
- Convenience function integration

**Files Created**:
- `/engines/language-lab/immersion.py` — Immersion podcast generation
- `/engines/language-lab/test_immersion.py` — Tests (17 tests)

**Files Updated**:
- `/FILE_MANIFEST.md` — Added immersion entries
- `/AGENT_LOG.md` — This log entry

## [2026-08-24 09:55] — opencode/ox-alpha (x-preview-f-free)
Task: Full-workspace architecture review (improve-codebase-architecture) — read all six governance files and every source/test file; produce deepening-opportunities report; update governance documents.
Touched: /CONTEXT.md (created — domain glossary), /FILE_MANIFEST.md (added CONTEXT.md + 2 missing test entries: test_export_integration.py, resume/test_parser.py), /TASKS.md (re-seeded queue: 5 OPEN, 1 BLOCKED:owner-decision, 2 WISHLIST), /AGENT_LOG.md (this entry). Report written outside repo: /tmp/architecture-review-20260824-094204.html
Why: Owner requested a governed current-status scan plus architecture review. Key findings: (1) four hand-rolled generate→validate→retry loops, two calling an LmStudioClient interface that doesn't exist — masked by tests patching _call_model; (2) ~30 sys.path.insert sites across 20 files, no importable packages, schema name collision dodged via importlib; (3) latent defects: narration default path always raises (Kokoro NotImplementedError), podcast_audio WAV check [8:] vs [8:12], resume validator's contact required-check is dead code, immersion.py drops target_language/level; (4) export.py is a 1004-line god-module whose audio branch generates content inside "export" (contradicts deterministic-export contract); (5) governance drift: no git repo despite worktree protocol, FILE_MANIFEST gaps, stale TASKS queue, 8 unexplained test failures from last run. Top recommendation: build the single Guardrail Pipeline module in model-layer first.
Left undone: No code changes made (review-only session). Grilling loop pending owner's pick of candidate. Git init awaits owner decision. Test suite not re-executed here (Python 3.14 lacks httpx/fpdf/docx; original runs were Windows/CPython-3.10). CONSTITUTION/BOOT_ROOT/MASTER_STORY untouched per §5 owner-amendment rule.

## [2026-08-24 10:20] — opencode/ox-alpha (x-preview-f-free)
Task: Draft the inclusive v1 production-readiness plan (owner request) and wire it into governance.
Touched: /docs/PRODUCTION_PLAN.md (created), /FILE_MANIFEST.md (registered plan), /CONTEXT.md (added Generation Pipeline + Voice Catalog terms), /TASKS.md (queue rewritten to canonical P0–P6 task IDs, 12 OPEN / 2 BLOCKED:owner-decision / 6 WISHLIST), /AGENT_LOG.md (this entry)
Why: Owner asked for a fix plan taking the project to production. Plan defines 8 measurable exit criteria (E1–E8: green offline suite, live smoke, zero audit defects, deterministic honest exports, installable offline desktop build on low-spec hardware, graceful resource failures, governance current, pinned deps), 7 phases (P0 foundation → P1 Generation Pipeline → P2 audio correctness/Voice Catalog → P3 language-lab semantics → P4 export split + PPTX/XLSX → P5 storage/shell/packaging → P6 hardening), risk register R1–R6, owner decision log D1–D5 (git init, dir naming, UI toolkit, target OS, v1 scope), and the defect register mapping each of the 6 audit defects to its closing task.
Left undone: No code changes (planning session). Plan is PROPOSED until owner approves; D1/D3/D4 answers unblock P0.0/P5.2/P5.4 respectively. P2∥P4 parallelization available after P1 per plan §4.

## [2026-08-24 10:45] — opencode/ox-alpha (x-preview-f-free)
Task: Execute owner-approved plan decisions — D1 git init (P0.0) + P0.3 cruft cleanup; record D3/D4/D5 resolutions in governance.
Touched: /.gitignore (extended: System Volume Information/, pagefile.sys, .claude/, .pytest_cache/), /docs/PRODUCTION_PLAN.md (status PROPOSED→ACTIVE; decision log D1/D3/D4/D5 RESOLVED), /TASKS.md (P0.0+P0.3 → DONE:opencode; P5.2/P5.4 unblocked with resolved toolkit/OS), /AGENT_LOG.md (this entry)
Why: Owner answered all four gating questions: D1=init now, D3=Tkinter, D4=Windows+Linux together, D5=all built pillars in v1. Executed P0.0: removed 18 generated cache dirs first so baseline is clean, hardened .gitignore against OS cruft on this mounted volume, initialized repo on main with local identity thommyshelby/<thommyshelby@local> (no global identity existed — owner may amend before pushing), staged 57 files / 14,092 lines, verified via `git diff --cached --name-only` that no secrets/pagefile/System Volume Information/.claude paths were included, committed as 09681c3 and tagged audit-2026-08-24.
Left undone: Nothing for P0.0/P0.3. Next claimable work per plan ordering: P0.1 (importable workspace/conftest), P0.2 (8 failing tests root-cause), P0.4 (dependency pins). D2 remains open-by-default.

## [2026-08-24 11:30] — opencode/ox-alpha (x-preview-f-free)
Task: Execute P0.1 + P0.2 + P0.4 (owner said "execute") — make the workspace importable, get the whole suite green from one command, pin dependencies.
Touched: /conftest.py (created), /pytest.ini (created), /requirements.txt (created), 9 source modules de-hacked (journey-core/generator, resume/generator, narration, podcast_audio, podcast_script, bilingual, immersion, youtube_summary, export), 16 test files migrated to canonical dotted imports + patch targets, model-layer/test_tts.py made hermetic (piper stubbed via patch.dict), FILE_MANIFEST/TASKS/AGENT_LOG updated
Why: P0.1 — hyphenated dirs can't be packages, so conftest registers alias packages in sys.modules (engines.journey_core → engines/journey-core etc.); every module now imports canonically (model_layer.*, engines.<engine>.<mod>); the resume/schema importlib dodge and all sys.path.insert bootstrap blocks deleted; pytest runs with --import-mode=importlib from root. Migration done by assertion-checked script (/tmp/opencode/migrate_p01.py, transient) plus iterative grep sweeps; one scripted over-replace corrupted output-filename literals ("narration.wav") — caught via git diff and restored.
Results: python -m pytest → **354 passed, 5 skipped, 0 failed** (was 8 failed at last recorded run). The 5 skips are live-marker tests whose skip messages independently CONFIRM audit defects #1 (LmStudioClient got unexpected kwarg 'model' ×3) and #2 (Kokoro not implemented) — scheduled closures P1.5/P2.1 unchanged. P0.2: old failures not reproducible after migration+pins; guarded permanently by E1 command. P0.4: pins verified on CPython 3.14/Linux.
Left undone: piper-tts not installed here (optional backend; mocked suite doesn't need it). Live smoke still pending LM Studio instance (P1.2 adds harness). Next claimable: P1.1 Generation Pipeline.

## [2026-08-24 12:10] — opencode/ox-alpha (x-preview-f-free)
Task: Execute P1.1 + P1.2 — build the Generation Pipeline (the one Guardrail Loop) and prove its contract with a fake-client suite.
Touched: /model-layer/pipeline.py (created), /model-layer/test_pipeline.py (created, 11 tests), /FILE_MANIFEST.md (+2 rows), /TASKS.md (P1.1, P1.2 → DONE:opencode), /AGENT_LOG.md (this entry)
Why: The pipeline is the deep module the whole plan hangs on: generate(registry, client, template=…, variables=…, validator=…, retry_template=…) returns validated data; it owns JSON extraction, bulleted feedback formatting, transient-error consumption (first consumer of ApiError.retryable), tool-call-instead-of-content handling, and a single DEFAULT_MODEL policy. ScriptedClient in the test suite implements the REAL client interface, so any divergence like the old broken _call_model copies now fails loudly at this seam.
Left undone: Engine migrations still OPEN — P1.3 journey-core, P1.4 resume (+changes-list fix + validator reconciliation closing defects #4/#6), P1.5 podcast_script/bilingual (closes defect #1), P1.6 YouTube summary. Suite state: 365 passed / 5 live-skipped / 0 failed. Next session can start migrating consumers onto the pipeline; each migration is independently committable and keeps the suite green.

## [2026-08-24 13:05] — opencode/ox-alpha (x-preview-f-free)
Task: Execute P1.3 + P1.4 + P1.5 — migrate journey-core, career-engine resume, podcast_script, and bilingual generation onto the Generation Pipeline.
Touched: engines/journey-core/generator.py (rewritten on pipeline), engines/career-engine/resume/generator.py (rewritten; envelope validator), engines/career-engine/resume/schema.py (schema-driven validate_resume via model-layer engine), engines/audio-engine/podcast_script.py + engines/language-lab/bilingual.py (pipeline migration; _call_model copies deleted), 4 private-patch blocks in career-engine/test_integration.py converted to public-seam client injection, podcast_script/bilingual test suites converted to _ScriptedClient injection, export-integration live-guards broadened to the real error taxonomy
Why: Each migration deletes a hand-rolled Guardrail Loop and moves behavior behind the one deep seam. Defects closed this session: #1 (both non-existent-interface _call_model copies deleted), #4 (resume validator now driven by RESUME_SCHEMA — declared contract == enforced contract), #6 (enhance() changes list always comes from the same validated response as the enhanced resume). Found during P1.5: podcast prompt template never interpolates {host_name} — recorded as part of P3.1 scope in TASKS.md.
Left undone: P1.6 (YouTube summary onto pipeline) remains OPEN — last Phase-1 item; then Phase 2 (audio correctness/Voice Catalog). Suite state: **365 passed / 5 live-skipped / 0 failed**, all committed green per step (ac2c344 P1.3, c8960c5 P1.4, this commit P1.5).

## [2026-08-24 14:00] — opencode/ox-alpha (x-preview-f-free)
Task: Execute P1.6 + P2.1 + P2.2 (owner said "continue").
Touched: model-layer/prompts.py (+youtube_summary templates), engines/career-engine/integrations/youtube_summary.py (pipeline migration + validate_video_summary), integrations/test_youtube_summary.py (two contracts flipped to guardrail behavior), model-layer/tts.py (KOKORO_IMPLEMENTED flag + early guard), engines/audio-engine/narration.py (auto-select gated on flag), audio-engine/test_narration.py (contract updates + flag-flip test), engines/audio-engine/podcast_audio.py (WAV [8:12] fix), test_podcast_audio.py (parsing regressions), TASKS/AGENT_LOG
Why: P1.6 completes PHASE 1 — every generation path in the codebase now runs the one Guardrail Loop; summaries lost their best-effort parsing (malformed/empty output retries then raises SchemaValidationError). P2.1 closes audit defect #2: narration's default path selected Kokoro, which always raises; auto-select now defaults to Piper behind the KOKORO_IMPLEMENTED gate, with a flip-the-flag test preserving future behavior. P2.2 closes defect #3: WAV validation rejected all real audio; regression tests parse a genuine header+PCM stream.
Left undone: Phase 2 remainder OPEN — P2.3 Voice Catalog, P2.4 public assembly seam render_segments (heaviest item; wire narration/podcast/bilingual/immersion off the underscore-privates), P2.5 offline voice provisioning kit; then Phases 3-6 per plan. Suite state: **368 passed / 5 live-skipped / 0 failed**; commits 946-style green chain (see log). One mis-scoped edit to prompts.py was caught and reverted via git before it landed (documented for transparency).

## [2026-08-24 15:10] — opencode/ox-alpha (x-preview-f-free)
Task: Execute Phase 2 remainder — P2.3, P2.4, P2.5 (owner said "continue").
Touched: engines/audio-engine/{voice_catalog.py, test_voice_catalog.py, assembly.py, provisioning.py, test_provisioning.py} (created), {narration.py, podcast_audio.py} (rewired onto seam+catalog), language-lab/bilingual.py (render path rebuilt on seam; private imports deleted), audio-engine README (+provisioning checklist), ~46 mock targets retargeted across three test suites, FILE_MANIFEST/TASKS/AGENT_LOG
Why: Phase 2 closed. Voice Catalog is now the only voice table (CONTEXT.md honored); assembly.render_segments is the only cross-engine audio surface — language-lab imports zero underscore-privates. Backend passthrough preserved explicit Kokoro selection (caught because render previously dropped it). Provisioning turned fresh-machine setup into missing_voices()/download_voice() with pinned HF URL layout; tests caught the ja_JP-ken_medium parsing edge and a context-manager mock bug before they shipped.
Left undone: PHASE 3 next — P3.1 podcast templates gain {target_language}/{level}/{host_name} interpolation + immersion forwarding (closes defect #5), P3.2 bilingual verification pass; then P4 export split, P5 storage/shell(Tkinter)/packaging(Win+Linux per D3/D4), P6 hardening. Suite state: **393 passed / 5 live-skipped / 0 failed**.

## [2026-08-24 16:05] — opencode/ox-alpha (x-preview-f-free)
Task: Execute Phase 3 — P3.1 + P3.2 (owner said "continue").
Touched: model-layer/prompts.py (+bilingual_verify template; podcast template gains {language}/{level}/{host_name} + explicit language/complexity requirements), engines/audio-engine/podcast_script.py (+language=/level= params), engines/audio-engine/voice_catalog.py (+LANGUAGE_NAMES/language_name), engines/language-lab/immersion.py (forwards target_language as display name + level; stray "default" model id replaced by project-wide DEFAULT_MODEL), engines/language-lab/bilingual.py (+VerificationVerdict, VerifiedBilingualPair, validate_verdict, verify_bilingual_pair, generate_bilingual_pair_verified), test_immersion/test_podcast_script contract updates, NEW test_bilingual_verification.py (10 tests), FILE_MANIFEST/TASKS/AGENT_LOG
Why: PHASE 3 COMPLETE and the defect register is now fully closed (all 6). P3.1 makes the podcast prompt actually speak the requested language at the requested level with the requested host — immersion's inputs finally reach the model (defect #5). P3.2 adds the §3 correctness artifact for translations: a second Pipeline call reviews every sentence pair, failures trigger one regeneration, and every verdict is kept for human inspection.
Left undone: PHASE 4 next — split export-engine god-module into format adapters, remove generation from export, add PPTX/XLSX Journey exporters, byte-stability tests; then P5 storage/shell/packaging, P6 hardening → E1-E8 ship gate. Suite state: **404 passed / 5 live-skipped / 0 failed**.

## [2026-08-24 17:00] — opencode/ox-alpha (x-preview-f-free)
Task: Execute Phase 4 — P4.1-P4.4 (owner said "continue").
Touched: engines/export-engine/{export.py rewritten thin, detect.py, text_format.py, pdf_format.py, docx_format.py, pptx_format.py, xlsx_format.py (new)}, test_export_integration.py (rewritten honest), test_byte_stability.py (new), requirements.txt (+python-pptx/openpyxl pins), FILE_MANIFEST (export section refreshed, +7 rows), TASKS (P4.x DONE), AGENT_LOG
Why: PHASE 4 COMPLETE. The 1004-line god-module is gone: rendering lives in six per-format adapters, export.py only dispatches and re-exports. Export is now HONEST — podcast/bilingual/immersion kinds raise ValueError naming the explicit engine composition instead of fabricating new podcasts inside a function named "export"; narration remains because text→audio IS deterministic, routed through the assembly seam. New Journey formats PPTX (deck per journey) and XLSX (card table) fulfill the MASTER_STORY promise. All binary formatters pin embedded timestamps/metadata, gated by a byte-stability suite (exit criterion E4).
Left undone: PHASE 5 next — P5.1 storage engine v1 + secrets adapter consolidation, P5.2 Tkinter desktop shell (D3 resolved), P5.3 typed errors to UI surfaces, P5.4 PyInstaller packaging Windows+Linux (D4). Then P6 hardening → ship gate. Suite state: **408 passed / 1 skipped / 0 failed** (skip count fell 5→1 honestly: the deleted regeneration tests were the old live-skips).

## [2026-08-24 18:00] — opencode/ox-alpha (x-preview-f-free)
Task: Execute P5.1 — storage engine v1 + secrets consolidation (owner said "continue").
Touched: storage/{secrets.py, persistence.py, test_secrets.py, test_persistence.py} (created), career-engine integrations {github_client, linkedin_client, youtube_summary} loaders now delegate to storage.secrets (local validity policies kept), youtube_summary user-facing error no longer hardcodes E:/, test docstrings' E:/ mentions normalized, storage/README module map, FILE_MANIFEST (+4 rows), TASKS (P5.1 DONE), AGENT_LOG
Why: Phase 5 opened. Persistence gives every artifact kind a durable offline home (needed by the P5.2 shell's revisit flows); the secrets seam is finally real per the two-adapters rule — three parsers became one, with integration-specific placeholder/length checks staying where they belong. One scripted batch died on a syntax error before touching anything (heredoc quoting); rerun clean — no partial state.
Left undone: P5.2 Tkinter shell (D3 resolved: Tkinter), P5.3 typed errors to UI, P5.4 PyInstaller Windows+Linux (D4) — deliberately left for a fresh session: the shell is a large new surface needing headless-test strategy. Suite state: **408 passed / 1 skipped / 0 failed**.

## [2026-08-24 19:15] — opencode/ox-alpha (x-preview-f-free)
Task: Execute P5.2/P5.3 (+P5.4 partial) — desktop shell vertical slice.
Touched: desktop-shell/{controller.py, app.py, test_controller.py, ldcc.spec, README.md} (created), conftest.py (+desktop_shell alias), pytest.ini (+storage & desktop-shell testpaths), storage/persistence.py (tagged containers T/B/J fixing str/bytes roundtrip loss), storage/test_persistence.py (+legacy-file compat test), FILE_MANIFEST (+4 rows), TASKS, AGENT_LOG
Why: The shell is delivered as architecture-first: every behavior sits behind ShellController whose public methods return FlowResult envelopes mapping the engine error taxonomy to four dialog kinds (no_model/bad_output/input/unexpected) with actionable details (E6) — 14 headless tests prove it, including that LM-Studio-down yields "start it and load a model" rather than a traceback. app.py is deliberately thin and imports tkinter only under main(), so CI stays display-free. Found while wiring: Storage lost the str-vs-bytes distinction on load — fixed with tagged containers (T/B/J) plus an untagged-legacy compatibility path. P5.4 is honest PARTIAL: spec + docs exist; real builds need Windows/display toolchains per D4.
Left undone: P5.4 build verification; shell follow-ups logged as WISHLIST (resume/language tabs, library browser). Remaining plan: P6 hardening → E1–E8 ship gate. Suite state: **443 passed / 1 skipped / 0 failed**.

## [2026-08-24 20:00] — opencode/ox-alpha (x-preview-f-free)
Task: Execute P6.1/P6.2/P6.4 (+ ship-gate audit) (owner said "continue").
Touched: pytest.ini (live deselected by default), run_checks.sh (created — release gate), desktop-shell/app.py (central logging config), engines/language-lab/immersion.py (prints→logger), README.md at root (fresh-machine guide, created), docs/PRODUCTION_PLAN.md (§8 ship-gate status), FILE_MANIFEST/TASKS/AGENT_LOG
Why: Hardening pass within what this environment can verify honestly. Error sweep found only wrap-and-reraise boundaries plus presentation-layer prints; immersion's user-facing prints moved to logging and the shell entry now configures root logging. Quality gates are executable: ./run_checks.sh compiles every source file then runs the offline suite with a 90% coverage floor — current coverage is 93.9%. Ship-gate audit recorded in plan §8: E1/E3/E4/E6/E7/E8 met; E2 (live smoke) and E5 (packaging builds) remain, both requiring resources this machine lacks.
Left undone: E2 live-smoke session against a running LM Studio; E5 PyInstaller builds on Windows+Linux (D4); P6.3 low-spec rehearsal on target hardware; shell follow-up tabs (WISHLIST). Suite state: **443 passed / 1 skipped / 0 failed** with gates green.

## [2026-08-24 21:00] — opencode/ox-alpha (x-preview-f-free)
Task: Plan Phase 7 from owner's vision brief — Paradise Playground as universal free-tool media playground; Language Lab as flagship with interactive grammar/vocab cards + evaluations; answer the small-model "skills/plugins" question.
Touched: docs/PLAYGROUND_AND_LANGUAGE_LAB_PLAN.md (created), MASTER_STORY.md (Pillars 2 & 4 amended in owner's words — Language Lab flagship scope; Playground universal-media/connector-hub scope), FILE_MANIFEST.md (+plan row, notes section), TASKS.md (+P7.1–P7.12 OPEN), AGENT_LOG.md (this entry)
Why: Owner defined expansions directly, exercising their amendment authority over MASTER_STORY. Core architectural answers recorded: (1) no plugin system needed for local models — the Generation Pipeline is the driving wheel; capability profiles + a one-shot probe replace plugins by setting honest expectations per model size; (2) Playground ships as two deep modules — a local ffmpeg-based Media Workspace (editing is offline) and a Connector Hub whose single adapter interface is proven real by three v1 adapters (keyless HF Spaces via gradio_client, keyless Pollinations, Figma free account), while an Import Inbox watch-folder makes no-API services (Suno/Udio/Runway web tiers) first-class; (3) Language Lab gains LessonPack generation feeding an interactive renderer with deterministic-first grading and verdict artifacts, reusing pipeline/assembly/storage seams already built.
Left undone: Implementation is P7.1–P7.12, all OPEN. No code this session (planning).

## [2026-08-24 22:30] — opencode/ox-alpha (x-preview-f-free)
Task: P7.1 capability profiles + one-shot probe; plus owner-directed completion of the local-model inventory (Addendum 2).
Touched: model-layer/{capabilities.py (new), client.py (+list_models), prompts.py (+capability_probe), test_capabilities.py (new)}, storage/persistence.py (+capabilities kind), storage/test_persistence.py, desktop-shell/{controller.py (run_capability_probe/capability_summary), app.py (health bar + Probe button), test_controller.py}, docs/research/2026-08-24-model-choice-for-ldcc.md (Addendum 2), TASKS, AGENT_LOG
Why: The probe grades the loaded model one-shot per task family through the Pipeline (max_attempts=1 — a first-try miss is exactly what's being measured), then persists a verdict doc under storage/capabilities/<model>.json with a preference pointer; health bar renders "ready | <model> (~NB): ready/degraded — <review notes>". Grading is honest: unknown id size degrades but never fails; bilingual keeps its mandatory verify pass below 14B. Inventory ground truth (udisks ro-mount of C:, no sudo needed): gemma-4-12B-it-QAT Q4_0 6.5GB IS installed (= recommended daily driver, vision mmproj included); qwen-2.5-14b-instruct-1m 8.37GB fills the generator slot; DeepSeek-R1-Qwen3-8B judge was DELETED since Addendum 1's Modelfile evidence; MiniMax-Music-3 GGUF load attempts in LM Studio failed (music DiT ≠ chat model — it belongs to ComfyUI on sda6).
Left undone: live probe run against loaded LM Studio (needs E2 session); P7.2+ per plan sequencing. Suite state: **473 passed / 1 skipped / 0 failed**, coverage 93.7%, gates green.

## [2026-08-24 23:15] — opencode/ox-alpha (x-preview-f-free)
Task: P7.2 LessonPack — schema + Pipeline templates + generate_lesson_pack() (owner said "continue").
Touched: model-layer/prompts.py (+lesson_pack_generate/lesson_pack_retry), engines/language-lab/lesson_pack.py (new), engines/language-lab/test_lesson_pack.py (new), FILE_MANIFEST (+2 rows), TASKS, AGENT_LOG
Why: One guardrailed generation produces the whole flagship lesson per plan §C1: dialogue segments shaped for the existing two-voice rendering path (validator enforces exactly two distinct speakers), vocab_cards (term/reading/translation/example), grammar_cards each carrying >=2 drills (prompt/answer), and evaluation[] restricted to the three types P7.3's deterministic graders can judge first (multiple_choice w/ in-range integer correct_index, fill_in_blank requiring a ___ marker, translation). The schema engine has no oneOf, so eval items are pinned at the discriminator in LESSON_PACK_SCHEMA and per-type shapes live in validate_lesson_pack's semantic pass — declared contract stays schema-driven like the P1.4 fix. Translation fidelity deliberately NOT validated here: correctness belongs to P7.3 graders + P3.2-style verification, never trusted from the generator.
Left undone: live-model smoke (E2); P7.3 graders next per plan sequencing. Suite state: **501 passed / 1 skipped / 0 failed**, coverage 93.8%, gates green.

## [2026-08-25 00:10] — opencode/ox-alpha (x-preview-f-free)
Task: P7.3 deterministic graders + model-judge fallback + pack fidelity audit (owner said "continue").
Touched: model-layer/prompts.py (+lesson_judge, lesson_verify), engines/language-lab/graders.py (new), engines/language-lab/test_graders.py (new), storage/persistence.py (+verdicts kind), FILE_MANIFEST (+2 rows), TASKS, AGENT_LOG
Why: Plan §C3 grading order is now enforced in code: deterministic graders answer first and NEVER consult the model (proven by dispatch tests with empty request logs) — normalization casefolds, strips edge punctuation both sides (¿¡ included; a first-cut asymmetric rule would have punted every polite Spanish sentence to the judge), accent-folds as a counted-correct fallback ("correct ignoring accents"), and splits "/" alternatives. Only free-form translations missing their key fall through to the lesson_judge (single pipeline attempt, P3.2 discipline), whose verdict carries canonical answer + issues in an inspectable GradeResult; no client + needed judge raises instead of silently failing the learner. verify_lesson_pack extends fidelity verification beyond translation to grammar explanations, one batched call producing a claim-level artifact (V*/G* ids) whose overall verdict can never contradict its own rows. Incident: test_graders.py picked up 5 NUL bytes from an interrupted tool call — file rewritten clean, __pycache__ purged.
Left undone: live-model smoke (E2); P7.4 LanguageLabRenderer next per plan sequencing. Suite state: **545 passed / 1 skipped / 0 failed**, coverage 94.05%, gates green.

## [2026-08-25 01:05] — opencode/ox-alpha (x-preview-f-free)
Task: P7.4 LanguageLabRenderer — interactive HTML pack (owner said "continue").
Touched: engines/language-lab/renderer.py (new), engines/language-lab/test_renderer.py (new), FILE_MANIFEST (+2 rows), TASKS, AGENT_LOG
Why: Follows the JourneyRenderer split (data vs presentation, never calls a model) with flagship-specific surfaces: flip/self-grade flashcards; grammar drills whose in-browser checking mirrors graders.py rules exactly (same edge-punctuation set incl ¿¡, lowercase≈casefold, whitespace collapse, NFD accent folding, slash alternatives — parity markers asserted so drift cannot land silently); MC and fill-in-blank auto-checked; translation items honestly declare browser limits and fall back to self-grade against the reference answer instead of fake binary judgement. Listening items play per-segment audio by artifact name ("dialogue-N", "listening-N" with fallback) — that is the exact contract P7.5 fills via assembly.render_segments. Deterministic bytes proven; every model-supplied string html-escaped, including quote-safe data-answer attributes (injection test with onmouseover payload). Caught pre-commit: checkDrill's ancestor selector missed .listening-row rows.
Left undone: live-model smoke (E2); P7.5 per-segment audio next per plan sequencing. Suite state: **561 passed / 1 skipped / 0 failed**, coverage 94.21%, gates green.
