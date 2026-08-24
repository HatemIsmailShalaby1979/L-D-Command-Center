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
OPEN: P0.1 root conftest.py + pytest config; remove ~30 sys.path.insert sites across 20 files; resolve schema name collision via package aliases (no dir renames — D2 deferred)
OPEN: P0.2 investigate + fix 8 failing tests from last recorded run (export PDF ×4, export audio ×4 per export-engine/.pytest_cache/lastfailed); log root cause in AGENT_LOG
DONE:opencode: P0.3 deleted all __pycache__/ and .pytest_cache/ from tree before baseline commit
OPEN: P0.4 pin dependencies in requirements.txt with tested versions; document Python target
OPEN: P1.1 build Generation Pipeline deep module in model-layer (render→call→extract→validate→feedback-retry→transient-retry→typed errors); single model-id policy; register youtube summary templates
OPEN: P1.2 one fake-client suite proving pipeline contract + live-marker smoke tests (skipped when LM Studio absent)
OPEN: P1.3 migrate journey-core generate_journey onto Pipeline (public interface unchanged)
OPEN: P1.4 migrate career-engine generate()/enhance(); Enhancement changes list survives retries; reconcile resume validator with RESUME_SCHEMA (dead contact required-check)
OPEN: P1.5 migrate podcast_script + bilingual generation onto Pipeline (deletes both broken _call_model copies)
OPEN: P1.6 migrate YouTube summarization onto Pipeline + schema-validate summary output
OPEN: P2.1 narration backend selection only among available backends; Piper truly default until Kokoro implemented
OPEN: P2.2 fix podcast_audio.py:160 WAV check ([8:] → [8:12]) + regression test with real-shaped WAV bytes
OPEN: P2.3 create Voice Catalog module consolidating narration/podcast/bilingual voice tables into one (language, role) → voice map
OPEN: P2.4 audio-engine public assembly seam render_segments([(text, voice, speed)]) → AudioResult; migrate all four audio consumers; language-lab stops importing underscore-privates
OPEN: P2.5 offline Piper voice provisioning kit (downloader/checklist + missing-voices error listing exactly what to fetch)
OPEN: P3.1 podcast templates gain {target_language}/{level}; immersion forwards both; regression test Spanish immersion → Spanish script
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
