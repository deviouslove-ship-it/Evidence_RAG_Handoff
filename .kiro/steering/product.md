---
inclusion: always
---

# Product: Vietnamese Evidence RAG Agent

> Steering reconstructed from the implemented code and project documents on 2026-11-09. It is not a historical Kiro steering file. Vietnamese translation: `docs/vi/kiro/steering/product.vi.md`.

## Purpose

Grounded lookup of Vietnamese legal documents. Users ask or search an approved, access-controlled store, see the exact passage and its location, and open the original file. The system supports staff; it does not produce legal authority, and AI output always needs expert review.

## Surfaces

- **User Portal** (web and Windows Tauri shell): grounded Q&A, document search, optional "AI interpretation".
- **Admin Portal**: document intake and review, document management, categories, accounts (RBAC/ABAC), Model Registry, embedding jobs, effectivity review, audit log.

## Roles

| Role | Can do | Cannot do |
|---|---|---|
| `USER` (e.g. `chuyenvien`) | Ask, search, open permitted sources | Read outside ACL |
| `CURATOR` | Upload, create and edit drafts, re-extract, submit for review | Approve own drafts |
| `REVIEWER` | Resolve tasks, confirm OCR pages, pick categories, approve or reject, review effectivity | Approve own proposals; approve without `can_review` on every assigned category |
| `SYS_ADMIN` (`admin`) | Categories, accounts, roles, Model Registry, embedding, suspend or soft-delete documents | Read all content or approve by default |
| `AUDITOR` | View audit functions as granted | Change AI config; read all documents |

## Product rules (do not weaken)

1. The agent is advisory and read-only. It has no tool that writes or approves business data.
2. A different person approves a draft than the one who prepared it (`SELF_APPROVAL_DENIED`).
3. ACL filtering happens in SQL before candidates are retrieved; citations and files are re-authorised on open.
4. Quotes come from stored `text_original`. A model never writes quotes, node IDs or page numbers.
5. Source files are immutable and addressed by SHA-256; the hash is re-verified when a file is opened.
6. Machine-proposed effectivity is never shown as verified. "In force + verified" comes only from a human attestation.
7. Session memory is in RAM, is never evidence, and is not a backup.
8. Sending data outside is blocked by default; `LOCAL` mode refuses `public` profiles.
9. No Gold question set is used to score the AI (ADR-010): the AI only assists, the domain staff decide.

## Honest scope

No domain acceptance exists, and no Gold question set is planned (ADR-010). Test figures in `docs/evidence/` are historical reports, not guarantees. Do not add claims about accuracy, coverage or deployment readiness that a report in the repository does not support.
