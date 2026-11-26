**Language / Ngôn ngữ:** [Tiếng Việt](REPORT.md) · English

English counterpart of `docs/evidence/2026-11-07-embedding-admin/REPORT.md`. The Vietnamese file is the original.

# Embedding management in the Admin Portal — 2026-11-07

## Scope

An administrator changes, adds, or upgrades an embedding model entirely in the UI; the system
rebuilds the vectors for approved Article (Điều)/Clause (Khoản)/Point (Điểm) nodes with a
background job, and keeps the old index serving search until the new index has been checked
and switched in a single transaction.

Reused: migration 0012 (a vector column whose dimension is not fixed, and the index status),
`storage/embeddings.py` (split into shared steps), `scripts/build_embeddings.py` (calls the
same steps), and Model Registry (profiles, probe, endpoint policy, audit). No new runtime
dependency is added (only stdlib, asyncpg, httpx, and pgvector, which are already present).

## Components

| Component | Contents |
|---|---|
| `migrations/0014_embedding_jobs.sql` (+ `.down.sql`) | Table `embedding_jobs`; the index status gains `paused` and `failed`; columns `last_error`, `verified_at`, `activated_at`, `retired_at`. No data is deleted. |
| `storage/embeddings.py` | The shared set of nodes that must be covered; open or reuse an index; HNSW `CONCURRENTLY` (REINDEX if it is broken, no DROP); `halfvec` for 2001–4000 dimensions; an integrity check; switch the index in one transaction. |
| `storage/embedding_jobs.py` | The preflight check, creating a job after confirmation, pause/resume/retry/cancel, and `EmbeddingWorker` running inside the API process. |
| `storage/comprehensive.py` | The question vector is always taken from the profile of the index that is active; if the model differs from the index, the semantic channel pauses and says so clearly. |
| `model_registry/runtime.py` | `EmbeddingOutcome.error` (an error code with the detail hidden); the embedding policy for an external API; a background job spaces itself out, in place of the interactive cool-down. |
| `api/v1/admin.py` | `GET /admin/embeddings`, `POST /admin/embeddings/preflight`, `POST /admin/embeddings/jobs` (requires `confirmed: true`), `POST /admin/embeddings/jobs/{id}/{pause|resume|retry|cancel}`; every operation writes an audit record. |
| Frontend | The model role on the profile form (embedding is separate, with an optional dimension count); the section "Embedding (tìm theo nghĩa)" (Embedding (search by meaning)) under AI & Kiểm toán (AI & Audit). |
| Portable package | `config/evidence.env`: `EVIDENCE_REMOTE_EMBEDDING_ALLOWED=false`, `EVIDENCE_EMBEDDING_WORKER=true`; README section 5a. The new code is in `backend/app`, so `package-portable.ps1` packages it on its own. |

## Flow

1. A profile with the role `embedding` (local, or `public` if policy allows it).
2. Check the model: role, approval, policy, address/key, `GET /models`, a trial vector (finite
   and not 0), the required dimension count, storage (`vector` ≤ 2000, `halfvec` ≤ 4000), and
   whether administrative documents (văn bản) are allowed to be sent outside (a `public`
   profile). It returns the number of nodes in the corpus, how many already have a vector for
   this model, how many must be created, and a rough time estimate.
3. Confirmation → the job is `queued`, and the `embedding` route of the current mode points at
   the profile that was chosen (the embedding stage only; the other stages are unchanged).
4. The worker: an advisory lock so that only one job runs; work proceeds by batch; a heartbeat
   every 15 seconds; a `running` job with no heartbeat for more than 60 seconds is placed back
   on the queue; a clean server shutdown requeues it immediately. A transient error: spacing of
   15/30/60/120/120 seconds, and a smaller batch on timeout; 5 times in a row → `failed`. A
   configuration error (the profile changes model partway through, it is not yet approved, the
   key is missing…) → `failed` immediately.
5. When the nodes are finished: build HNSW, check (enough nodes, the correct dimensions, a
   valid HNSW, vectors present, and one sample vector rebuilt with cosine ≥ 0.95), and switch
   the index; the old index becomes `retired`, and its vectors and HNSW are kept.

A node approved after the switch is reported as "N nút mới chưa có vector" (N new nodes have
no vector) and is filled in by a `catch_up` job on the index that is in use. Switching back to
an old model reuses that model’s `retired` index.

## Test results (dev machine, 2026-11-07)

- `scripts/verify.ps1 -ProgramsRoot E:\Programs` passed 12/12 (`verify/summary.json`): backend
  **225 passed** with real PostgreSQL, and no test was skipped (previously 218); frontend
  **77 passed** (previously 74); lint, mypy, OpenAPI, migrations, the source-code policy, and
  the build all passed.
- `test_embedding_jobs_postgres.py` (a temporary schema, 3–4 FICTIONAL (HƯ CẤU) nodes, a fake
  embedding service over HTTP transport): the first index is created; switching to a model
  with a different dimension count, with the service failing after one batch → the job is
  `failed` after 5 attempts, and the old index is still serving (an 8-dimension question
  vector); retry → it continues from the vectors already saved, switches (12 dimensions), and
  the old index is `retired` and keeps 3 vectors and a valid HNSW; a new node → `catch_up`,
  pause/resume; going back to the old model reuses the vectors (only 1 node is sent); a job
  left unfinished by a dead process is recovered; an unstable model →
  `EMBEDDING_SAMPLE_MISMATCH`, and there is no switch; 2100 dimensions use `halfvec` and can
  be searched; 4100 dimensions are rejected at the check step; the `build_embeddings` script
  still runs. At the end of the test no vector had been deleted. API tests: permissions (USER
  403), missing confirmation 422, an operation in the wrong state 409, and the audit is
  complete.
- A real model (`smoke_real_model.py`, result `smoke-real-model.json`): local Ollama,
  `qwen3-embedding:0.6b`, 12 FICTIONAL (HƯ CẤU) nodes, through the HTTP API and the background
  worker. Run 1: 1024 dimensions, the worker was stopped partway through (the job went back to
  `queued`), a new worker continued, finished 12/12, with no errors. Run 2: the same model,
  and the profile requires 256 dimensions → the check passed 256/256; while the vectors were
  being created, the index still serving was the 1024-dimension one; after the switch, the
  question is 256 dimensions, the semantic channel returns 5 results, and 0 nodes are missing
  a vector; the 1024-dimension index, now `retired`, still has all 12 vectors.
- Migration 0014 was trial-run on the DB `evidence_rerank_eval` (7,230 vectors) inside a
  transaction and then `ROLLBACK`: the status constraint changes correctly, and the data is
  unchanged.

## Remaining limits

- The time estimate at the check step is a rough estimate from a single call; the time
  remaining for a job that is running is computed from the actual speed (a moving average).
- Recovery after a process failure takes at most about 60 seconds (the heartbeat threshold).
- One job runs at a time; the other jobs queue in the order they were created. The job that
  finishes last is the index that is used.
- Embedding through an external API was not tried with a real provider in this round (only
  the policy was checked, by tests).
- There is no function on the UI to delete an old index (the requirement is that it does not
  delete on its own); cleanup, if it is needed, is a separate operations decision.
