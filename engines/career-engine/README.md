# Career Engine

The career-engine handles resume generation, upload, and enhancement, along with account connections to LinkedIn, GitHub, and personal portfolio platforms. It enables the model to research topics on YouTube and summarize them with traceable source references, and can post to LinkedIn — all only when the user explicitly requests it in a prompt, and only citing authenticated and traceable sources. If this engine is deleted, all career development features including resume management and social platform integrations are lost.

---
UPDATE 2026-09-23 — Endpoint auto-detect (ollama/LM Studio) applied; quality guard (non-robotic + humor/tips) active; e2e smoke report: E2E_SMOKE_REPORT.md. Release judgment: small boring change shipped; rollback via previous archive in build/.