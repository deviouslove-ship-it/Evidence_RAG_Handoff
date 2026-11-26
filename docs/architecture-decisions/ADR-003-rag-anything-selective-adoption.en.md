**Language / Ngôn ngữ:** [Tiếng Việt](ADR-003-rag-anything-selective-adoption.md) · English

English counterpart of `docs/architecture-decisions/ADR-003-rag-anything-selective-adoption.md`. The Vietnamese file is the original.

# ADR-003 — Evaluation of RAG-Anything for the lookup algorithm

Date: 2026-10-22 · Status: accepted for selective application of the ideas in the POC; the framework is not yet integrated.

## Basis and boundaries

The public source of HKUDS/RAG-Anything was read at commit [afb67c43](https://github.com/HKUDS/RAG-Anything/tree/afb67c43d391b1b1008a6fee9f020a232067b9e5) (2026-10-21), including the [README](https://github.com/HKUDS/RAG-Anything/blob/afb67c43d391b1b1008a6fee9f020a232067b9e5/README.md), [context-aware processing](https://github.com/HKUDS/RAG-Anything/blob/afb67c43d391b1b1008a6fee9f020a232067b9e5/docs/context_aware_processing.md), [query code](https://github.com/HKUDS/RAG-Anything/blob/afb67c43d391b1b1008a6fee9f020a232067b9e5/raganything/query.py), [dependencies](https://github.com/HKUDS/RAG-Anything/blob/afb67c43d391b1b1008a6fee9f020a232067b9e5/pyproject.toml), and the [MIT license](https://github.com/HKUDS/RAG-Anything/blob/afb67c43d391b1b1008a6fee9f020a232067b9e5/LICENSE). This is source research; it does not import code, a package, a model, or a license notice into the product.

The framework combines the MinerU parser, LightRAG, language/embedding models, and processors for images, tables, and formulas; it aims at contextual retrieval of text and of multiple modalities. Core dependencies declare lightrag-hku<1.5 and mineru[core]>=3.4.1; the README states that MinerU models may be downloaded on first use. The app's current dossier makes the original PDF, ACL in SQL, an approved effectivity (hiệu lực) snapshot, and Local Mode without Internet mandatory conditions; SRS §14.2a/§15 treats full LightRAG/GraphRAG as a P2 research direction, not an MVP dependency.

## Decision

1. Apply the principle of preserving source identity and structure when ranking and grouping evidence. In the POC, the pipeline prefers an exact match on Article (Điều) and the administrative-document (văn bản) number inside the **candidate set that has passed ACL**, and it separates groups by document version. Regression tests distinguish `Điều 5`/`Điều 50` (Article 5/Article 50), two versions, and a sentence with multiple references. This only re-ranks candidates and organizes evidence; it does not prove effectivity (hiệu lực) or semantic correctness.
2. Keep the retrieval path of SRS v1.3: L1_WORD, L2_SYLLABLE, conditional DENSE; Grouped RRF; bounded reference traversal only on edges that have been approved; an independent whole-chain effectivity resolver. Do not use a self-inferred graph entity to confirm legal effectivity.
3. Do not add RAG-Anything, LightRAG, or MinerU to the current lockfile/runtime. Open a separate parser/multimodal POC only when a real public PDF is available, and check source/bbox/rotation, model policy, and the Windows footprint. Every model must go through the Registry and policy; Local Mode does not download a model or send data to the Internet.
4. Before rolling out any retrieval change, measure ablation B0–B7 on a real corpus plus an approved Gold [Not implemented — see ADR-010], tracking Recall/nDCG@10, wrong_doc/node, missed_exception, false abstention, ACL leakage, P50/P95, and RAM/disk. Compare against the same corpus hash and the same model/tokenizer/index/snapshot revision. The current aggregate test does not replace that measurement.

## Current consequences

The small change works with the existing backend and adds no new dependency. There is not yet PostgreSQL/pgvector, real PDF ingestion, a Gold [Not implemented — see ADR-010] set, a model, or a multimodal evaluation, so **there is not yet a conclusion that retrieval quality improves in real-world use**. Current SQL candidate generation is still the lexical baseline; re-ranking has an effect only on candidates that have already been returned. In particular, it does not replace exact lookup, re-checking ACL when citing, or the effectivity (hiệu lực) validator.
