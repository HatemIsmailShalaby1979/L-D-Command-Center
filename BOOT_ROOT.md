> **Internal development artifact** — documents the AI-assisted build process for this project.

# BOOT_ROOT — Workspace Bootstrap Protocol

Read this before creating the first file. This defines the physical
structure every agent must respect so duplication becomes structurally
hard, not just against the rules.

## Folder Skeleton

```
/
├── CONSTITUTION.md          # governance — read first, always
├── MASTER_STORY.md          # product vision — read second
├── BOOT_ROOT.md             # this file
├── AGENT_LOG.md             # append-only session ledger
├── FILE_MANIFEST.md         # every file + its one-line reason for existing
├── TASKS.md                 # shared task queue (see Coordination Protocol)
├── /engines/                # one subfolder per independent engine
│   ├── /journey-core/       # topic → interactive HTML + quiz + eval
│   ├── /export-engine/      # journey content → docx/pdf/txt/pptx/xlsx
│   ├── /audio-engine/       # text → audiobook/podcast, TTS orchestration
│   ├── /language-lab/       # bilingual + immersion podcast generation
│   ├── /career-engine/      # resume gen/enhance, LinkedIn/GitHub/portfolio
│   └── /playground-bridge/  # Figma/Suno/Gemma/etc import-export
├── /model-layer/            # LM Studio client, prompt templates, schema
│                             # validation, retry logic — the guardrail layer
├── /storage/                # local persistence, Notion SOP sync
├── /desktop-shell/          # packaging/installer, the actual desktop app
└── /docs/                   # anything not governance and not code
```

An engine folder is created only when `MASTER_STORY.md` names it. No
speculative folders "for later."

## FILE_MANIFEST.md Format

One line per file, appended when the file is created:
```
/engines/journey-core/generator.py — generates HTML journey cards from a
topic+level spec; deleting this removes the core generation loop
```

Before creating any file, an agent greps this manifest for the intended
path and for near-duplicate purposes. If a close match exists, the task
is to extend that file, not create a new one.

## Multi-Agent Coordination Protocol

You've mentioned wanting Claude Code and opencode (with OpenRouter/Nvidia
agents) running in separate terminals against this same workspace. The
pattern below is what's actually holding up in practice right now —
full automatic handoff between *different* agent tools isn't reliable
yet anywhere, this workspace included:

1. **One git worktree per agent.** Never two agents on the same branch
   at the same time. `git worktree add ../ldcc-agent-a feature/journey-core`
   gives each agent its own physical directory and branch.
2. **`TASKS.md` is the only handoff surface.** A flat list, one task per
   line, each with a status: `OPEN`, `CLAIMED:<agent>`, `DONE:<agent>`,
   `BLOCKED:<reason>`. An agent claims a task by editing its status
   before starting — this is the entire coordination mechanism. No agent
   works on a task it hasn't claimed.
3. **No agent merges its own worktree.** Claiming, working, and logging
   to `AGENT_LOG.md` happens inside the worktree. Merging back to main
   is a separate, reviewed step — by you, or by a single designated
   "integrator" session, never automatically.
4. **Conflicts are a signal, not a bug to route around.** If two agents'
   worktrees touch the same file, that's `FILE_MANIFEST.md` or engine
   boundaries being unclear — fix the boundary, don't script around the
   conflict.

This is deliberately low-tech. It's the version of "automatic handoff"
that won't silently corrupt work while you're not watching both
terminals.

## Agent Startup Sequence

Every session, in order:
1. Read `CONSTITUTION.md`
2. Read `MASTER_STORY.md`
3. Read `FILE_MANIFEST.md`
4. Read `TASKS.md`, claim or continue a task
5. Do the work
6. Update `FILE_MANIFEST.md` for any new file
7. Append to `AGENT_LOG.md`
8. Update `TASKS.md` status
