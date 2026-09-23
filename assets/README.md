# assets/

Optional branding assets for the app.

- `et_face.png` — the E.T. persona logo (friendly alien, original
  artwork: big warm eyes, gold/green palette; inspired in spirit,
  never a copy of any studio's trade dress). The UI works without
  this file — panels use the 👽/🛸 emoji fallbacks — so dropping a
  128×128 PNG here simply upgrades the header art wherever
  `ET_FACE_ASSET` is referenced.

---
UPDATE 2026-09-23 — Endpoint auto-detect (ollama/LM Studio) applied; quality guard (non-robotic + humor/tips) active; e2e smoke report: E2E_SMOKE_REPORT.md. Release judgment: small boring change shipped; rollback via previous archive in build/.