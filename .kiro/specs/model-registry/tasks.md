# Tasks: Model Registry

**Language / Ngôn ngữ:** [Tiếng Việt](../../../docs/vi/kiro/specs/model-registry.vi.md) · English

> Initially reconstructed from implemented code on 2026-11-09 and updated against the source on 2026-11-17. Checkboxes reflect source implementation, not runtime deployment or Portable release acceptance.

- [x] 1. Provider-neutral profiles and OpenAI-compatible adapter (`model_registry/`)
- [x] 2. Stage definitions and per-stage policy table (`stages.py`, migration `0010`)
- [x] 3. Hybrid Auto escalation, cost caps, usage log (`runtime.py`, `ai_limits.py`; ADR-007)
- [x] 4. Diagnostics for draft and saved profiles (`diagnostics.py`)
- [x] 5. DPAPI key store (`secret_store.py`)
- [x] 6. Admin API (`/model-registry`, `/test`, `/routes`, `/policies`, `/probe`)
- [x] 7. Two-form UI and assignment panel (`frontend/src/components/ai/*` with tests)
- [x] 8. Policy tests (`backend/tests/test_ai_policy.py`, `test_ai_registry_postgres.py`)
- [ ] 9. Real OpenAI and Gemini connection check (reported not done on 08/11/2026)
- [ ] 10. Model Registry UI check inside the Tauri desktop shell (reported not done)
- [x] 11. Local-only `ocr` stage, Ollama native vision adapter, single-attempt/300-second policy and no API escalation (`stages.py`, `runtime.py`, `ollama_local.py`)
- [x] 12. Image-based readiness probe validates expected OCR text, model digest/profile revision and vision support (`diagnostics.py`, `runtime.py`)
- [x] 13. OCR AI profile snapshot validation before result apply; embedding model/index workflow remains separate

Implementation review: `docs/evidence/qwen35-upgrade/REVIEW_FIXES_2026-11-17.md`. A real `qwen3.5:4b` model was exercised locally, but no claim is made that an operational Registry or Portable r4 has been reconfigured.
