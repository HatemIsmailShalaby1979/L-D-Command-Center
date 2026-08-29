> **Internal development artifact** — documents the AI-assisted build process for this project.

# L&D Command Center — Master Story

This is the canonical description of what this project is. Any agent
starting a new session reads this instead of asking the owner to
re-explain the product. If this file and a chat prompt disagree, this
file is the source of truth until the owner amends it.

## Vision

A free, offline-first, desktop-only Learning & Development command
center. One local model (via LM Studio) is the sole generation brain for
every output the app produces — text, interactive HTML, documents, and
audio. It runs on modest, older hardware, not just modern laptops.
Nothing about it depends on a hosted API or a subscription.

## The Four Pillars

### 1. Learning Journeys
The core loop: user names a topic, the app generates an interactive HTML
learning experience — cards, quizzes, evaluations — for that topic at a
chosen depth/level. A journey can be revisited, modified, and extended
over time. Any journey's content can be exported to any format: DOCX,
PDF, TXT, PPTX, XLSX, or audio (audiobook/podcast, WAV/MP3). Within a
journey, content can also be captured as an SOP and stored in Notion,
so a journey can grow into a full knowledge base of SOPs specific to
that user's work.

### 2. Language Lab ("Speak Like an Alien" mode)
The flagship pillar. A distinct journey type for language learning:
podcast audio generated two ways for the same lesson/level, PLUS the
interactive layer that makes it the most powerful tool in the app —
grammar cards with drills, vocabulary flashcards and quizzes, listening
comprehension tied to exact podcast segments, and final evaluations:
- **Bilingual podcast**: two voices — a host speaking the target
  language, a second host translating word-by-word or sentence-by-
  sentence into the user's known language.
- **Immersion podcast**: the same lesson and level, but both voices
  speak only the target language, as a normal target-language podcast.

### 3. Career Development
Resume generation, upload (PDF/DOCX/TXT with confidence flags),
enhancement with inspectable changes, and export to PDF/DOCX. Account
connections to LinkedIn and GitHub (profile → contact fields, repos →
projects list). A job-board search agent hunts Greenhouse, Ashby, and
RemoteOK for matching roles, ranks by keyword hits, and prepares full
application packages (tailored resume + cover letter + listing reference)
for each listing — the agent finds and prepares, the human submits.
A saved-search watchlist reports only new listings on a configurable
timer. YouTube research and LinkedIn posting available when the user
explicitly asks.

### 4. Paradise Playground
The media playground — a kids' area, an opera for musicians. Users import
ANY media (images, audio, video, documents) from local files or from any
FREE tool or AI service they hold an account with — including limited
free quotas (Suno, Figma, Gemini, Hugging Face Spaces, keyless services) —
generate with those tools, merge and edit everything locally, and export
anywhere, including back into journeys and lessons. The app's job is the
playground itself plus a connector hub that finds a free path per file
type; cloud or local origin does not matter.

## Core Engine Philosophy

- One local model, LM Studio-hosted, 3B+ parameters, tool-calling
  capable, does all generation, analysis, editing, and summarization of
  documents.
- The app must not depend on model size for quality. Skills, plugins,
  and guardrails engineered into the app itself are what prevent
  hallucination and instability — not a bigger model. See
  `CONSTITUTION.md` §3.
- Any generated topic, any format, offline, free. That promise is the
  product.

## Platform Constraints

- Desktop-only, packaged/installable, no cloud dependency required to
  function.
- Must run on low-spec hardware — not gated behind "modern laptop"
  requirements.
- Production-ready is the bar, not a prototype.

## Workspace History (context for future agents)

This is a deliberate fresh start in a new, empty workspace. Earlier
attempts in this problem space exist (an event-sourced L&D engine, a
Windows desktop app using local Ollama + Piper TTS, an ops platform with
multiple micro-engines) and are **not** to be imported, copied, or
refactored into this workspace. Lessons from them inform this build;
their code does not.

## Resolved Scoping Decisions (formerly "Open Questions")

All resolved as of 2026-08-25:
- **v1 scope**: All four pillars ship in v1 — Learning Journeys, Language
  Lab (flagship), Career Development (with job-board agent), Paradise
  Playground (universal media + connector hub). See D5 in PRODUCTION_PLAN.
- **Social/creative integrations**: LinkedIn + GitHub are core to Career
  Dev (v1). YouTube research, LinkedIn posting, Notion, Figma, Suno
  included as keyless connectors in Playground (v1). Gmail deferred post-v1.
- **UI toolkit**: Tkinter (D3 resolved).
- **Target OS**: Windows + Linux together (D4 resolved).
- **Git init**: Done, baseline tagged audit-2026-08-24 (D1 resolved).
- **D9 — Hardening phase**: Phase 8 (stabilization & polish) entered
  2026-08-26. No new features until Phase 8 closes. Phase 8 closed
  2026-08-27 — all exit criteria met: offline suite green (730 passed,
  93.6% coverage), live generation verified across Journeys/LessonPack/
  Career flows, loading indicators and error messages confirmed in UI.
