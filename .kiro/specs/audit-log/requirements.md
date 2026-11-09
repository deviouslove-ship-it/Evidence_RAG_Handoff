# Requirements: Hash-chained Audit Log

> Spec reconstructed from the implemented code on 2026-11-09. This is not a historical Kiro-generated spec. Evidence is cited by repository path.

## Introduction

Privileged changes are recorded in a tamper-evident chain that auditors can verify.

## Requirements

### Requirement 1: Append with the change

#### Acceptance Criteria

1. WHEN a privileged change occurs THE SYSTEM SHALL append one `audit_events` row inside the caller's transaction, so the change and its audit commit together (`audit.py::append_audit`).
2. THE SYSTEM SHALL serialise appends with a PostgreSQL advisory transaction lock.

### Requirement 2: Chain integrity

#### Acceptance Criteria

1. THE SYSTEM SHALL compute each event hash as SHA-256 over previous hash, principal, action, target type, target ID, metadata and timestamp (`audit.py::_event_hash`).
2. WHEN the chain is verified THE SYSTEM SHALL report `valid`, `checked`, `broken_at` and `complete` (`audit.py::verify_audit_chain`).
3. IF more events exist than the verification limit (default 10,000) THEN THE SYSTEM SHALL report validity as unknown (`null`) rather than valid.

### Requirement 3: Access

#### Acceptance Criteria

1. WHEN an authorised user opens the audit view THE SYSTEM SHALL return recent events (limit 1 to 500) and the chain result (`GET /api/v1/admin/audit-events`).
2. THE SYSTEM SHALL NOT infer audit permission from other administrator roles.

### Requirement 4: What is recorded

#### Acceptance Criteria

1. THE SYSTEM SHALL record administration (accounts, categories, model registry, embedding jobs), document lifecycle (approval, availability, metadata and OCR edits), effectivity decisions, and processing failures such as `EFFECTIVITY_PROCESSING_FAILED`.
2. THE SYSTEM SHALL NOT write passwords or API keys into event metadata.
