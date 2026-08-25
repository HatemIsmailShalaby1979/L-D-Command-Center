# PRODUCTION_PLAN.md — L&D Command Center v1

Status: ACTIVE (owner-approved 2026-08-24 with D1/D3/D4/D5 resolved — see §6).
D2 stays open-by-default (alias approach). Task IDs below (`P0.1`, `P1.2`, …)
are the canonical references used in TASKS.md.

---

## 1. Exit criteria — what "production ready" means here

Per MASTER_STORY: desktop-only, offline-first, free, runs on low-spec hardware,
production-ready is the bar. Concretely, v1 is done when **all** of these hold:

| # | Criterion | Verified by |
|---|-----------|-------------|
| E1 | Entire suite green from one command at repo root, no network needed | `python -m pytest -m "not live"` |
| E2 | Live end-to-end smoke against LM Studio passes for every shipped feature | `python -m pytest -m live` (documented manual variant) |
| E3 | Zero known latent defects from the 2026-08-24 audit | Defect register §7 all closed |
| E4 | Exports are deterministic and honest (bytes-in → bytes-out; never calls the model) | Byte-stability tests + code rule |
| E5 | Installable desktop package runs fully offline on a clean low-spec machine | Packaged build + offline checklist |
| E6 | Missing-resource failures degrade gracefully (no TTS voice, LM Studio down, no ffmpeg) with actionable messages | Error-path tests |
| E7 | Governance current: FILE_MANIFEST complete, AGENT_LOG continuous, TASKS.md has no stale OPEN items | Audit pass |
| E8 | Dependency set pinned and installable offline (vendored wheels or documented installer) | Fresh-machine install rehearsal |

---

## 2. Ground rules

1. **Each phase ends green.** No phase starts while the previous one fails E1.
2. **One task per TASKS.md line**, claimed per BOOT_ROOT protocol. Plan IDs are
   stable references; TASKS.md carries status.
3. **No new top-level folders.** Everything lands inside the BOOT_ROOT skeleton.
4. **Decisions before dependencies.** D1–D5 (§6) gate specific phases; ambiguous
   points escalate to the owner (CONSTITUTION §3), never silently guessed.
5. **Guardrail Loop stays the shape of correctness**: any new generation path
   must go through the Generation Pipeline (CONTEXT.md), never around it.

---

## 3. Phases

### Phase 0 — Foundation & hygiene  `[size: S]`  *(blocks everything)*

| ID | Task | Notes |
|----|------|-------|
| P0.0 | **D1: initialize git repository**, baseline commit, tag `audit-2026-08-24` | Currently BLOCKED:owner-decision. Everything else is safer once history exists. Secrets stay ignored. |
| P0.1 | Root test/bootstrap config: `conftest.py` + `pytest.ini`/`pyproject.toml`; kill all ~30 `sys.path.insert` sites; resolve the `schema` name collision via package aliases | Review candidate C2, conftest-first variant — no BOOT_ROOT amendment required. Renaming dirs stays open as D2, deferred. |
| P0.2 | Investigate + fix the 8 failing tests from the last recorded run (export PDF ×4, export audio ×4) | Likely dependency/API drift (fpdf2 `new_x/new_y` kwargs) — pin versions in P0.4 regardless. Log root cause in AGENT_LOG. |
| P0.3 | Delete generated cruft from tree: `__pycache__/`, `.pytest_cache/` (×9 each) | One-off cleanup; .gitignore already covers them post-D1. |
| P0.4 | Pin dependencies: `requirements.txt` with tested versions (httpx, fpdf2, python-docx, pdfplumber, piper-tts, pytest); document Python target (3.10/3.11) | Feeds E8. |
| P0.5 | Close out governance drift items from the audit (manifest rows, ledger continuity) | Mostly done 2026-08-24; verify none reopened. |

**Exit:** E1 green from root command; clean `git status`; pinned deps install.

### Phase 1 — Generation Pipeline (guardrail correctness core)  `[size: L]`

Review candidate C1. The four hand-rolled loops collapse into one deep module;
this retires audit defects #1 (broken `_call_model` ×2) and #6 (Enhancement
changes list lost on retry).

