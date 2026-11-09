# Tasks: Model Registry

> Spec reconstructed from the implemented code on 2026-11-09. Checkboxes reflect what exists in the repository.

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
