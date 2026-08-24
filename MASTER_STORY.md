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
A distinct journey type for language learning. Instead of HTML cards,
the output is podcast audio, generated two ways for the same
lesson/level:
- **Bilingual podcast**: two voices — a host speaking the target
  language, a second host translating word-by-word or sentence-by-
  sentence into the user's known language.
- **Immersion podcast**: the same lesson and level, but both voices
  speak only the target language, as a normal target-language podcast.

### 3. Career Development
Resume generation, upload, and enhancement. Account connections to
LinkedIn, GitHub, and a personal portfolio. The model can research a
topic on YouTube and summarize it with reference back to the source
video, and can post to LinkedIn — both only when the user explicitly
asks for it in a prompt, and only citing authenticated/traceable
sources.

### 4. Paradise Playground
Connections to external creative AI tools (Figma, Suno, Gemma, and
others) so outputs from those tools can be imported into a learning
journey, or a journey's content can be exported out to them.

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

## Open Scoping Questions

These are proposed, not decided — flag disagreement rather than silently
picking one:
- v1 cut: which of the four pillars ships first? (Recommendation: get
  Learning Journeys + export solid before Language Lab, Career Dev, and
  Paradise Playground, since the other three each depend on the same
  generation/export core working reliably first.)
- Which social/creative integrations are v1 vs. later (LinkedIn+GitHub
  are core to Career Dev; YouTube, Gmail, Figma, Suno, Notion can likely
  follow once the core engine is proven).
