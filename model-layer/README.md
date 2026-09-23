# Model Layer

The model-layer provides the AI inference foundation for the entire system. It manages the LM Studio client connection, loads and renders prompt templates, performs schema validation on model outputs, and implements retry logic with failover to ensure reliability. It is the guardrail layer that ensures all generated content is accurate, structured, and aligned with quality standards — not dependent on model size alone. If this engine is deleted, no AI generation, validation, or prompt processing is possible across any other engine.

---
UPDATE 2026-09-23 — Endpoint auto-detect (ollama/LM Studio) applied; quality guard (non-robotic + humor/tips) active; e2e smoke report: E2E_SMOKE_REPORT.md. Release judgment: small boring change shipped; rollback via previous archive in build/.