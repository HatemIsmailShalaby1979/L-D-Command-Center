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
| `/desktop-shell/README.md` | Packaging and installer pipeline for the desktop-native, offline-first executable. |
| `/docs/README.md` | Supplementary documentation — design notes, research, architecture decisions (non-governance, non-code). |
| `/docs/PRODUCTION_PLAN.md` | Phased v1 production-readiness plan: task IDs (P0–P6) used by TASKS.md, exit criteria, decision log, defect register |
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
| `/engines/export-engine/export.py` | Plain-text, PDF, and DOCX export for both Journey and Resume dicts; unified `export()` dispatcher with `_detect_type()` |
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
| `/engines/export-engine/test_export_integration.py` | 12 tests for unified export() dispatcher incl. audio routing (narration/podcast/bilingual/immersion, all mocked); 4 audio cases failing at last recorded run — see TASKS.md |

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
| `/engines/audio-engine/test_podcast_audio.py` | 22 tests: silence/WAV generation, speaker→voice mapping, segment synthesis, duration calculation, error handling, MP3 toggle |
| `/engines/language-lab/bilingual.py` | Bilingual lesson generation — topic+target/known language → BilingualPair with schema validation and retry; renders to audio using audio-engine TTS with alternating target/translation voices |
| `/engines/language-lab/test_bilingual.py` | 37 tests: dataclass validation, schema validation, generation with retry, audio rendering with voice mapping, error handling, convenience function |
| `/engines/language-lab/immersion.py` | Immersion podcast generation — topic+target language → PodcastScript in target language via audio-engine, rendered with two distinct target-language voices; no new TTS logic, just configuration wiring |
| `/engines/language-lab/test_immersion.py` | 17 tests: ImmersionResult properties, script generation delegation, audio rendering delegation, parameter passing, error handling |
