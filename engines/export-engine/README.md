# Export Engine

The export-engine converts journey content into downloadable formats — DOCX, PDF, TXT, PPTX, XLSX, or audio (WAV/MP3). It takes the HTML learning experience produced by journey-core and serializes it into whatever output format the user requests, ensuring that content captured in a journey can be shared, printed, or consumed offline in any standard document or audio format. If this engine is deleted, all export and sharing capabilities vanish; the core learning journey remains intact but cannot leave the app.

---
UPDATE 2026-09-23 — Endpoint auto-detect (ollama/LM Studio) applied; quality guard (non-robotic + humor/tips) active; e2e smoke report: E2E_SMOKE_REPORT.md. Release judgment: small boring change shipped; rollback via previous archive in build/.