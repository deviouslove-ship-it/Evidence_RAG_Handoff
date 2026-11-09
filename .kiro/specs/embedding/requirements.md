# Requirements: Embedding Management

> Spec reconstructed from the implemented code on 2026-11-09. This is not a historical Kiro-generated spec. Evidence is cited by repository path. Decisions: ADR-009 section 1.

## Introduction

Semantic search needs one vector index per embedding model and dimension. Administrators can change the model through a guarded background job, and the serving index stays available until the new one is verified.

## Requirements

### Requirement 1: One index per model and dimension

#### Acceptance Criteria

1. THE SYSTEM SHALL store vectors in `node_embeddings` without a fixed dimension and register each model, revision and dimension in `embedding_indices`, each with its own HNSW index (migration `0012_comprehensive_search.sql`).
2. THE SYSTEM SHALL embed text built from document number, citation label and clause text, limited to 800 characters.
3. THE SYSTEM SHALL require the query embedding model to match the serving index.

### Requirement 2: Preflight before change

#### Acceptance Criteria

1. WHEN an administrator checks a model THE SYSTEM SHALL test connectivity, vector output, dimension, permission and node count, and report estimates (`POST /api/v1/admin/embeddings/preflight`, `storage/embedding_jobs.py::preflight`).
2. IF the mode, endpoint policy or privacy zone does not allow the model THEN THE SYSTEM SHALL refuse with a coded error (`remote_embedding_allowed`).

### Requirement 3: Background job

#### Acceptance Criteria

1. WHEN the administrator confirms THE SYSTEM SHALL create a job and process it in batches (default 16, maximum 256) in the API process, one job at a time (`EmbeddingWorker`).
2. THE SYSTEM SHALL support pause, resume, retry and cancel according to job state: pause from queued or running, resume from paused, retry from failed, cancel from queued, paused or failed.
3. WHEN a batch fails THE SYSTEM SHALL retry with backoff and mark the job failed after 5 consecutive failures or a permanent error.
4. THE SYSTEM SHALL show progress, rate, estimate and errors.

### Requirement 4: Verified switch

#### Acceptance Criteria

1. WHEN all nodes have vectors THE SYSTEM SHALL verify the index and run a sample check before activating it.
2. IF verification fails THEN THE SYSTEM SHALL keep the previous index serving and fail the job.
3. THE SYSTEM SHALL NEVER delete old indexes automatically.
4. WHEN new nodes are approved later THE SYSTEM SHALL allow "check and fill missing vectors".

### Requirement 5: Local-only stage

#### Acceptance Criteria

1. THE SYSTEM SHALL send `embedding` and `rerank` stages only to local profiles and never to `public` profiles, in both operating modes (`model_registry/stages.py::LOCAL_ONLY_STAGES`).
2. IF no vector is available THEN THE SYSTEM SHALL still serve keyword search.
