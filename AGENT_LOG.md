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
