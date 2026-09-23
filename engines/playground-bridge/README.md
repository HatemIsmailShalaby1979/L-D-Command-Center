# Playground Bridge

The playground-bridge engine manages connections to external creative AI tools such as Figma, Suno, Gemma, and others, enabling bidirectional import-export of content. It allows outputs from these external tools to be imported into a learning journey, and conversely allows a journey's content to be exported out to them. If this engine is deleted, all integrations with external creative AI platforms and their corresponding import-export functionality are lost.

---
UPDATE 2026-09-23 — Endpoint auto-detect (ollama/LM Studio) applied; quality guard (non-robotic + humor/tips) active; e2e smoke report: E2E_SMOKE_REPORT.md. Release judgment: small boring change shipped; rollback via previous archive in build/.