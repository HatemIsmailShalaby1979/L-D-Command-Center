# PLAYGROUND_AND_LANGUAGE_LAB_PLAN.md — Phase 7

Status: ACTIVE (owner-directed expansion, 2026-08-24). This plan turns two
owner mandates into claimable work:

1. **Paradise Playground** = a universal media playground ("a kids' area,
   an opera for musicians"): import/export ANY media type, edit and merge
   locally, and reach ANY free tool or AI service the user has an account
   with — free tiers and keyless services first. The app does not care
   whether media starts local or cloud; it cares that the user can find a
   free path for the file type and merge everything here.
2. **Speak Like an Alien** = the flagship. Keep the two-voice podcast, add
   interactive grammar + vocabulary cards, drills, and evaluations until it
   is the most powerful tool in the app.

Task IDs P7.x are canonical in TASKS.md.

---

## Part A — Do small local models need "skills/plugins" to drive? (Answer)

**No plugin system is needed — the driving wheel already exists.** Every
generation runs through the Generation Pipeline
(model-layer/pipeline.py): prompt template in, schema-validated artifact
out, feedback retry between. A 3B and a 14B load the same templates; the
guardrails — not the model size — decide whether output is usable
(CONSTITUTION §3). What small models genuinely change is *how often* the
retry loop fires and which tasks are realistic at all.

So instead of plugins we ship **capability profiles** (P7.1):

| Task | Comfortable from | Notes |
|------|------------------|-------|
| Journey cards / quizzes | ~7B | JSON discipline dominates |
| Resume generate/enhance | ~7B | long-form coherence |
| Bilingual translation | ~7B + mandatory verify pass below 14B | fidelity is correctness (§3) |
| Grammar explanations | ~12B recommended | weakest spot on 3B |
| Podcast dialogue | ~7B | creativity + schema |
| Summaries/classification | ~3B | easy wins |

`capabilities.py` ships a one-shot **probe**: tiny calibration prompts per
profile run against whatever model LM Studio has loaded; verdicts persist
via Storage; the shell health bar shows "ready / degraded: translations
may need review". No magic — just honest expectations wired into UX.

---

## Part B — Paradise Playground

### B0 Principles (ruthless prioritization)
1. **Keyless before keys, keys before scrapes.** A connector that works
   with zero accounts beats one needing OAuth beats one needing a browser.
2. **Editing is local, always.** Merging/trimming/mixing happens offline
   via ffmpeg (already a proven dependency) — cloud only for generation.
3. **One seam, N services.** Adapters implement one interface; the Hub
   never learns about individual vendors.
4. **Free-tier reality documented per adapter** (quota notes surface in UI).

### B1 Media Workspace (P7.7) — the local editing core
Pure-function module over ffmpeg:
`ingest(path)` normalizes anything → storage artifact;
`trim/concat/overlay/mix/volume/convert/export` as composable ops with a
plan→execute model so edits are testable without a display. Images get
resize/pad/format conversion (ffmpeg covers this too).

### B2 Import Inbox (P7.8)
A watch-folder. Services with free web tiers but no API (Suno, Udio,
Runway, Gemini web exports…) become drag-and-drop citizens: drop files →
normalized into `storage/media/*`. This single feature makes "any service
with a free quota" true even where APIs don't exist.

### B3 Connector Hub (P7.9–P7.11)
```python
class Connector(Protocol):
    name: str
    def capabilities(self) -> Capabilities      # file types, ops, quota notes, auth kind
    def send(self, artifact, op) -> Job         # submit generation job
    def poll(self, job) -> Result               # artifact bytes or progress
```
v1 roster (all free):
| Adapter | Auth | Unlocks |
|---|---|---|
| **HF Spaces** (`gradio_client`) | none | thousands of Spaces: image gen, audio/music gen, video, upscalers, TTS |
| **Pollinations** | none | keyless image generation |
| **Figma REST** | free account token | import frames/designs as PNG/SVG assets |

Storage gains `secrets/*.secrets` entries per connected account; quota
notes render in the Playground tab (P7.12).

### B4 What users can actually do (v1 promises)
- Drop any image/mp3/wav/mp4/pdf → workspace library.
- Trim/join/mix audio into lesson material; convert formats.
- Send an artifact to a keyless generator; result lands back in the inbox.
- Push finished media into a Journey/LessonPack or export anywhere.

---

## Part C — Speak Like an Alien power-up

### C1 LessonPack (P7.2) — one generation, whole lesson
Pipeline templates produce ONE validated JSON pack per (topic, language,
level):
`dialogue segments` (feeds today's two-voice rendering) + `vocab_cards[]`
(term, reading, translation, example) + `grammar_cards[]` (point,
explanation, drill items) + `evaluation[]` (mixed item types).

### C2 Interactive renderer (P7.4)
New LanguageLabRenderer following the JourneyRenderer pattern:
flashcards (flip/self-grade), multiple-choice vocab quizzes, fill-in-blank
and transformation grammar drills, listening items that play the exact
podcast segment (per-segment audio already exists via the assembly seam),
and a final evaluation screen with score breakdown.

### C3 Correctness discipline (P7.3)
Grading order: **deterministic graders first** (exact/regex/normalization
for fill-in-blank & translation typing), **model-judge second** producing
inspectable verdict artifacts (reuse of the P3.2 pattern), and the existing
bilingual fidelity verification extended to grammar explanations. Nothing
is trusted because the model said so.

### C4 Spaced repetition lite (P7.6)
SM-2 scheduling persisted through Storage preferences/artifacts — reviews
survive restarts, stay offline, stay exportable.

---

## Sequencing
LL first (flagship value, zero new deps): C1→C3→C2→C5→C4 = P7.2→P7.6.
Playground after: P7.7/P7.8 (local core) → P7.9 (gradio_client unlock) →
P7.10/P7.11 → P7.12 UI. Capability probe (A) can land anytime; do it first
(it's small and informs everything).

## Risks
- gradio_client Space churn → adapter pins Space IDs, capabilities() hides dead ones.
- Small-model grammar quality → capability probe warns; judge-verdict keeps humans in charge.
- ffmpeg variance across OS builds → pin system requirement in README; tests use generated fixtures.
