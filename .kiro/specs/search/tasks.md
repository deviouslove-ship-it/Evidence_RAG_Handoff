# Tasks: Search and Grounded Q&A

> Spec reconstructed from the implemented code on 2026-11-09. Checkboxes reflect what exists in the repository. Figures come from the cited reports and were not re-run.

- [x] 1. Search v1 SQL channels and normalisation (`storage/search.py`, `normalization.py`)
- [x] 2. ACL-first retrieval (`storage/authorized_search.py`)
- [x] 3. Comprehensive search, four channels, RRF (`storage/comprehensive.py`, migration `0012`)
- [x] 4. Stable tie-break key (ADR-009; check script `evaluation/coverage/check_tiebreak_stability.py`; report `docs/evidence/2026-11-07-g5-rerank/REPORT-tiebreak.md`)
- [x] 5. Result sets and paging (`api/v1/comprehensive.py`)
- [x] 6. Search UI with three modes and filters (`SearchPage.tsx`)
- [x] 7. Grounded chat with SSE, stop and retry (`EvidenceChat.tsx`, `workflow/chat_answer.py`)
- [x] 8. Coverage and benchmark harness (`evaluation/coverage/run_coverage.py`, `scripts/benchmark_search.py`)
- [x] 9. Reranker comparison recorded; RRF kept as default (`REPORT.md`, `REPORT-50-cau.md`)
- [ ] 10. Subject-matter-expert confirmation of required provisions and queries (not present)
- [ ] 11. Retrieval fix for the two provisions missed in the G5 run (not present)
