# Requirements: Document Management (Admin Portal)

> Spec reconstructed from the implemented code on 2026-11-09. This is not a historical Kiro-generated spec: no Kiro spec session exists for this project (see `KIRO_WORK_SUMMARY.en.md`). Evidence is cited by repository path.

## Introduction

The Admin Portal lets authorised staff list, inspect, correct, re-version, suspend and soft-delete legal documents without breaking lookup for users or losing source files.

## Requirements

### Requirement 1: List, search and filter documents

**User Story:** As an administrator, I want a paginated, filterable document list, so that I can find a document by number or title quickly.

#### Acceptance Criteria

1. WHEN an authorised user opens "Quản lý văn bản" THE SYSTEM SHALL return a paginated list (`GET /api/v1/admin/documents`, `documents/management_read.py::list_documents`).
2. WHEN the user searches by document number or title THE SYSTEM SHALL match accent-insensitively.
3. WHEN the user applies filters (type, issuing body, date range, processing status, effectivity, lookup status, deleted) THE SYSTEM SHALL return only matching documents.
4. IF the user is not SYS_ADMIN THEN THE SYSTEM SHALL restrict rows to documents the user may access by category ACL or document ACL (`documents/management_access.py`).

### Requirement 2: Document detail

**User Story:** As a reviewer or curator, I want one detail view, so that I can see metadata, versions, OCR pages and the Article/Clause/Point tree.

#### Acceptance Criteria

1. WHEN the user opens a document THE SYSTEM SHALL show metadata, categories, version history and processing history (`management_read.py::detail`).
2. WHEN the user has read permission THE SYSTEM SHALL serve the immutable original file and OCR pages, after re-checking permission, version and SHA-256 (`management_read.py::original`).
3. WHEN the user lacks content permission THE SYSTEM SHALL still show metadata only if the role allows it, and SHALL NOT expose content or the original.

### Requirement 3: Correct an approved version

**User Story:** As a curator, I want to fix metadata or OCR text of an approved version, so that errors are corrected with a review trail.

#### Acceptance Criteria

1. WHEN a curator edits metadata or OCR text of an approved version THE SYSTEM SHALL create a new draft revision that reuses the immutable original (`management_write.py::change_version`).
2. WHILE the new revision awaits review THE SYSTEM SHALL keep serving the previously approved version if the document is active and the user is permitted.
3. WHEN the revision is approved THE SYSTEM SHALL withdraw the previous version of the same file from lookup and keep it in history.
4. WHEN OCR text of a page is edited THE SYSTEM SHALL require re-confirmation of every edited page and SHALL store OCR text before and after editing.
5. IF the submitted review revision is stale THEN THE SYSTEM SHALL reject the action so the user reloads.

### Requirement 4: Add a version from a new file

#### Acceptance Criteria

1. WHEN a curator adds a PDF, Word or TXT file to an existing document THE SYSTEM SHALL run the standard intake pipeline and create a draft version of the same document.
2. WHEN the version is approved THE SYSTEM SHALL make it searchable from the confirmed issue date, or from the approval date if no issue date exists.

### Requirement 5: Separation of duties in approval

#### Acceptance Criteria

1. WHEN a draft is submitted THE SYSTEM SHALL allow only a different REVIEWER to approve or reject it.
2. IF the reviewer lacks `can_review` on any assigned category THEN THE SYSTEM SHALL deny approval.
3. IF categories change while a revision is being approved THEN THE SYSTEM SHALL reject the approval so the reviewer reloads.

### Requirement 6: Suspend, soft-delete and restore

**User Story:** As SYS_ADMIN, I want to suspend or soft-delete documents in bulk, so that bad content leaves lookup without destroying data.

#### Acceptance Criteria

1. WHEN SYS_ADMIN submits `POST /api/v1/admin/documents/actions` with a reason THE SYSTEM SHALL suspend lookup, restore lookup, soft-delete or restore the selected documents (`management_write.py::change_availability`).
2. THE SYSTEM SHALL keep source files, vectors, categories and history for suspended and soft-deleted documents.
3. WHEN a soft-deleted document is restored THE SYSTEM SHALL keep an earlier suspension flag in force.
4. THE SYSTEM SHALL treat lookup status as independent from legal effectivity.

### Requirement 7: Cross-process visibility

#### Acceptance Criteria

1. WHEN availability changes THE SYSTEM SHALL bump a lookup-visibility counter (migration `0016_document_management.sql`, `storage/lookup_visibility.py`).
2. WHEN a backend process sees a changed counter THE SYSTEM SHALL expire cached result sets, and chat, search, AI interpretation and the citation API SHALL re-check accessibility.

### Requirement 8: Auditability

#### Acceptance Criteria

1. WHEN metadata, OCR text, availability or approval changes THE SYSTEM SHALL append a hash-chained audit event in the same transaction (`audit.py::append_audit`).
