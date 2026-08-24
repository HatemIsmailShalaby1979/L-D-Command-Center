# FILE_MANIFEST.md

Every file in this workspace and its one-line reason for existing. See `CONSTITUTION.md` §1 and `BOOT_ROOT.md`.

## Governance Files (pre-existing)

| Path | Reason |
|------|--------|
| `/CONSTITUTION.md` | Engineering constitution — governs all agent behavior; read first, always |
| `/MASTER_STORY.md` | Canonical product vision and Four Pillars; read second |
| `/BOOT_ROOT.md` | Workspace bootstrap protocol — defines folder skeleton and coordination rules |
| `/CONTEXT.md` | Domain glossary — canonical names for Journey, Card, Bilingual Pair, Immersion Podcast, etc.; gives seams their names |

## Infrastructure Files

| Path | Reason |
|------|--------|
| `/AGENT_LOG.md` | Append-only session ledger per CONSTITUTION.md §2 and BOOT_ROOT.md |
| `/FILE_MANIFEST.md` | This file — canonical registry of every file and its one-line purpose |
| `/TASKS.md` | Shared task queue for multi-agent coordination per BOOT_ROOT.md |
| `/.gitignore` | Excludes /tmp, secrets files (CONSTITUTION.md §3), and standard OS/editor cruft |

## Engine Directories (skeleton — no implementation code)

| Path | Engine Responsibility |
|------|----------------------|
| `/engines/journey-core/README.md` | Topic → interactive HTML learning experience (cards, quizzes, evaluations). Foundational output format all other engines build upon. |
| `/engines/export-engine/README.md` | Converts journey content to downloadable formats: DOCX, PDF, TXT, PPTX, XLSX, and audio (WAV/MP3). |
| `/engines/audio-engine/README.md` | Text → audiobook and podcast audio via TTS orchestration. Serves the export-engine and language-lab. |
| `/engines/language-lab/README.md` | Bilingual and immersion podcast generation for the "Speak Like an Alien" language-learning pillar. |
| `/engines/career-engine/README.md` | Resume generation, upload, enhancement, LinkedIn/GitHub/portfolio connections, YouTube research, and optional LinkedIn posting. |
| `/engines/playground-bridge/README.md` | Bidirectional import-export with external creative AI tools (Figma, Suno, Gemma, etc.). |

## Layer Directories

| Path | Responsibility |
|------|---------------|
| `/model-layer/README.md` | LM Studio client, prompt templates, schema validation, retry logic — the guardrail layer ensuring correctness independent of model size. |
| `/storage/README.md` | Local persistence for journeys, exports, preferences, cached outputs; Notion SOP sync. |
| `/storage/persistence.py` | Storage engine v1 — file-backed artifact store (journeys/resumes/scripts/audio/exports) + preferences; LDCC_DATA_DIR override (P5.1) |
| `/storage/secrets.py` | The one secrets-file adapter — parse_secrets_file/load_secret with deterministic scan order; integrations keep only their validity policies (P5.1) |
| `/storage/test_persistence.py` | 14 tests: roundtrips, kind isolation, name validation, preference defaults/cross-instance persistence |
| `/storage/test_secrets.py` | 9 tests: comment/first-'=' parsing, explicit-path precedence, sorted scan fallback, empty-value policy |
| `/desktop-shell/README.md` | Packaging and installer pipeline for the desktop-native, offline-first executable. |
| `/desktop-shell/controller.py` | Shell controller — the entire engine surface behind typed FlowResults; all UI behavior, headless-tested (P5.2/P5.3) |
| `/desktop-shell/app.py` | Thin Tkinter window over the controller; tkinter imported only at runtime (P5.2) |
| `/desktop-shell/test_controller.py` | 14 controller tests: health, journey flow, typed-error mapping (no_model/bad_output/input/unexpected), render+persist, export routing, library roundtrip |
| `/desktop-shell/ldcc.spec` | PyInstaller spec for the single-file `ldcc` executable (P5.4); secrets/voices deliberately not bundled |
| `/docs/README.md` | Supplementary documentation — design notes, research, architecture decisions (non-governance, non-code). |
| `/docs/PRODUCTION_PLAN.md` | Phased v1 production-readiness plan: task IDs (P0–P6) used by TASKS.md, exit criteria, decision log, defect register |
| `/docs/PLAYGROUND_AND_LANGUAGE_LAB_PLAN.md` | Phase-7 plan: capability profiles (small-model driving), Media Workspace + Connector Hub roster, LessonPack/interactive renderer/spaced-repetition for Language Lab |
| `/requirements.txt` | Pinned dependency versions for reproducible offline installs (exit criterion E8) |
| `/conftest.py` | Root pytest bootstrap — registers underscore alias packages for hyphenated engine dirs so dotted imports resolve; the single import convention |
| `/pytest.ini` | Runner config — testpaths, importlib mode, `live` marker registration |