| ID | Task | Notes |
|----|------|-------|
| P1.1 | Build the **Generation Pipeline** in model-layer: render → call → extract JSON → validate → feedback-retry → transient-retry → typed error. Single model-id policy. Consumes `ApiError.retryable`. | Interface ≈ `generate(template_key, variables, validator) -> data`. PromptRegistry gains youtube summary templates (today inline in youtube_summary.py — violates its own contract). |
| P1.2 | One fake-client test suite proving the pipeline contract (retry counts, extraction edge cases, tool-call-instead-of-content, connection failure taxonomy). Add `live` marker tests skipped when LM Studio is absent. | Fixes the class of bug where mocks diverge from the real adapter. |
| P1.3 | Migrate journey-core `generate_journey` onto the pipeline. Public function unchanged. | |
| P1.4 | Migrate career-engine `generate()`/`enhance()`; carry the Enhancement changes list through retries intact. | Defect #6 closes here. |
| P1.5 | Migrate podcast_script + bilingual generation (deletes both broken `_call_model`s). Immersion inherits via delegation. | Defect #1 closes here. |
| P1.6 | Migrate YouTube summarization onto the pipeline + schema-validate its summary output. | Today: json.loads-with-fallback, no validation — a CONSTITUTION §3 gap. |

**Exit:** every generation path goes through the Pipeline; fake-client suite
covers it; live smoke passes for Journey + Resume + PodcastScript +
BilingualPair (E2 partial).

### Phase 2 — Audio correctness & Voice Catalog  `[size: M]`

Review candidate C3. Retires audit defects #2 (narration Kokoro crash) and
#3 (WAV parse bug).

| ID | Task | Notes |
|----|------|-------|
| P2.1 | Fix narration backend selection: auto-select only among *available* backends; Piper is the true default until Kokoro is implemented. | Availability = voice model files present (`get_available_voices`). |
| P2.2 | Fix `podcast_audio.py` WAV check (`wav_bytes[8:]` → `[8:12]`) + regression test with real-shaped WAV bytes. | |
| P2.3 | Create the **Voice Catalog** module: one `(language, role) → voice id` table consolidating narration's Kokoro map, podcast_audio's speaker pool, bilingual's TARGET_VOICES/KNOWN_VOICES. Backend-aware. | New concept — registered in CONTEXT.md 2026-08-24. |
| P2.4 | Public assembly seam in audio-engine: `render_segments([(text, voice, speed)]) -> AudioResult` (silence/concat/mp3 internal). Migrate narration, podcast, bilingual, immersion onto it. Language-lab stops importing underscore-privates. | |
| P2.5 | Offline voice provisioning: documented downloader/checklist for Piper voice files + graceful "missing voices" error listing exactly what to fetch. | Offline-first requirement (MASTER_STORY); feeds E6. |

**Exit:** narrate/podcast/bilingual/immersion all produce real audio on a
machine with only Piper voices installed; no private imports cross the seam.

### Phase 3 — Language-lab semantics  `[size: S]`

Retires audit defect #5; strengthens the §3 correctness stance on translation.

| ID | Task | Notes |
|----|------|-------|
| P3.1 | Extend podcast templates with `{target_language}`/`{level}` variables; immersion forwards both. Regression: Spanish immersion request → Spanish-language script. | Defect #5. |
| P3.2 | Bilingual translation verification pass: second Pipeline call where the model checks target/translation fidelity segment-by-segment; mismatches retried. Human-inspectable verdict kept alongside the Bilingual Pair. | Translation accuracy is a correctness problem (CONSTITUTION §3, CONTEXT.md). Design-it-twice if interface unclear. |

**Exit:** language outputs provably honor requested language/level; bilingual
pairs ship with a verification artifact.

### Phase 4 — Export split & promised formats  `[size: M]`

Review candidate C4. Enforces the Export contract (CONTEXT.md): deterministic,
never calls the model. Do before PPTX/XLSX work lands in today's god-file.

| ID | Task | Notes |
|----|------|-------|
| P4.1 | Split export-engine into format adapters (txt/pdf/docx modules) behind the unified `export()` dispatch; replace key-sniffing with explicit artifact typing where feasible. | Keeps public signature; 50-test suite migrates with it. |
| P4.2 | Remove generation from export: delete `export_audio_*` regeneration paths; Journey→audio becomes an explicit engine-level pipeline composition (Journey → PodcastScript → audio) that callers invoke deliberately. | The current `export(podcast_dict)` fabricates a *new* podcast — dishonest interface. |
| P4.3 | Add PPTX + XLSX Journey exporters (MASTER_STORY promise). | python-pptx/openpyxl added to pins. |
| P4.4 | Byte-stability tests: same artifact → identical bytes across runs for every format. | Feeds E4. |

