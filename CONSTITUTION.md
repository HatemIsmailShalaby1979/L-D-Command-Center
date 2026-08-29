> **Internal development artifact** — documents the AI-assisted build process for this project.

# L&D Command Center — Engineering Constitution

This file outranks convenience, speed, and any single session's judgment.
If any prompt, agent instinct, or shortcut conflicts with this file, this
file wins. Every agent (human or AI) working in this workspace reads this
before touching anything.

## 1. Prime Directives

1. **No duplicate files, ever.** Before creating anything, check
   `FILE_MANIFEST.md` and the folder tree. If something close already
   exists, extend it — do not create a sibling, a `v2`, or a `-new`.
2. **No temp files.** No `scratch.py`, `test2.js`, `untitled.md`,
   `notes_old.txt`. Anything transient lives in a git-ignored `/tmp`
   working directory and is deleted before the session ends. If it can't
   be deleted cleanly, it shouldn't have been created outside `/tmp`.
3. **No unapproved file creation.** Every new file gets a one-line reason
   recorded in `FILE_MANIFEST.md` the moment it's created. If the reason
   can't fit in one sentence, the file isn't ready to exist yet — the
   design isn't finished.
4. **No god files, no god modules.** One file = one responsibility. The
   moment a module is doing two unrelated jobs (e.g. HTML generation AND
   TTS orchestration), it gets split — before it grows further, not after.
5. **Every file explains itself.** Top-of-file header comment: what this
   file is, why it exists, what breaks if it's deleted. Non-obvious logic
   gets an inline comment explaining the *reasoning*, not a restatement
   of what the code already says.

## 2. The Agent Ledger

Every agent session — Claude Code, opencode, any local or remote agent —
opens by reading `AGENT_LOG.md` and closes by appending an entry before
exiting. No entry, no trust: an unlogged session's work is treated as
unverified until someone checks it.

Entry format:
```
## [YYYY-MM-DD HH:MM] — <agent/model>
Task: <what was assigned>
Touched: <files created/modified/deleted>
Why: <the reasoning, not just the diff>
Left undone: <what's incomplete or needs review>
```

## 3. Engineering Discipline

- **Chunked, not monolithic.** The system is built as independent engines
  with explicit boundaries (see `MASTER_STORY.md`). Any single engine can
  be deleted and rebuilt without breaking its neighbors. If deleting one
  file cascades failures across unrelated features, the architecture is
  wrong and gets fixed before more code is added.
- **Guardrails over model size.** The reasoning core is a small local
  model (target: 3B+, tool-calling capable, via LM Studio). Correctness
  comes from the scaffolding around it, not from trusting one free-form
  generation pass:
  - deterministic templates for anything structural (HTML card layout,
    export formats, podcast script structure)
  - schema-validated model outputs with retry-on-failure, not
    best-effort parsing
  - human-inspectable intermediate artifacts for anything with a
    right/wrong answer — quiz answer keys, translations, factual content
  - this applies with extra weight to the language-learning podcasts:
    word-for-word/sentence-for-sentence translation is a correctness
    problem, not a creative one, and gets treated like one.
- **Ambiguity escalates — it never gets silently guessed.** If a spec is
  unclear, the agent stops and asks rather than shipping a plausible
  guess.
- **Security baseline, from day one.** No credentials, tokens, or API
  keys in code or commits — ever. Every third-party connection (LinkedIn,
  GitHub, Gmail, YouTube, Notion, Figma, Suno) reads from a secrets file
  that is git-ignored *before* the first integration is written, not
  added as an afterthought.

## 4. Definition of Done

A task is done when: it works, it has at least one test or a documented
manual verification step, `AGENT_LOG.md` has an entry for it,
`FILE_MANIFEST.md` is current, and nothing temporary was left behind.

## 5. Amendments

This file can change — but only via an explicit, logged decision by the
project owner. No agent edits this file to make its own task easier.