## Model-Layer Implementation

| Path | Reason |
|------|--------|
| `/model-layer/client.py` | Real LM Studio HTTP client (httpx) — OpenAI-compatible /v1/chat/completions with tool calling, typed ApiError subclasses, health check |
| `/model-layer/schema.py` | Journey JSON schema + validate_journey() + SchemaValidator with 3-attempt retry loop + extract_json_from_text() bracket-scanner |
| `/model-layer/prompts.py` | PromptRegistry with journey_generate and journey_retry templates, {placeholder} rendering, schema_key wiring |
| `/model-layer/pipeline.py` | Generation Pipeline — the single Guardrail Loop (render→call→extract→validate→retry→typed error) every engine generates through; owns model-id defaults and transient-error policy |
| `/model-layer/test_pipeline.py` | 11 contract tests for the Pipeline via a ScriptedClient matching the real LmStudioClient interface (retry counts, feedback formatting, error taxonomy) |

## Journey-Core Engine (implementation)

| Path | Reason |
|------|--------|
| `/engines/journey-core/__init__.py` | Package init for journey-core (hyphenated dir requires explicit init) |
| `/engines/journey-core/generator.py` | generate_journey(topic, level) — wires prompts→client→validate→retry; the single entry point for journey generation |
| `/engines/journey-core/test_generator.py` | 10 tests covering valid output, retry on schema failure, malformed output, invalid level, default client, custom num_cards, and schema validation |
| `/engines/journey-core/renderer.py` | JourneyRenderer — converts validated Journey dict to interactive HTML with cards, quizzes, evaluation panels, and JS interactivity; never calls the model |
| `/engines/journey-core/test_renderer.py` | 12 tests covering HTML structure, content inclusion, escaping, error cases, and convenience function |

## Export-Engine Implementation

| Path | Reason |
|------|--------|
| `/engines/export-engine/__init__.py` | Package init for export-engine |
| `/engines/export-engine/export.py` | Thin public surface: honest `export()` dispatcher (journey/resume/narration; rejects generation-requiring kinds per P4.2) + re-exports from format adapters |
| `/engines/export-engine/detect.py` | Content-type detection (`_detect_type`) extracted from the former god-module (P4.1) |
| `/engines/export-engine/text_format.py` | Deterministic plain-text renderers/writers (Journey + Resume) |
| `/engines/export-engine/pdf_format.py` | Deterministic PDF renderers/writers; creation date pinned for byte-stability |
| `/engines/export-engine/docx_format.py` | Deterministic DOCX renderer/writer; core properties pinned |
| `/engines/export-engine/pptx_format.py` | Journey -> PowerPoint deck (title slide + one slide per Card); properties pinned (P4.3) |
| `/engines/export-engine/xlsx_format.py` | Journey -> spreadsheet (metadata header + card rows); properties pinned (P4.3) |
| `/engines/export-engine/test_byte_stability.py` | E4 gate: same artifact exported twice must be byte-identical across all binary formats |
| `/engines/export-engine/test_export.py` | 50 tests: journey text/PDF, resume text/PDF/DOCX, type detection, unified dispatcher, file writing |

## Career-Engine Implementation

| Path | Reason |
|------|--------|
| `/engines/career-engine/resume/schema.py` | Resume JSON schema (contact, summary, experience[], education[], skills[], projects[]) + validate_resume() |
| `/engines/career-engine/resume/generator.py` | generate() and enhance() entry points — wires prompts→client→validate→retry using model-layer SchemaValidator; enhance() also returns human-inspectable changes list |
| `/engines/career-engine/resume/test_generator.py` | 11 tests: 3 for generate() (mocked), 4 for validate_resume(), 4 for enhance() (mocked, including retry and persistent failure) |
| `/engines/career-engine/resume/parser.py` | PDF/DOCX resume parser — extracts fields via pattern matching, returns (resume_dict, confidence_flags) with unknown/missing fields flagged |
| `/engines/career-engine/resume/test_parser.py` | 16 tests: text parsing patterns, PDF/DOCX extraction, confidence flagging, file dispatch |

## Career-Engine Integrations

