# Tasks: Embedding Management

> Spec reconstructed from the implemented code on 2026-11-09. Checkboxes reflect what exists in the repository.

- [x] 1. Dimension-free vector table and per-model HNSW index (migration `0012`)
- [x] 2. Embedding build script (`scripts/build_embeddings.py`)
- [x] 3. Jobs table and index lifecycle columns (migration `0014`, with down script)
- [x] 4. Preflight (`storage/embedding_jobs.py::preflight`)
- [x] 5. Job control and worker with backoff (`create_job`, `control_job`, `EmbeddingWorker`)
- [x] 6. Admin API (`api/v1/admin.py`)
- [x] 7. Admin UI (`EmbeddingManager.tsx`, `EmbeddingManager.test.tsx`)
- [x] 8. Report recorded (`docs/evidence/2026-11-07-embedding-admin/REPORT.md`)
- [ ] 9. Re-run the embedding switch with a real second model and record the result (not re-run when this spec was written)
