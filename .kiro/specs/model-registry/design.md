# Design: Model Registry

> Initially reconstructed from implemented code on 2026-11-09 and updated against the source on 2026-11-17. This is not a historical Kiro-generated spec. Evidence is cited by repository path.

## Components

| Concern | Files |
|---|---|
| Profiles and routes | `backend/app/model_registry/profiles.py`, `runtime.py` |
| Stages and policy | `model_registry/stages.py`, migration `0010_ai_policy`, `backend/app/ai_limits.py` |
| Provider adapter | `model_registry/adapters/base.py`, `openai_compatible.py` |
| Local vision adapter | `model_registry/adapters/ollama_local.py` |
| Diagnostics | `model_registry/diagnostics.py` |
| Key storage | `model_registry/secret_store.py` |
| Stage selection in the pipeline | `backend/app/workflow/ai_selection.py` |
| API | `backend/app/api/v1/admin.py` (`/model-registry*`) |
| UI | `frontend/src/components/ai/` (`ModelProfilesPanel`, `AssignmentsPanel`, `ProfileEditor`, `CheckResult`, `aiConfig.ts`) |
| Config templates | `configs/model-registry.example.yaml`, `ai-runtime.env.example`, `security-policy.example.yaml` |
| Guidance | `docs/ai-model-recommendations.md`, `docs/HUONG_DAN_SU_DUNG_VA_CAU_HINH_AI.md` |

## Routing

```mermaid
flowchart LR
  S[Stage call] --> O{Stage is ocr?}
  O -->|yes| V[Ollama local vision only, one attempt]
  O -->|no| M{Mode}
  M -->|LOCAL| L[Local profile only]
  M -->|API| P[Primary local profile]
  P -->|checks fail or deep analysis| E[Escalation API profile, once]
  L --> X[Egress and cost guard]
  P --> X
  E --> X
  X --> A[Adapter: OpenAI-compatible]
  A --> U[ai_usage_events]
  V --> I[Native Ollama vision adapter]
  I --> U
```

## Decisions

- Hard rules (egress, escalation, local-only stages) live in code, not in prompts or per-profile switches.
- Endpoint `localhost` is interpreted from the backend host, not from the client.
- Saving a profile that fails testing is possible only with explicit consent and never makes it usable.
- `ocr` is always local-only, requires a tested Ollama vision-capable profile, never escalates to an API, permits one attempt and allows a stage timeout up to 300 seconds. The background worker has its own total-task limit and is opt-in (`EVIDENCE_OCR_AI_ENABLED=false` by default).
- Changing a text-generation/OCR profile does not rebuild embeddings. Changing the embedding model uses the separate index job and preserves the serving index until validation succeeds.

## Known limits

The Model Registry UI report states that real OpenAI and Gemini calls were not verified and the Tauri shell was not checked (`docs/evidence/2026-11-08-model-registry-ui/REPORT.md`). The 2026-11-17 audit exercised Qwen3.5 text and vision locally and verified the vision profile snapshot; it did not configure the operational Registry, rebuild Portable r4 or verify on another Windows machine (`docs/evidence/qwen35-upgrade/REVIEW_FIXES_2026-11-17.md`).
