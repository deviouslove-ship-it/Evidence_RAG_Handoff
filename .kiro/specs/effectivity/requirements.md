# Requirements: Document and Clause Effectivity

> Spec reconstructed from the implemented code on 2026-11-09. This is not a historical Kiro-generated spec. Source of the rules: `docs/architecture-decisions/ADR-008-effectivity-two-axes.md` and `docs/thiet-ke-tra-cuu-hieu-luc.md`.

## Introduction

Effectivity is modelled on two axes: legal status (axis A) and verification state (axis B: `verified`, `unverified`, `not_found`). Machine proposals are never shown as verified conclusions.

## Requirements

### Requirement 1: Two-axis status

#### Acceptance Criteria

1. THE SYSTEM SHALL store legal status per document and per Article/Clause/Point, and verification state in `document_effective_intervals` and `node_effective_intervals` (migration `0011_effectivity.sql`).
2. WHEN a status is computed THE SYSTEM SHALL evaluate it at the requested `as_of_date` over snapshot intervals.
3. WHEN the lookup date is after the store's data date THE SYSTEM SHALL cap verification at "unverified".

### Requirement 2: "In force + verified" only from human attestation

#### Acceptance Criteria

1. THE SYSTEM SHALL produce "in force + verified" only from `effectivity_attestations`, and the query layer SHALL downgrade it if another source claims it (`resolver.py::cap_verification`).
2. IF no terminating relation exists THEN THE SYSTEM SHALL show "undetermined" with "no information found in the store" and the effective-from date when known.
3. IF a proposal is unapproved THEN THE SYSTEM SHALL NOT change axis A and SHALL add a note that an unconfirmed proposal exists.
4. IF a relation is conditional or transitional THEN THE SYSTEM SHALL show "undetermined" with the condition.
5. WHEN an approved relation touches the target after an attestation date THE SYSTEM SHALL mark the attestation `needs_reverify` (trigger `effectivity_mark_reverify`).
6. THE SYSTEM SHALL assert "in force" only up to the attestation date (`ATTESTATION_FUTURE_DATE`).

### Requirement 3: Rule-based proposals

#### Acceptance Criteria

1. WHEN a document is approved THE SYSTEM SHALL read issue date, issuing body, effective date, replace/repeal/amend/suspend relations and consolidation by rules (`effectivity/extract.py`).
2. WHEN a sentence contains relation keywords the rules cannot read THE SYSTEM SHALL count it as a candidate for the AI `relation` stage, which only proposes.
3. IF reading relations fails THEN THE SYSTEM SHALL still allow source approval and record `EFFECTIVITY_PROCESSING_FAILED` in the audit log.
4. WHEN a target number is matched THE SYSTEM SHALL normalise the number, then type, then issue date, and mark multiple candidates `ambiguous` and no candidate `unresolved` (`effectivity/store.py::match_target`).

### Requirement 4: Review and permissions

#### Acceptance Criteria

1. WHEN a proposal is reviewed THE SYSTEM SHALL require a REVIEWER with `can_review` on the source or new target document's category.
2. THE SYSTEM SHALL NOT let a proposer approve their own proposal, and SYS_ADMIN SHALL NOT approve.
3. WHEN a reviewer edits action, date or target THE SYSTEM SHALL save a new record and keep the proposal as history.

### Requirement 5: Clause-level effectivity

#### Acceptance Criteria

1. THE SYSTEM SHALL record node-level exceptions for a node and its subtree, and a document-level terminating status SHALL override node exceptions.
2. THE SYSTEM SHALL compute `clause_level_reviewed` and show the general warning only while results include documents below that level.

### Requirement 6: Snapshots

#### Acceptance Criteria

1. WHEN a source, relation or attestation is approved or revoked THE SYSTEM SHALL publish a snapshot atomically (`POST /api/v1/admin/effectivity/snapshots/publish`), keep the 3 latest, and set `data_date` to the publish date.
2. IF a snapshot is stale or the graph is unknown THEN THE SYSTEM SHALL return temporal unknown and block legal conclusions (`docs/amendments-and-effective-snapshots.md`).
