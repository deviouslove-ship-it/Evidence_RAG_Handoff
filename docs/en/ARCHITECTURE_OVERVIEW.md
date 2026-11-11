# Architecture Overview

**Language / Ngôn ngữ:** [Tiếng Việt](../vi/ARCHITECTURE_OVERVIEW.md) · English

A short architecture overview for reviewers, written on 2026-11-09 from the repository code and documents; Kiro-use dates and spec update history were added on 2026-11-11. Details: [System description](SYSTEM_DESCRIPTION.md), the ADRs in `docs/architecture-decisions/` (Vietnamese) and the specs in `.kiro/specs/`.

## Components

```mermaid
flowchart TB
  subgraph Clients
    W[Browser: User Portal and Admin Portal]
    D[Tauri 2 Windows USER shell]
  end
  subgraph Server["FastAPI backend (backend/app)"]
    API[api/v1]
    AUTH[auth_acl: RBAC/ABAC]
    DOC[documents: intake, OCR, review, management]
    SRCH[storage: search, comprehensive, citations]
    EFF[effectivity]
    SYN[synthesis]
    REG[model_registry: profiles, stages, egress]
    AUD[audit: hash chain]
  end
  W --> API
  D --> API
  API --> AUTH
  API --> DOC
  API --> SRCH
  API --> EFF
  API --> SYN
  SYN --> REG
  SRCH --> REG
  DOC --> AUD
  DB[(PostgreSQL + pgvector)]
  FS[(Originals by SHA-256)]
  AUTH --> DB
  DOC --> DB
  DOC --> FS
  SRCH --> DB
  EFF --> DB
  AUD --> DB
  REG --> LM[Local models: Ollama and compatible]
  REG --> EX[Allowed external API]
  DOC --> OCR[Tesseract]
```

## Main flows

1. **Intake**: file → format and hash check → draft → extraction/OCR → tree and page spans → human review (a different person) → approval → effectivity proposals → snapshot.
2. **Lookup**: query → normalisation → ACL in SQL → four channels fused with RRF → grouped results → evidence cards.
3. **Open a source**: evidence ID → ACL, availability, version and SHA-256 re-check → PDF page or original file.
4. **AI interpretation** (optional): permitted evidence → `summarize` model → code checks → answer with supporting evidence.

## Principles and where they live

| Principle | Where |
|---|---|
| Permission before retrieval | `storage/authorized_search.py` |
| Quotes come from stored text | `storage/citations.py`, `evidence/validators.py`, `synthesis/checks.py` |
| Immutable, hashed originals | `documents/provenance.py` |
| Separation of duties in approval | `documents/review.py`, `documents/management_access.py` |
| Two-axis effectivity; human-only "verified" | `effectivity/resolver.py`, ADR-008 |
| Egress blocked by default; local-only embedding and rerank | `model_registry/stages.py`, ADR-004, ADR-007 |
| Tamper-evident audit | `audit.py` |

## Deployment shapes

- Development stack: `scripts/start-local-stack.ps1` (optionally `-Lan`).
- Clean portable package: `deploy/portable/`.
- Offline LAN package with local models: `deploy/lan-portable/`.

## How Kiro fits

Per the project owner, Kiro (Claude Sonnet 5.5 and Claude Opus 5.5) continued to be used through the 2026-11-11 snapshot; Kiroween remains open until its 2026-12-04 deadline. The stored logs cover 7 sessions from 2026-11-05 through the 2026-11-09 review on one machine. See [`KIRO_WORK_SUMMARY.en.md`](../../KIRO_WORK_SUMMARY.en.md) for evidence and owner-confirmed work. The `.kiro/specs` were initially reconstructed on 2026-11-09; effectivity and citation-pinning specs were updated on 2026-11-11.
