**Language / Ngôn ngữ:** [Tiếng Việt](REPORT.md) · English

English counterpart of `docs/evidence/2026-10-22-takeover/REPORT.md`. The Vietnamese file is the original.

# Technical takeover report — 2026-10-22

**WP:** Take over the existing POC; the WP 0.0/0.1 portion and the backend, frontend, and retrieval slices.

**Status:** Partially done. The POC baseline has been tested on this machine; it has not met the S0/S3 gates or product acceptance.

**What was done**

- Identified the code from the previous AI session as a POC, with no Git repository and no test or build output. Saved a source snapshot before editing, in the audit folder of the tool root provided by the owner; the [manifest of 50 source changes](source-change-manifest.json) comprises 35 edits, 14 additions, and 1 removal. No fake Git history was created.
- Synced the original bytes of 5 handover documents from the root to the standard location in docs; [hash cross-check](document-sync.json). The SRS, the main dossier, and parts were not edited.
- Fixed the backend failing to start because of an HTTP 204 response; normalized API/OpenAPI errors; blocked an incorrect SSE replay of a run, cleared RAM and results on delete or expiry, handled idempotency on retry, and does not emit a result after cancel. Fixed the citation validator missing an ID, Vietnamese normalization that changed the meaning, the document-number (số hiệu) parser, and extractive responses that contain evidence.
- Fixed the frontend sending an empty fact, using a fake principal, using fake mode labels, and joining a new question to old evidence (căn cứ); checked API error responses and the TypeScript build.
- Set up Python, Node, pnpm, uv, and the dev packages and cache inside the program root provided by the owner; created a dev lockfile, a verification script, OpenAPI, and a self-hosted Windows workflow. The [inventory of versions, hashes, and relative real paths](development-inventory.json) is a development environment only, not a release manifest.
- Read [RAG-Anything at commit afb67c43](https://github.com/HKUDS/RAG-Anything/tree/afb67c43d391b1b1008a6fee9f020a232067b9e5); recorded [ADR-003](../../architecture-decisions/ADR-003-rag-anything-selective-adoption.md). Applied ranking of Article (Điều) and document-number (số hiệu) references on candidates that have passed ACL, and grouped the evidence by version, without adding a framework or a model. One independent review confirmed 4 session, retry, cancel, and stale-UI bugs; they were fixed and have regression tests.

**Tests and real measurements**

| Check | Result on this Windows machine |
|---|---|
| [Verify suite](verification/summary.json) | 12/12 checks exit 0 |
| [Backend pytest](verification/backend-tests.txt) | 66 passed, 1 skipped, 1 warning; the skip is the PostgreSQL integration, which was not given a disposable DB |
| [Mypy](verification/backend-typing.txt) and [Ruff](verification/backend-lint.txt) | 38 source files type clean; lint clean |
| [Frontend test](verification/frontend-tests.txt), [build](verification/frontend-build.txt) | 8 passed across 4 files; Vite build succeeded |
| [OpenAPI](verification/openapi.txt), [migration pairing](verification/migration-pairs.txt), [source policy](verification/source-policy.txt) | Passed the static checks; migrations have not run on a DB |
| [Polarity](verification/polarity-fixtures.txt), [temporal](verification/temporal-fixtures.txt) | Synthetic fixtures passed; they are not Gold |
| [Localhost UI smoke](ui-smoke.json) | The Local label and the not-logged-in error are correct; the document does not overflow horizontally at 320/768/1280 px |

Python 3.11.15, Node 24.16.0, pnpm 9.12.3, uv 0.11.28; the dev environment and the physical packages live in the tool root. The only backend warning comes from an old anyio alias in the Starlette test client. The dependency check confirms that the installed packages are compatible; it does not prove a clean Windows install. The regression test referencing Article (Điều) 5 / Article (Điều) 50 uses only synthetic data, and **does not justify inferring higher Recall or lower hallucination on a real store**.

**New decisions/ADRs:** [ADR-003](../../architecture-decisions/ADR-003-rag-anything-selective-adoption.md) on selective application of the ideas of preserving source structure and of ranking; RAG-Anything, LightRAG, and MinerU were not installed. ADR-000/SRS v1.3 remains the main contract.

**NOT DONE / deferred**

1. PostgreSQL/pgvector, migration up/down, ACL SQL queries, effectivity (hiệu lực) snapshots, backup/restore, and the Windows service have not run on the target database or machine. The new search SQL was corrected to the schema and checked statically; the reference re-ranking takes effect only if SQL has already returned the correct candidate.
2. Production identity/RBAC, the Admin Portal, immutable PDF ingestion and review, bbox/rotation/CropBox, and a real citation click are still missing. The frontend is currently a shell; a query without auth fails closed, as in the smoke test.
3. There is no real public PDF corpus, no approved Gold set of 150–200 cases, no trap set, no model, API key, or local runtime, and no B0–B7/P50/P95 measurement. It is not known whether RAG-Anything would improve Vietnamese legal quality in this app until an ablation is measured on the same ACL, snapshot, and corpus.
4. The new Model Router is only a contract/mock; there is no real LLM, embedding, or reranker, and the AI attempt budget and egress have not been checked in practice. Stop prevents output from a cancelled turn but does not yet interrupt a real model task; two-phase SSE has not been tried over a production network or proxy.
5. Tauri native has not been built or run; Orb, login, panel, tray, and DPI are still missing. There is no evidence yet of a release dependency manifest, SBOM, license, footprint, or clean install, or of a GitHub self-hosted CI run. The source scanner is a narrow literal check and does not replace a full secret and egress audit.

**Order to continue:** finish WP 0.1 manifest/CI/footprint; WP 0.2 PostgreSQL/pgvector plus ACL, migration, and backup; WP 0.3 the PDF parser and a real corpus; WP 0.5 a thin auth/E2E path plus the native shell; then ingestion/review, the Registry API/Local path, and Gold and retrieval ablation. Any graph or multimodal expansion opens only after a baseline, and a speculative edge is not used to confirm effectivity (hiệu lực).

**Risks / needs a decision-maker:** document access and egress by category; the business rules for effectivity (hiệu lực) and amendment (sửa đổi); a reviewer for sources and for Gold; the target Windows machine and a real provider and model configuration. The remaining parts are technical work that can continue independently once suitable infrastructure and data are available.
