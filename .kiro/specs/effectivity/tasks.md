# Tasks: Effectivity

> Spec reconstructed from the implemented code on 2026-11-09 (updated 2026-11-11). Checkboxes reflect what exists in the repository. Figures come from the cited reports and were not re-run.

- [x] 1. Migration `0011_effectivity` with down script (tables, enum value `replaced`, trigger)
- [x] 2. Rule reader (`effectivity/extract.py`)
- [x] 3. Resolver with hard rules and tests (`resolver.py`, `test_effectivity_rules.py`)
- [x] 4. Target matching (`store.py::match_target`)
- [x] 5. Review, attestation, revoke and snapshot API (`api/v1/effectivity.py`)
- [x] 6. Clause-level relations (`node_paths.py`, `documents/node_effectivity.py`, `test_effectivity_node_scope_pg.py`)
- [x] 7. AI relation proposals, propose-only (`effectivity/ai.py`)
- [x] 8. Review UI and badges (`EffectivityReviewPanel.tsx`, `EffectivityBadges.tsx`)
- [x] 9. Extraction script (`scripts/extract_effectivity.py`)
- [ ] 10. Subject-matter-expert confirmation of the relation reference set (not present)
- [ ] 11. UI picker for unresolved clause targets (not available; see user guide)
