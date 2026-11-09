# Requirements: Search and Grounded Q&A

> Spec reconstructed from the implemented code on 2026-11-09. This is not a historical Kiro-generated spec. Evidence is cited by repository path. Search behaviour is described in `docs/architecture-decisions/ADR-005`, `ADR-006` and `ADR-009`.

## Introduction

Users find legal provisions by meaning, by all words, or by exact phrase, and ask questions that are answered only from approved, permitted sources.

## Requirements

### Requirement 1: Three search modes

#### Acceptance Criteria

1. WHEN a user searches THE SYSTEM SHALL offer comprehensive (by meaning), all-words and exact-phrase modes (`frontend/src/pages/SearchPage.tsx`, `GET /api/v1/search`, `POST /api/v1/search/comprehensive`).
2. WHEN a query is typed without Vietnamese diacritics or in different letter case THE SYSTEM SHALL still match (`storage/normalization.py`, `storage/search.py`).
3. WHEN a document number is typed in a different form (for example `15/2020/nđ-cp`) THE SYSTEM SHALL normalise it before matching.

### Requirement 2: Permission before retrieval

#### Acceptance Criteria

1. THE SYSTEM SHALL apply ACL filtering in SQL before candidates are retrieved (`storage/authorized_search.py`).
2. WHEN a result set page is requested THE SYSTEM SHALL re-check permission and source.
3. IF a document is suspended, soft-deleted or not approved THEN THE SYSTEM SHALL exclude it from results.

### Requirement 3: Comprehensive search channels

#### Acceptance Criteria

1. WHEN the user runs comprehensive search THE SYSTEM SHALL combine four channels with reciprocal rank fusion (k = 60): exact (SQL), semantic (vector), concept expansion, and document relations (`storage/comprehensive.py`).
2. IF no embedding index is available THEN THE SYSTEM SHALL continue with the keyword channels.
3. WHEN two results tie THE SYSTEM SHALL order them by a stable key: document number, source-file SHA-256, then clause position, with `COLLATE "C"` byte comparison; UUID is the last resort (ADR-009 section 1.3).
4. THE SYSTEM SHALL keep reranking optional and off by default (`EVIDENCE_RERANK_DEFAULT=false`).

### Requirement 4: Honest scope and limits

#### Acceptance Criteria

1. THE SYSTEM SHALL count results up to a configurable cap (`EVIDENCE_SEARCH_COUNT_CAP`, 8,000 in the verified configuration) and display "more than N" beyond it.
2. THE SYSTEM SHALL report categories searched, documents in scope, data date, unvectorised clauses and channel contributions.
3. WHEN nothing is found THE SYSTEM SHALL say nothing was found in the current store and scope, and SHALL NOT claim exhaustive search.

### Requirement 5: Result sets and paging

#### Acceptance Criteria

1. THE SYSTEM SHALL freeze results per request in an in-memory result set, readable only by its owner, expiring after `EVIDENCE_RESULT_SET_TTL_SECONDS`, at most 20 per user (`GET /api/v1/search/comprehensive/{result_set_id}`).
2. WHEN results are grouped by document THE SYSTEM SHALL page them and place partial matches in a separate group.

### Requirement 6: Grounded Q&A

#### Acceptance Criteria

1. WHEN a user asks a question THE SYSTEM SHALL stream a structured answer (SSE) built from approved, permitted evidence, with one card per document (`POST /api/v1/query/evidence`, `workflow/fixed_pipeline.py`, `workflow/chat_answer.py`).
2. IF no suitable provision exists, for example for penalty amounts or deadlines THEN THE SYSTEM SHALL answer "not found" instead of guessing (`storage/relevance.py`).
3. WHEN the only grounds are expired THE SYSTEM SHALL drop the conclusion; WHEN a single provision is expired THE SYSTEM SHALL exclude it and note it in the practical-use caveats.
4. THE SYSTEM SHALL keep session memory in RAM only and SHALL NOT use it as evidence.
