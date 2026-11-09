# Requirements: Citation Pinning

> Spec reconstructed from the implemented code on 2026-11-09. This is not a historical Kiro-generated spec. Contracts: `docs/citation-contract.md`, `docs/pdf-anchor-coordinate-contract.md`.

## Introduction

Every piece of evidence shown to a user is pinned to an immutable document version, an Article/Clause/Point node, a source span on a page, and the SHA-256 of the original file. Quotes come from stored text, never from a model.

## Requirements

### Requirement 1: Stable, traceable evidence identity

#### Acceptance Criteria

1. THE SYSTEM SHALL identify evidence as `ev_<node id>` traceable to `document_version_id`, `document_nodes.id`, `source_spans` (page, offset, length, quads) and the source-file SHA-256 (`storage/citations.py`).
2. THE SYSTEM SHALL pin the `as_of_date` and reviewed effectivity state with the evidence.

### Requirement 2: Quotes are never generated

#### Acceptance Criteria

1. THE SYSTEM SHALL hydrate every quote from `document_nodes.text_original`.
2. THE SYSTEM SHALL NOT accept a quote, node ID or page number from a language model (`evidence/validators.py`, `evidence/mapper.py`, `synthesis/checks.py`).

### Requirement 3: Multi-page clauses

#### Acceptance Criteria

1. WHEN a clause spans pages THE SYSTEM SHALL store one source span per page (`documents/spans.py`, `node_writer.py`).
2. WHEN a node exceeds 4,000 characters THE SYSTEM SHALL continue it in "(phần N)" parts (`documents/tree_parser.py::MAX_NODE_CHARACTERS`).
3. THE SYSTEM SHALL store `parent_id`, `path` and `citation_label` for the Chapter/Section/Article/Clause/Point tree (migration `0009_node_structure.sql`).

### Requirement 4: Open the original with live authorisation

#### Acceptance Criteria

1. WHEN a user opens a citation (`GET /api/v1/citations/{id}`, `/pdf`, `/original`) THE SYSTEM SHALL re-check ACL, lookup availability, version, source state and SHA-256 before serving bytes.
2. IF permission was revoked THEN THE SYSTEM SHALL return 403 and SHALL NOT replay cached content.
3. WHEN the source is a PDF THE SYSTEM SHALL open it at the cited page; WHEN the source is Word or TXT THE SYSTEM SHALL download the file as originally uploaded.
4. IF bounding box, CropBox or rotation is uncertain THEN THE SYSTEM SHALL open only the page and show the quote, without drawing a highlight.

### Requirement 5: Immutable sources

#### Acceptance Criteria

1. THE SYSTEM SHALL store originals under `originals/<sha256>.pdf` and verify the digest on read (`documents/provenance.py::verify_immutable_pdf`).
2. IF the digest or path does not match THEN THE SYSTEM SHALL refuse with `PDF_STORAGE_CONFLICT`.