| Path | Reason |
|------|--------|
| `/engines/career-engine/integrations/github_client.py` | Read-only GitHub client — fetches public repos and READMEs, seeds Resume.projects proposals (never writes) |
| `/engines/career-engine/integrations/test_github_client.py` | 16 tests: token loading, repo fetching, README parsing, project proposal logic |
| `/secrets/github.secrets` | GitHub personal access token (git-ignored per CONSTITUTION.md §3) |
| `/engines/career-engine/integrations/linkedin_client.py` | LinkedIn OAuth client (self-serve tier) — reads own profile via /v2/userinfo (openid+profile), posts via w_member_social, rate-limited, require confirm=True for write ops |
| `/engines/career-engine/integrations/test_linkedin_client.py` | 19 tests: scopes, rate limiter, token loading, profile fetch, post safety gate, rate limit enforcement |
| `/secrets/linkedin.secrets` | LinkedIn OAuth token/credentials (git-ignored per CONSTITUTION.md §3) |
| `/engines/career-engine/integrations/youtube_summary.py` | YouTube video search + AI summarization — requires YOUTUBE_API_KEY, every summary includes traceable source URL, uses model layer via PromptRegistry |
| `/engines/career-engine/integrations/test_youtube_summary.py` | 19 tests: API key loading, video search, summary generation, URL tracing invariant |
| `/secrets/youtube.secrets` | YouTube Data API key (git-ignored per CONSTITUTION.md §3) |

## Career-Engine Integration Tests

| Path | Reason |
|------|--------|
| `/engines/career-engine/test_integration.py` | 8 tests: full pipeline generate→enhance→export PDF/DOCX→GitHub→LinkedIn→YouTube (all mocked), drift status report |

## Integration Tests

| Path | Reason |
|------|--------|
| `/engines/test_integration.py` | Full pipeline test: generate→render→export using same Journey; mocked and live variants |
| `/engines/export-engine/test_export_integration.py` | Honest dispatcher suite: routing per kind/format, file writing incl. nested dirs, narration-via-seam WAV, and the no-generation ValueErrors (P4.2) |

## TTS Client (model-layer)

| Path | Reason |
|------|--------|
| `/model-layer/tts.py` | Text-to-speech client with Piper (default, CPU-only) and Kokoro-82M (optional) backends; backend-agnostic `synthesize(text, voice, language) -> audio bytes` interface |
| `/model-layer/test_tts.py` | 25 tests covering config, error handling, backend dispatch, voice discovery, and audio generation |

## Audio-Engine Implementation

