# Design: AI Interpretation and Verified Synthesis

> Spec reconstructed from the implemented code on 2026-11-09. This is not a historical Kiro-generated spec. Evidence is cited by repository path.

## Components

| Concern | Files |
|---|---|
| Orchestration, batching | `backend/app/synthesis/service.py` |
| Question focus | `synthesis/focus.py`, `synthesis/focused.py` |
| Code verification | `synthesis/checks.py` |
| Labels and groups | `synthesis/labels.py`, migration `0013_content_groups` |
| API | `backend/app/api/v1/synthesis.py` |
| Stage routing | `workflow/ai_selection.py`, `model_registry/runtime.py` |
| UI | `frontend/src/components/AiInterpretation.tsx`, `SynthesisPanel.tsx`, `LabelReviewPanel.tsx`, `AiAnswerView.tsx` |

## Sequence

```mermaid
sequenceDiagram
  participant U as UI
  participant S as synthesis/service
  participant M as summarize model
  participant C as checks.py
  U->>S: question + result set
  S->>S: select focused evidence within budgets
  S->>M: question + permitted evidence
  M-->>S: statements with evidence IDs
  S->>C: verify IDs, numbers, dates, labels, conclusions
  C-->>S: keep / drop / mark unverified
  S-->>U: answer, unsupported parts, evidence, checks
```

## Decisions

- The model never supplies quotes, node IDs or page numbers; evidence cards are hydrated from stored text.
- Verification is rule-based and cannot prove a statement is legally correct.
- Local runs 10/10 and API runs 11/11 (including three real API calls, 12/12 statements passing checks) were reported in the G4 session; they were not re-run when this spec was written.
