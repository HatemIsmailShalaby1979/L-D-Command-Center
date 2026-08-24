# TASKS.md

Shared task queue for multi-agent coordination. Status values: OPEN, CLAIMED:<agent>, DONE:<agent>, BLOCKED:<reason>.
See `BOOT_ROOT.md` — Multi-Agent Coordination Protocol.

DONE:claude-code: model-layer client for LM Studio's local API with schema-validated responses and retry-on-failure
DONE:claude-code: journey-core HTML card generator for a single topic+level (renderer module + generator)
DONE:claude-code: export-engine plain-text and PDF output from a journey

DONE:claude-code: career-engine resume schema and generation with model-layer retry pattern
DONE:claude-code: wire Resume objects into export-engine (PDF + DOCX support), add career-engine integration test covering generate→enhance→export→GitHub→LinkedIn→YouTube (all mocked)
DONE:claude-code: add TTS client to model-layer with Piper (default) and Kokoro-82M (optional) backends, backend-agnostic synthesize() interface

--- Production plan queue (IDs are canonical — see /docs/PRODUCTION_PLAN.md; review report: /tmp/architecture-review-20260824-094204.html) ---

DONE:opencode: P0.0 git initialized on main, baseline commit 09681c3, tagged audit-2026-08-24; secrets/OS cruft verified excluded (D1 resolved)
DONE:opencode: P0.1 root conftest.py (hyphen-dir alias packages) + pytest.ini (--import-mode=importlib); all ~30 sys.path.insert sites removed across 20 files; schema collision resolved via canonical dotted imports; suite green from root
DONE:opencode: P0.2 all 8 previously-failing tests now pass under pinned deps; old failures not reproducible post-migration (likely fpdf2 API drift + env drift); permanent guard = pinned requirements.txt + one-command suite. NOTE: 5 live-skips confirm audit defects #1/#2 in un-mocked paths — closed by P1.5/P2.1
DONE:opencode: P0.3 deleted all __pycache__/ and .pytest_cache/ from tree before baseline commit
DONE:opencode: P0.4 requirements.txt pinned (httpx 0.28.1, fpdf2 2.8.8, python-docx 1.2.0, pdfplumber 0.11.10, requests 2.32.5, pytest 9.1.1, reportlab 5.0.1; piper-tts optional)
DONE:opencode: P1.1 build Generation Pipeline deep module in model-layer (render→call→extract→validate→feedback-retry→transient-retry→typed errors); single model-id policy; register youtube summary templates
DONE:opencode: P1.2 one fake-client suite proving pipeline contract + live-marker smoke tests (skipped when LM Studio absent)
DONE:opencode: P1.3 journey-core generate_journey migrated onto Pipeline (public interface unchanged); verified via run_checks.sh
DONE:opencode: P1.4 career-engine generate()/enhance() on Pipeline; Enhancement changes list survives retries (envelope validated per-attempt); validator now schema-driven via _validate_object — dead contact required-check gone (defects #4/#6 closed)
DONE:opencode: P1.5 migrate podcast_script + bilingual generation onto Pipeline; both broken _call_model copies DELETED (defect #1 closed); their suites inject scripted clients through the public seam; live-guard tests in export-integration now use the real error taxonomy
DONE:opencode: P1.6 YouTube summarization on Pipeline; templates registered; validate_video_summary + feedback retry replace best-effort parsing (malformed/empty now raise SchemaValidationError after retries)
DONE:opencode: P2.1 KOKORO_IMPLEMENTED gate in tts.py; narration auto-select defaults to Piper until Kokoro exists (defect #2 closed); explicit overrides honored; flag-flip test keeps future behavior covered
DONE:opencode: P2.2 WAV check fixed to [8:12]; real-shaped-WAV regression test added (defect #3 closed)
DONE:opencode: P2.3 Voice Catalog module (engines/audio-engine/voice_catalog.py): narrator/pair/speaker resolution + has_language provisioning check; 16 tests consolidating narration/podcast/bilingual voice tables into one (language, role) → voice map
DONE:opencode: P2.4 assembly.py render_segments seam live; narration/podcast/bilingual consume it + Voice Catalog; cross-engine private imports eliminated render_segments([(text, voice, speed)]) → AudioResult; migrate all four audio consumers; language-lab stops importing underscore-privates
DONE:opencode: P2.5 provisioning.py — voice_urls/missing_voices/download_voice + README checklist; ja_JP-style ids handled; 9 tests (downloader/checklist + missing-voices error listing exactly what to fetch)
DONE:opencode: P3.1 podcast templates interpolate {language}/{level}/{host_name}; immersion forwards target_language+level (defect #5 CLOSED); LANGUAGE_NAMES in Voice Catalog
DONE:opencode: P3.2 bilingual verification pass — bilingual_verify template, validate_verdict, verify_bilingual_pair + generate_bilingual_pair_verified regenerate-on-fail loop with full verdict audit trail
DONE:opencode: P4.1 export god-module split into detect/text/pdf/docx/pptx/xlsx adapters behind thin export() dispatch
DONE:opencode: P4.2 generation removed from export: podcast/bilingual/immersion kinds raise ValueError pointing at explicit engine composition; narration stays (deterministic text->audio via assembly seam)
DONE:opencode: P4.3 PPTX + XLSX Journey exporters added (python-pptx 1.0.2, openpyxl 3.1.5 pinned)
DONE:opencode: P4.4 byte-stability suite green: pdf/pptx/xlsx/docx pinned metadata => identical bytes on repeat exports (E4 satisfied)
DONE:opencode: P5.1 storage engine v1: persistence.py (artifact kinds + preferences, LDCC_DATA_DIR) and secrets.py (single KEY=VALUE adapter); github/linkedin/youtube loaders now delegate parsing to it, keeping only local validity policies; stale E:/ paths cleaned
DONE:opencode: P5.2 desktop shell v0 (vertical slice): tested ShellController + thin Tkinter window (journey generate→render→save→export txt/pdf/pptx/xlsx + health indicator). FOLLOW-UP: resume/language-lab tabs + library browser
DONE:opencode: P5.3 typed errors surfaced: FlowResult envelope maps ConnectionError/ApiError/SchemaValidationError/ValueError/unexpected to dialog kinds with actionable details; 6 dedicated tests
OPEN:P5.4 ldcc.spec + build docs added; actual PyInstaller builds NOT yet verified on Windows/Linux — pending a machine with display/toolchain
DONE:opencode: P6.1/P6.2/P6.4 error-sweep+gates+docs: run_checks.sh gate (syntax+suite+cov floor 90%), live deselected by default, immersion prints->logger, shell logging config, root README fresh-machine guide, ship-gate snapshot in plan §8


--- Phase 7 queue: Paradise Playground + Language Lab power-up (see /docs/PLAYGROUND_AND_LANGUAGE_LAB_PLAN.md; owner amended vision 2026-08-24) ---

DONE:opencode: P7.1 model-layer/capabilities.py — six task profiles (min-size + review note; bilingual keeps mandatory verify <14B), best-effort size-from-id estimator, one-shot probe through Pipeline (max_attempts=1, no feedback retries), verdict persisted via new storage kind "capabilities" + preference pointer; client.list_models() added; controller run_capability_probe/capability_summary; health bar shows "ready | model (~NB): ready/degraded — …" with Probe button; 27 tests incl. validator rejection branches
DONE:opencode: P7.2 LessonPack schema + Pipeline templates (lesson_pack_generate/lesson_pack_retry) + generate_lesson_pack() with feedback retry — one validated pack: two-voice dialogue (exactly 2 distinct speakers, feeds two-voice rendering), vocab_cards, grammar_cards with drills, evaluation[] in 3 grader-friendly types (multiple_choice/fill_in_blank w/ ___ marker/translation)
DONE:opencode: P7.3 deterministic graders (exact/normalized/accent-folded/slash-alternatives for fill-in-blank+drills; MC integer-index checks) + model-judge fallback for free-form translations (lesson_judge template, inspectable GradeResult w/ canonical answer+issues) + pack fidelity audit (lesson_verify extends P3.2 verification to grammar explanations; claim-level verdict artifact); storage gains "verdicts" kind
DONE:opencode: P7.4 LanguageLabRenderer — interactive HTML pack: flip/self-grade vocab flashcards, grammar drills graded in-browser by JS mirroring graders.py normalization (edge-punct incl ¿¡, accent-fold, slash alternatives), MC/fill-in-blank evaluation, translation items honest self-grade vs reference, listening items wired to segment audio via dialogue-N/listening-N artifact names (consumed by P7.5), final score breakdown; deterministic output; all model content escaped
DONE:opencode: P7.5 per-segment audio via assembly.render_segments — render_pack_audio() emits one WAV per dialogue turn named per the renderer contract (<stem>-dialogue-<i>.wav); speakers resolved to distinct language-scoped voices through the Voice Catalog; optional output_path persistence; mp3 off by default (browser plays wav)
DONE:opencode: P7.6 spaced-repetition-lite (SM-2) — pure scheduler (ladder/ease-floor/lapse rules, injectable today) + SrsStore persisted through Storage preferences blob; due-card selection and cross-restart persistence tested
OPEN: P7.7 Media Workspace core — ffmpeg ingest/normalize/trim/concat/overlay/mix/export for audio/video/image; pure functions + tests (no UI)
OPEN: P7.8 storage kinds extension (media/*) + Import Inbox watch-folder (drop files from any no-API service: Suno/Udio/Runway web exports…)
OPEN: P7.9 Connector Hub seam — single adapter interface (capabilities/send/poll) + gradio_client adapter to keyless Hugging Face Spaces (images/audio/video/upscalers)
OPEN: P7.10 Figma REST adapter (free account) — import designs/frames as PNG/SVG assets
OPEN: P7.11 Pollinations keyless image-generation adapter (no account needed)
OPEN: P7.12 Playground tab in desktop shell — canvas list, import inbox drop target, connector panel with quota notes
