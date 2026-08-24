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
OPEN: P1.3 migrate journey-core generate_journey onto Pipeline (public interface unchanged)
OPEN: P1.4 migrate career-engine generate()/enhance(); Enhancement changes list survives retries; reconcile resume validator with RESUME_SCHEMA (dead contact required-check)
DONE:opencode: P1.5 migrate podcast_script + bilingual generation onto Pipeline; both broken _call_model copies DELETED (defect #1 closed); their suites inject scripted clients through the public seam; live-guard tests in export-integration now use the real error taxonomy
DONE:opencode: P1.6 YouTube summarization on Pipeline; templates registered; validate_video_summary + feedback retry replace best-effort parsing (malformed/empty now raise SchemaValidationError after retries)
DONE:opencode: P2.1 KOKORO_IMPLEMENTED gate in tts.py; narration auto-select defaults to Piper until Kokoro exists (defect #2 closed); explicit overrides honored; flag-flip test keeps future behavior covered
CLAIMED:opencode: P2.2 fix podcast_audio.py:160 WAV check ([8:] → [8:12]) + regression test with real-shaped WAV bytes
OPEN: P2.3 create Voice Catalog module consolidating narration/podcast/bilingual voice tables into one (language, role) → voice map
OPEN: P2.4 audio-engine public assembly seam render_segments([(text, voice, speed)]) → AudioResult; migrate all four audio consumers; language-lab stops importing underscore-privates
OPEN: P2.5 offline Piper voice provisioning kit (downloader/checklist + missing-voices error listing exactly what to fetch)
OPEN: P3.1 podcast templates gain {target_language}/{level} AND {host_name} interpolation (gap found during P1.5: template never renders host); immersion forwards all three; regression tests Spanish immersion → Spanish script, custom host appears in prompt
OPEN: P3.2 bilingual translation verification pass (second Pipeline call checking target/translation fidelity; mismatches retried; human-inspectable verdict kept)
OPEN: P4.1 split export-engine/export.py (1004 lines) into format adapters behind unified export() dispatch
OPEN: P4.2 remove generation from export (delete export_audio_* regeneration); Journey→audio becomes explicit engine-level composition callers invoke deliberately
WISHLIST: P4.3 add PPTX + XLSX Journey exporters (MASTER_STORY promise; python-pptx/openpyxl pinned first)
WISHLIST: P4.4 byte-stability tests for every export format
WISHLIST: P5.1 storage/ engine v1 — file persistence for artifacts + preferences; consolidate three secrets parsers into storage/secrets.py::load_secret(name)
OPEN: P5.2 desktop app shell — toolkit RESOLVED D3=stdlib Tkinter; minimal UI over existing engines
WISHLIST: P5.3 wire typed errors to UI surfaces (LM Studio down → actionable message; missing TTS voices → provisioning hint)
OPEN: P5.4 desktop-shell packaging (PyInstaller → Windows + Linux installers per D4; offline verification both OSes; low-spec perf budget)
WISHLIST: P6.x hardening & release gates — error-taxonomy sweep, coverage floor, low-spec rehearsal, docs pass, final governance audit (see PRODUCTION_PLAN.md Phase 6)
