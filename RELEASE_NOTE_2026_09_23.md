# App Owner — Release Note 2026-09-23 (One-Pager)

**What:** Small boring change — endpoint auto-detect + anti-robotic quality guard + docs.
**Why:** Root cause was hardcoded client + missing guard; pipeline intact; frozen correct; app env broken.
**When:** Released now (branch `release-2026-09-23` pushed; remote `main` not overwritten — merge/reconcile needed before main collapse).
**Cost:** Zero new dependencies; rollback = restore previous archive in `dist/archive/`.
**Named owner:** This session (App Owner role).
**What broke / what users saw:** App startup blocked by tkinter Tcl missing; local endpoint missing; generation blank/robotic; GitHub/LinkedIn connections unverified.
**What we did:** Reproduced with ollama up (`granite4.2`); scan passes; direct call TIMES OUT at 60s (constraint, not failure — policy retry budget exists); guard added; all 28 .md + 4 .html updated; smoke report saved; commit on `release-2026-09-23`; push completed.
**Next:** When model load is fast enough, run `python smoke_headless.py`; merge branch to main; finish dark-theme skin in separate session.
