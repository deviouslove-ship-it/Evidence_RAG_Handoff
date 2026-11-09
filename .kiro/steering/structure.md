---
inclusion: always
---

# Repository Structure

> Steering reconstructed from the repository layout on 2026-11-09. It is not a historical Kiro steering file. Vietnamese translation: `docs/vi/kiro/steering/structure.vi.md`.

```text
backend/app/
  api/v1/         HTTP routes: auth, user, admin, comprehensive, effectivity, synthesis
  auth_acl/       passwords, RBAC/ABAC policy, sessions
  documents/      intake, conversion, native PDF, OCR, tree parser, spans, review, management_*
  effectivity/    rule reader, resolver, store, AI proposals
  evidence/       evidence mapping and validators
  memory/         in-RAM session memory
  migrations/     paired SQL migrations and runner
  model_registry/ profiles, stages, runtime, adapters, diagnostics, secret store
  storage/        search, comprehensive search, embeddings, citations, relevance
  synthesis/      focus, checks, labels, service
  vietnamese_nlp/ Unicode normalisation, legal citation parser
  workflow/       fixed pipeline, chat answer, AI selection
backend/tests/    pytest suites
frontend/src/     pages/, components/ (+ components/ai/), api/, desktop/, theme/
src-tauri/        Tauri 2 shell for Windows USER
deploy/           windows/ notes, portable/ package source, lan-portable/ offline LAN package source
scripts/          verify, start-local-stack, packaging, import, embedding, benchmark, OpenAPI export
evaluation/       public corpus, search eval, coverage and rerank harness (fictional cases)
configs/          example configuration only (no secrets)
tools/            egress check, source hash check, footprint
docs/             SRS, handoff files, ADRs, runbooks, evidence reports, OpenAPI
docs/en, docs/vi  English and Vietnamese counterparts of key documents
.kiro/            Kiro permissions, specs, steering, hooks
.stitch/          UI design notes from Stitch
```

## Conventions

- New backend feature: route in `api/v1/`, logic in its domain package, SQL in a new paired migration, tests in `backend/tests/`.
- New admin UI: page in `frontend/src/pages/`, components in `components/`, API calls in `api/client.ts`, types in `types.ts`.
- Documents: the original file keeps its language. Its counterpart is added beside it: `README.en.md`, `*.vi.md` / `*.en.md`, or under `docs/en/` and `docs/vi/`. Do not overwrite one language with the other.
- Files Kiro reads in `.kiro/specs` and `.kiro/steering` stay in English; Vietnamese translations live in `docs/vi/kiro/`.
- Generated or runtime data stays out of Git (`data/`, `backups/`, `.agents/`, large binaries; see `.gitignore`).
- Do not edit `.kiro/settings/permissions.yaml` unless the project owner asks.
