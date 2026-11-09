# Tasks: AI Interpretation and Verified Synthesis

> Spec reconstructed from the implemented code on 2026-11-09. Checkboxes reflect what exists in the repository.

- [x] 1. Content taxonomy, rules, labels (migration `0013`, `synthesis/labels.py`)
- [x] 2. Batched synthesis service and settings (`synthesis/service.py`, `api/v1/synthesis.py`)
- [x] 3. Code checks for IDs, numbers, dates, labels, conclusions (`synthesis/checks.py`)
- [x] 4. Question focus to avoid off-topic statements (`synthesis/focus.py`, `focused.py`)
- [x] 5. Label review UI (`LabelReviewPanel.tsx`) and synthesis UI (`SynthesisPanel.tsx`, `AiInterpretation.tsx`)
- [x] 6. Hybrid Auto escalation for `summarize` (ADR-007)
- [x] 7. Evidence reports (`docs/evidence/2026-11-08-ai-ocr/REPORT.md`)
- [ ] 8. Legal-expert review of synthesised statements (not present)
- [ ] 9. AI interpretation check in the Tauri shell (reported not verified)