| Path | Reason |
|------|--------|
| `/engines/audio-engine/__init__.py` | Package init for audio-engine |
| `/engines/audio-engine/narration.py` | Text narration function — auto-selects Kokoro for supported languages, falls back to Piper; outputs WAV + MP3 via ffmpeg |
| `/engines/audio-engine/test_narration.py` | 33 tests: language detection, backend selection, error handling, Journey card/Resume summary narration, MP3 conversion |
| `/engines/audio-engine/podcast_script.py` | Podcast script generation — topic/Journey → structured script with schema validation and retry logic |
| `/engines/audio-engine/test_podcast_script.py` | 30 tests: dataclass validation, schema validation, generation, retry logic, error cases, convenience functions |
| `/engines/audio-engine/podcast_audio.py` | Podcast audio renderer — maps each speaker to a distinct Piper voice, synthesizes and concatenates segments with brief pauses; outputs WAV (+ optional MP3 via ffmpeg) |
| `/engines/audio-engine/assembly.py` | Public audio assembly seam — render_segments(speech|silence) -> AudioResult; owns WAV parse/silence/concat/MP3 so no engine imports another's privates |
| `/engines/audio-engine/voice_catalog.py` | Voice Catalog — single (language, role) -> voice table (Piper + future Kokoro); English fallback warns |
| `/engines/audio-engine/provisioning.py` | Offline voice provisioning — catalog id -> HF URLs, missing-voices report, downloader |
| `/engines/audio-engine/test_podcast_audio.py` | 22 tests: silence/WAV generation, speaker→voice mapping, segment synthesis, duration calculation, error handling, MP3 toggle |
| `/engines/language-lab/bilingual.py` | Bilingual lesson generation — topic+target/known language → BilingualPair with schema validation and retry; renders to audio using audio-engine TTS with alternating target/translation voices |
| `/engines/language-lab/test_bilingual.py` | 37 tests: dataclass validation, schema validation, generation with retry, audio rendering with voice mapping, error handling, convenience function |
| `/engines/language-lab/immersion.py` | Immersion podcast generation — topic+target language → PodcastScript in target language via audio-engine, rendered with two distinct target-language voices; no new TTS logic, just configuration wiring |
| `/engines/language-lab/test_immersion.py` | 17 tests: ImmersionResult properties, script generation delegation, audio rendering delegation, parameter passing, error handling |
| `/engines/language-lab/test_bilingual_verification.py` | 10 tests for the P3.2 translation-fidelity pass — verdict schema, review rendering, generate-verify-regenerate audit trail |
| `/engines/language-lab/lesson_pack.py` | P7.2 whole-lesson generation — topic+languages+level → one validated LessonPack dict (two-voice dialogue, vocab cards, grammar cards with drills, mixed evaluation items); LESSON_PACK_SCHEMA via _validate_object + semantic pass (exactly 2 speakers; per-type eval shapes) |
| `/engines/language-lab/test_lesson_pack.py` | 28 tests: pipeline generation with feedback retry, typed failure, input guards, schema+semantic rejection branches, template registration |
| `/engines/language-lab/graders.py` | P7.3 grading — deterministic first (normalize/accent-fold/slash alternatives; MC index checks), model-judge fallback for free-form translations (inspectable GradeResult, single pipeline attempt), pack fidelity audit of vocab translations + grammar explanations returning claim-level verdict artifact |
| `/engines/language-lab/test_graders.py` | 44 tests: normalization table, all grader rules and rejection branches, judge verdict validation/prompt content, dispatch guarantees (deterministic hits never call the model), audit consistency |
| `/engines/language-lab/renderer.py` | P7.4 LanguageLabRenderer — validated LessonPack dict → deterministic self-contained interactive HTML: flip/self-grade flashcards, grammar drills checked by JS mirroring graders.py normalization (edge-punct incl ¿¡, accent fold, slash alternatives), MC + fill-in-blank + translation evaluation with honest self-grade fallback for free-form answers, listening items wired to per-segment audio artifact names, score breakdown screen; all model content escaped |
| `/engines/language-lab/test_renderer.py` | 16 tests: section/content presence, determinism, rejection of incomplete packs, injection escaping incl. quote-safe answer attributes, JS/Python grading-rule parity markers, audio wiring contract (dialogue-N / listening-N keys with fallback) |
| `/engines/language-lab/pack_audio.py` | P7.5 per-segment lesson-pack audio — each dialogue turn rendered through assembly.render_segments into its own WAV artifact named exactly per the renderer contract (<stem>-dialogue-<i>.wav); speaker→voice assignment via Voice Catalog language-scoped pool (distinct speakers = distinct voices); optional output_path persistence; MP3 off by default |
| `/engines/language-lab/test_pack_audio.py` | 12 tests: renderer-contract naming, slug safety, distinct/stable voice mapping (language-scoped), speed forwarding, empty-dialogue rejection, output_path byte-identical writes |
| `/engines/language-lab/srs.py` | P7.6 spaced-repetition-lite — pure SM-2 core (interval ladder 1→6→ease-multiplied, quality ease-adjustment floored at 1.3, lapse reset + lapse counter) over a frozen CardState; SrsStore persists all card schedules as one Storage preference blob; today injectable everywhere |
| `/engines/language-lab/test_srs.py` | 22 tests: SM-2 table (first/second/nth recalls, ease deltas q=5/4/3, floor after repeated hard cycles, lapse reset+restart), invalid-quality rejections, state roundtrip with unknown-key tolerance, persistence across instances, due-card filtering/sorting, forget |
| `/engines/playground-bridge/media_workspace.py` | P7.7 Media Workspace core — pure ffmpeg plan functions (convert/trim/scale/pad/volume/mix amix/concat demuxer w/ side-file listing/overlay) returning frozen MediaSpec argv data + one thin executor with injectable runner; ffprobe→typed ProbeResult; ingest copies collision-safe then probes; missing binary → install-hint MediaToolError |
| `/engines/playground-bridge/test_media_workspace.py` | 18 tests: verbatim argv contracts per planner, spec purity/determinism, concat side-file materialization, failure stderr-tail mapping, parent-dir creation, canned ffprobe JSON parsing, collision-safe ingest |
| `/engines/playground-bridge/import_inbox.py` | P7.8 Import Inbox watch-folder — one-shot scan_inbox() moves dropped files into storage media/<subkind> with collision-safe names, case-insensitive extension filter (rejected files stay), delete-after-import semantics, per-failure isolation; storage/persistence.py gains namespaced media/<subkind> kinds |
| `/engines/playground-bridge/test_import_inbox.py` | 19 tests: media subkind roundtrip + invalid-subkind rejection, unique-name suffixing, import+delete, filter leave-in-place, case-insensitivity, collision rename, delete_after=false, dir/absent-inbox handling, custom subkind |

## Notes

- 2026-08-24: owner amended vision (Phase 7). TASKS.md carries P7.1–P7.12; plan in docs/PLAYGROUND_AND_LANGUAGE_LAB_PLAN.md.
