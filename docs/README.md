# Docs

The docs directory holds anything that is not governance (CONSTITUTION.md, MASTER_STORY.md, BOOT_ROOT.md) and not code — design notes, research summaries, architecture decision records, and any other reference material that supports the project but doesn't belong in a specific engine. If this directory is deleted, only supplementary documentation is lost; the engines and their responsibilities remain unchanged.

---
UPDATE 2026-09-23 — Endpoint auto-detect (ollama/LM Studio) applied; quality guard (non-robotic + humor/tips) active; e2e smoke report: E2E_SMOKE_REPORT.md. Release judgment: small boring change shipped; rollback via previous archive in build/.

---
UPDATE 2026-10-03 — Ollama is a first-class inference backend: local servers are discovered (`discover_local_servers`), their models fill a new Server + Model picker pair in the shell, and the capability probe grades and attributes either runtime (Ollama or LM Studio). Additive only — `LmStudioClient` and `scan_local_endpoints` are unchanged and pinned by regression tests. Offline suite: 1122 passed / 7 live deselected. Release note: RELEASE_NOTE_2026_10_03.md.