**Exit:** E4 satisfied; Journey exports to txt/PDF/PPTX/XLSX; Resume to
txt/PDF/DOCX.

### Phase 5 — Storage, app shell, packaging  `[size: L]`

The unbuilt platform tier. Includes review candidate C5 (secrets adapter).

| ID | Task | Notes |
|----|------|-------|
| P5.1 | **storage/** engine v1: file-based persistence for Journeys/Resumes/scripts/exports + preferences; consolidate the three secrets-file parsers into `storage/secrets.py::load_secret(name)`. | GitHub/LinkedIn/YouTube adapters migrate to it; Paradise Playground inherits free. |
| P5.2 | **D3: choose UI toolkit**, then minimal desktop shell: create/browse/render Journeys, export dialog, narrate button, language-lab forms, resume upload/enhance, health indicator for LM Studio. Recommendation: stdlib Tkinter (zero deps, low-spec-safe); revisit in v2. | Owner decision gates this task. |
| P5.3 | Wire typed errors to UI surfaces (LM Studio down → actionable message; missing TTS voice → provisioning hint from P2.5). | Feeds E6. |
| P5.4 | **desktop-shell/**: PyInstaller (or Nuitka) build → signed-or-at-least-versioned installer; offline verification checklist; low-spec perf budget test (define: e.g. 8GB RAM / 4-core machine, generation latency measured). | D4 confirms target OS order (recommendation: Windows first — workspace evidence is Windows; Linux second). Feeds E5. |

**Exit:** E5 met — installable app on a clean machine, fully offline.

### Phase 6 — Hardening & release gates  `[size: M]`

| ID | Task | Notes |
|----|------|-------|
| P6.1 | Error-taxonomy sweep: no bare excepts in shipped paths; logging configured centrally; secrets never logged (re-audit). | |
| P6.2 | Quality gates: coverage floor on model-layer + engine cores; `-m "not live"` default; CI-style runner script (local, offline). | Feeds E1/E7 permanently. |
| P6.3 | Low-spec performance rehearsal on target hardware: generation retry-rate stats (small-model reality check), TTS throughput, memory ceiling. | Informs whether guardrail budgets (max_attempts=3) hold on weak machines. |
| P6.4 | Documentation pass: READMEs match reality; ARCHITECTURE pointers into CONTEXT.md; fresh-machine install guide (feeds E8). | |
| P6.5 | Final governance audit against §1 exit criteria; close TASKS.md leftovers; AGENT_LOG completeness check. | |

**Exit:** E1–E8 all checked. Ship v1.

### Post-v1 backlog (explicitly NOT production-blocking)

Notion SOP capture · Paradise Playground bridge (Figma/Suno/Gemma) · Kokoro
backend implementation · LinkedIn/GitHub deep flows (portfolio, YouTube
research UI) · multi-machine sync · installer signing/auto-update · D2 folder
renaming revisit.

---

## 4. Sequencing & sizing overview

```
P0 ──► P1 ──► P2 ──► P3 ──► P4 ──► P5 ──► P6 ──► v1 SHIP
 S      L      M      S      M      L      M
      └────────── parallelizable after P1: P2 ∥ P4 ──────────┘
```

Phases 2 and 4 touch disjoint seams (audio-engine/language-lab vs
export-engine) and can run in parallel worktrees once P1 lands. P5 needs D3/D4
decided by the time P4 completes.

---

## 5. Risk register

| # | Risk | Mitigation |
|---|------|------------|
| R1 | Dependency API drift behind passing tests (likely cause of the 8 failures) | P0.2 root-cause + P0.4 version pins + byte-stability tests (P4.4) |
| R2 | Small local model produces frequent invalid output on some topics → retry storms, slow UX | Measure retry rates in P6.3; tighten prompts/templates; consider max_attempts tuning; keep human-inspectable intermediates |
| R3 | Piper voice downloads are a hidden online setup step, violating the offline promise perception | P2.5 provisioning kit + first-run checklist; document exact URLs/sizes |
| R4 | Hyphenated dirs keep generating bootstrap hacks if rename (D2) is deferred forever | Alias approach in P0.1 is stable; revisit rename only if friction recurs |
| R5 | Single-machine (Windows) development → untested cross-platform claims | Declare Windows-first support honestly (D4); add Linux rehearsal in P5.4 if claimed |
| R6 | LM Studio version coupling (API shape changes) | Pin/document tested LM Studio version; ConnectionError health check surfaced in UI (P5.3) |

---

## 6. Decision log — owner inputs gating the plan

| # | Decision | Resolution | Gates |
|---|----------|------------|-------|
| D1 | Initialize git repository now? | **RESOLVED 2026-08-24: Yes** — repo initialized on `main`, baseline commit `09681c3`, tagged `audit-2026-08-24`; secrets/OS cruft verified excluded | P0.0 ✅ done |
| D2 | Rename hyphenated engine dirs to underscore packages (requires BOOT_ROOT amendment)? | OPEN — alias/conftest approach for v1; revisit only if friction recurs | P0.1 |
| D3 | Desktop UI toolkit for v1 | **RESOLVED 2026-08-24: Tkinter** (stdlib, zero-install, low-spec-friendly); PySide6/pywebview remain v2 options | P5.2 unblocked |
| D4 | Primary packaging target OS | **RESOLVED 2026-08-24: Windows + Linux together** — both installers built and offline-verified in P5.4; adds Linux rehearsal to the packaging task | P5.4 unblocked |
| D5 | v1 scope = all four pillars as built (Learning, Language Lab, Career core), Playground deferred? | **RESOLVED 2026-08-24: All built pillars ship in v1** once Phases 0–4 correct them; Playground/Notion post-v1 | whole plan |

Repo-local git identity was set during init (`thommyshelby` / `thommyshelby@local`) because no global identity existed — owner may replace it before any push.

---

## 7. Defect register (from 2026-08-24 audit — close each in its phase)

| # | Defect | Closed by |
|---|--------|-----------|
| 1 | `podcast_script.py:287` / `bilingual.py:293` call non-existent client interface | P1.5 |
| 2 | narration auto-selects Kokoro → always raises | P2.1 |
| 3 | `podcast_audio.py:160` WAV check `[8:]` instead of `[8:12]` | P2.2 |
| 4 | `resume/schema.py:140` contact required-check dead (reads data dict) | P1.4 (validator reconciled with RESUME_SCHEMA during migration) |
| 5 | `immersion.py` drops `target_language`/`level` | P3.1 |
| 6 | `enhance()` loses Enhancement changes list on retry path | P1.4 |


---

## 8. Ship-gate status (audit 2026-08-24, post P0–P7 + career agent)

| Criterion | Status | Notes |
|-----------|--------|-------|
| E1 offline suite | ✅ | `python -m pytest` → 639 passed / 7 deselected; live deselected by default; run_checks.sh gate green |
| E2 live smoke vs LM Studio | ✅ | 2026-08-25: 6/6 passed vs real gemma-4-12B on localhost:1234 — covers ALL MODEL-FACING features. Connector network flows verified (Greenhouse 162 listings). E2b follow-ups: ffmpeg on real media, piper audio render |
| E3 zero known defects | ✅ | all six audit defects closed (P1.3–P1.5, P2.1–P2.2, P3.1) |
| E4 deterministic exports | ✅ | byte-stability suite across pdf/pptx/xlsx/docx/txt |
| E5 installable offline desktop build | 🟡 | Linux ✅ 2026-08-25 (dist/ldcc onefile, smoke-run clean vs live LM Studio); Windows ⬜ needs PyInstaller run on Windows side |
| E6 graceful resource failures | ✅ | typed FlowResult kinds w/ actionable details; voice/model errors carry provisioning hints; dead job boards log and continue |
| E7 governance current | ✅ | manifest/ledger/queue audited; MASTER_STORY/TASKS/PRODUCTION_PLAN updated 2026-08-25 |
| E8 pinned deps installable | ✅ | requirements.txt verified on CPython 3.14/Linux; fresh-machine README |

Blocking v1 tag: E5 only (Windows packaging run on real OS target).
P6.3 low-spec rehearsal requires target hardware — instructions remain in §Phase 6.
