# Phụ lục thống kê đóng góp của Kiro

**Ngôn ngữ / Language:** Tiếng Việt · [English](KIRO_STATS_APPENDIX.en.md)

Danh sách các tệp **sản phẩm trong Git (commit `34cff8b`)** có ít nhất một lệnh ghi/sửa của Kiro trong bản ghi phiên còn lưu. Phương pháp và cách đọc số liệu: [`KIRO_WORK_SUMMARY.vi.md`](KIRO_WORK_SUMMARY.vi.md) mục 8. Tệp thống kê này và các tệp tóm tắt được cập nhật sau commit đó thuộc lượt hiện tại nhưng không nằm trong danh sách.

Ký hiệu cột **Loại ghi**: `W` = có ít nhất một lệnh `fs_write` (Kiro tạo hoặc ghi đè toàn bộ tệp tại thời điểm đó); `E` = chỉ sửa cục bộ (`str_replace`, `fs_append`, đổi tên/di chuyển). Cột **Giai đoạn**: `H` = bản ghi lịch sử trước yêu cầu hồ sơ Kiroween (05–09/11/2026 17:19); `C` = lượt hiện tại (từ 09/11/2026 17:19); `H+C` = cả hai. Cột **Mới/Có sẵn** (chỉ cho `C`): tệp chưa có / đã có ở commit `08b0021`.

<details><summary>(root) (10)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `00_README.md` | 76 | W | H | 1 | 4c10b6e7 |
| `Dung-ung-dung-test.bat` | 6 | W | H | 1 | 4c10b6e7 |
| `KIRO_WORK_SUMMARY.en.md` | 170 | W | C (mới) | 1 | 4c10b6e7 |
| `KIRO_WORK_SUMMARY.vi.md` | 173 | W | C (mới) | 12 | 4c10b6e7 |
| `Mo-ung-dung-test.bat` | 7 | W | H | 1 | 4c10b6e7 |
| `PROJECT_TIMELINE.md` | 39 | W | C (có sẵn) | 1 | 4c10b6e7 |
| `PROJECT_TIMELINE.vi.md` | 39 | W | C (mới) | 1 | 4c10b6e7 |
| `README.en.md` | 131 | W | C (mới) | 1 | 4c10b6e7 |
| `README.md` | 166 | W | H+C | 9 | 201bebb1, 4c10b6e7 |
| `ung-dung-test.ps1` | 164 | W | H | 5 | 201bebb1, 4c10b6e7 |

</details>

<details><summary>.kiro (35)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `.kiro/hooks/backend-python-lint.json` | 16 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/hooks/frontend-typescript-check.json` | 16 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/ai-synthesis/design.md` | 38 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/ai-synthesis/requirements.md` | 56 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/ai-synthesis/tasks.md` | 13 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/audit-log/design.md` | 31 | W | C (mới) | 2 | 4c10b6e7 |
| `.kiro/specs/audit-log/requirements.md` | 38 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/audit-log/tasks.md` | 11 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/citation-pinning/design.md` | 39 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/citation-pinning/requirements.md` | 47 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/citation-pinning/tasks.md` | 13 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/document-management/design.md` | 47 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/document-management/requirements.md` | 81 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/document-management/tasks.md` | 14 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/effectivity/design.md` | 41 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/effectivity/requirements.md` | 59 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/effectivity/tasks.md` | 15 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/embedding/design.md` | 40 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/embedding/requirements.md` | 49 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/embedding/tasks.md` | 13 | W | C (mới) | 2 | 4c10b6e7 |
| `.kiro/specs/model-registry/design.md` | 43 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/model-registry/requirements.md` | 57 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/model-registry/tasks.md` | 14 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/ocr/design.md` | 42 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/ocr/requirements.md` | 56 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/ocr/tasks.md` | 15 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/search/design.md` | 40 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/search/requirements.md` | 58 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/search/tasks.md` | 15 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/windows-lan-portable/design.md` | 38 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/windows-lan-portable/requirements.md` | 61 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/specs/windows-lan-portable/tasks.md` | 14 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/steering/product.md` | 42 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/steering/structure.md` | 44 | W | C (mới) | 1 | 4c10b6e7 |
| `.kiro/steering/tech.md` | 58 | W | C (mới) | 1 | 4c10b6e7 |

</details>

<details><summary>backend/(root) (1)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `backend/pyproject.toml` | 51 | E | H | 2 | 4c10b6e7 |

</details>

<details><summary>backend/app/(root) (5)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `backend/app/admin_services.py` | 915 | E | H | 18 | 201bebb1, 4c237fbe, 79b7dcee |
| `backend/app/audit.py` | 90 | E | H | 2 | 4c10b6e7 |
| `backend/app/config.py` | 166 | E | H | 17 | 4c10b6e7, 4c237fbe, 79b7dcee, f6f39653 |
| `backend/app/main.py` | 1079 | E | H | 31 | 201bebb1, 4c10b6e7, 4c237fbe, 79b7dcee, f6f39653 |
| `backend/app/schemas.py` | 615 | E | H | 21 | 201bebb1, 4c10b6e7, 4c237fbe, 79b7dcee, f6f39653 |

</details>

<details><summary>backend/app/api (5)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `backend/app/api/v1/admin.py` | 1226 | E | H | 16 | 201bebb1, 4c10b6e7, 79b7dcee, f6f39653 |
| `backend/app/api/v1/comprehensive.py` | 231 | W | H | 9 | 201bebb1, 4c10b6e7, 79b7dcee |
| `backend/app/api/v1/effectivity.py` | 250 | W | H | 3 | 79b7dcee |
| `backend/app/api/v1/errors.py` | 206 | E | H | 13 | 4c10b6e7, 79b7dcee, f6f39653 |
| `backend/app/api/v1/synthesis.py` | 250 | W | H | 5 | 201bebb1, 79b7dcee |

</details>

<details><summary>backend/app/documents (11)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `backend/app/documents/convert.py` | 386 | W | H | 3 | 4c10b6e7 |
| `backend/app/documents/draft.py` | 304 | E | H | 10 | 201bebb1, 4c10b6e7, 79b7dcee |
| `backend/app/documents/draft_read.py` | 74 | E | H | 1 | 79b7dcee |
| `backend/app/documents/native_pdf.py` | 182 | E | H | 5 | 201bebb1 |
| `backend/app/documents/node_writer.py` | 164 | W | H | 2 | 4c10b6e7 |
| `backend/app/documents/ocr.py` | 294 | W | H | 9 | 201bebb1 |
| `backend/app/documents/provenance.py` | 205 | E | H | 4 | 201bebb1, 4c10b6e7 |
| `backend/app/documents/reextract.py` | 134 | E | H | 4 | 201bebb1, 4c10b6e7 |
| `backend/app/documents/review.py` | 527 | E | H | 10 | 201bebb1, 4c10b6e7, 79b7dcee |
| `backend/app/documents/spans.py` | 70 | E | H | 2 | 4c10b6e7 |
| `backend/app/documents/tree_parser.py` | 241 | W | H | 6 | 201bebb1, 4c10b6e7 |

</details>

<details><summary>backend/app/effectivity (7)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `backend/app/effectivity/__init__.py` | 1 | W | H | 1 | 79b7dcee |
| `backend/app/effectivity/ai.py` | 125 | W | H | 1 | 79b7dcee |
| `backend/app/effectivity/extract.py` | 569 | W | H | 13 | 79b7dcee |
| `backend/app/effectivity/node_paths.py` | 99 | W | H | 1 | 79b7dcee |
| `backend/app/effectivity/resolver.py` | 294 | W | H | 5 | 79b7dcee |
| `backend/app/effectivity/service.py` | 547 | W | H | 4 | 79b7dcee |
| `backend/app/effectivity/store.py` | 737 | W | H | 11 | 79b7dcee |

</details>

<details><summary>backend/app/migrations (17)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `backend/app/migrations/0008_source_format.down.sql` | 3 | W | H | 1 | 4c10b6e7 |
| `backend/app/migrations/0008_source_format.sql` | 8 | W | H | 1 | 4c10b6e7 |
| `backend/app/migrations/0009_node_structure.down.sql` | 3 | W | H | 2 | 4c10b6e7 |
| `backend/app/migrations/0009_node_structure.sql` | 51 | W | H | 3 | 4c10b6e7 |
| `backend/app/migrations/0010_ai_policy.down.sql` | 8 | W | H | 1 | 4c10b6e7 |
| `backend/app/migrations/0010_ai_policy.sql` | 44 | W | H | 1 | 4c10b6e7 |
| `backend/app/migrations/0011_effectivity.down.sql` | 42 | W | H | 1 | 79b7dcee |
| `backend/app/migrations/0011_effectivity.sql` | 141 | W | H | 1 | 79b7dcee |
| `backend/app/migrations/0012_comprehensive_search.down.sql` | 19 | W | H | 1 | 79b7dcee |
| `backend/app/migrations/0012_comprehensive_search.sql` | 35 | W | H | 1 | 79b7dcee |
| `backend/app/migrations/0013_content_groups.down.sql` | 4 | W | H | 1 | 79b7dcee |
| `backend/app/migrations/0013_content_groups.sql` | 96 | W | H | 1 | 79b7dcee |
| `backend/app/migrations/0014_embedding_jobs.down.sql` | 10 | W | H | 1 | f6f39653 |
| `backend/app/migrations/0014_embedding_jobs.sql` | 55 | W | H | 2 | f6f39653 |
| `backend/app/migrations/0015_ocr_page_review.down.sql` | 3 | W | H | 1 | 201bebb1 |
| `backend/app/migrations/0015_ocr_page_review.sql` | 5 | W | H | 1 | 201bebb1 |
| `backend/app/migrations/README.md` | 43 | W | H | 4 | 201bebb1, 4c10b6e7, f6f39653 |

</details>

<details><summary>backend/app/model_registry (7)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `backend/app/model_registry/adapters/base.py` | 30 | W | H | 1 | 4c237fbe |
| `backend/app/model_registry/adapters/openai_compatible.py` | 271 | E | H | 8 | 4c10b6e7, 79b7dcee, f6f39653 |
| `backend/app/model_registry/diagnostics.py` | 250 | W | H | 1 | 201bebb1 |
| `backend/app/model_registry/profiles.py` | 41 | E | H | 1 | 4c237fbe |
| `backend/app/model_registry/runtime.py` | 1282 | E | H | 27 | 4c10b6e7, 4c237fbe, 79b7dcee, f6f39653 |
| `backend/app/model_registry/secret_store.py` | 158 | W | H | 1 | 201bebb1 |
| `backend/app/model_registry/stages.py` | 48 | W | H | 3 | 4c10b6e7, 79b7dcee |

</details>

<details><summary>backend/app/storage (10)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `backend/app/storage/authorized_search.py` | 627 | E | H | 24 | 4c10b6e7, 79b7dcee |
| `backend/app/storage/chat_retrieval.py` | 261 | W | H | 9 | 201bebb1 |
| `backend/app/storage/citations.py` | 138 | E | H | 8 | 201bebb1, 4c10b6e7 |
| `backend/app/storage/comprehensive.py` | 1165 | W | H | 51 | 201bebb1, 4c10b6e7, 79b7dcee, f6f39653 |
| `backend/app/storage/cross_encoder.py` | 59 | W | H | 1 | 4c10b6e7 |
| `backend/app/storage/embedding_jobs.py` | 944 | W | H | 7 | f6f39653 |
| `backend/app/storage/embeddings.py` | 494 | W | H | 7 | 79b7dcee, f6f39653 |
| `backend/app/storage/relevance.py` | 621 | W | H | 37 | 201bebb1 |
| `backend/app/storage/search.py` | 1051 | E | H | 33 | 4c10b6e7, 79b7dcee |
| `backend/app/storage/search_paging.py` | 193 | E | H | 11 | 4c10b6e7, 79b7dcee |

</details>

<details><summary>backend/app/synthesis (6)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `backend/app/synthesis/__init__.py` | 1 | W | H | 1 | 79b7dcee |
| `backend/app/synthesis/checks.py` | 378 | W | H | 10 | 201bebb1, 79b7dcee |
| `backend/app/synthesis/focus.py` | 200 | W | H | 6 | 201bebb1 |
| `backend/app/synthesis/focused.py` | 530 | W | H | 24 | 201bebb1 |
| `backend/app/synthesis/labels.py` | 165 | W | H | 2 | 79b7dcee |
| `backend/app/synthesis/service.py` | 519 | W | H | 21 | 201bebb1, 79b7dcee |

</details>

<details><summary>backend/app/workflow (3)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `backend/app/workflow/ai_selection.py` | 117 | W | H | 4 | 4c10b6e7, 4c237fbe |
| `backend/app/workflow/chat_answer.py` | 508 | W | H | 29 | 201bebb1 |
| `backend/app/workflow/fixed_pipeline.py` | 679 | E | H | 14 | 201bebb1, 4c10b6e7, 79b7dcee |

</details>

<details><summary>backend/tests (17)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `backend/tests/test_ai_interpretation.py` | 257 | W | H | 8 | 201bebb1 |
| `backend/tests/test_ai_policy.py` | 340 | W | H | 1 | 4c237fbe |
| `backend/tests/test_ai_registry_postgres.py` | 649 | E | H | 2 | 4c237fbe |
| `backend/tests/test_audit_regressions.py` | 432 | E | H | 1 | 4c10b6e7 |
| `backend/tests/test_auth_and_admin_portal.py` | 344 | E | H | 7 | 201bebb1, 4c10b6e7, 4c237fbe, 79b7dcee, f6f39653 |
| `backend/tests/test_chat_answer.py` | 100 | W | H | 1 | 201bebb1 |
| `backend/tests/test_citation_api.py` | 316 | E | H | 1 | 201bebb1 |
| `backend/tests/test_effectivity_rules.py` | 254 | W | H | 1 | 79b7dcee |
| `backend/tests/test_embedding_jobs_postgres.py` | 505 | W | H | 2 | f6f39653 |
| `backend/tests/test_embedding_policy.py` | 57 | W | H | 1 | f6f39653 |
| `backend/tests/test_execution_regressions.py` | 164 | E | H | 1 | 4c10b6e7 |
| `backend/tests/test_model_diagnostics.py` | 305 | W | H | 4 | 201bebb1 |
| `backend/tests/test_model_registry_api.py` | 288 | W | H | 6 | 201bebb1 |
| `backend/tests/test_ocr_review.py` | 227 | W | H | 2 | 201bebb1 |
| `backend/tests/test_postgres_integration.py` | 138 | E | H | 3 | 4c10b6e7 |
| `backend/tests/test_relevance.py` | 112 | W | H | 1 | 201bebb1 |
| `backend/tests/test_synthesis_checks.py` | 53 | W | H | 1 | 79b7dcee |

</details>

<details><summary>configs (1)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `configs/ai-runtime.env.example` | 28 | W | H | 2 | 4c10b6e7 |

</details>

<details><summary>deploy (22)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `deploy/lan-portable/Backup-Data.bat` | 14 | W | H | 1 | d0b73228 |
| `deploy/lan-portable/README.en.txt` | 105 | W | C (mới) | 1 | 4c10b6e7 |
| `deploy/lan-portable/README.txt` | 102 | W | H+C | 2 | 4c10b6e7, d0b73228 |
| `deploy/lan-portable/Restore-Data.bat` | 16 | W | H | 1 | d0b73228 |
| `deploy/lan-portable/Start-Server.bat` | 15 | W | H | 1 | d0b73228 |
| `deploy/lan-portable/Stop-Server.bat` | 13 | W | H | 1 | d0b73228 |
| `deploy/lan-portable/config/evidence.env` | 43 | W | H | 1 | d0b73228 |
| `deploy/lan-portable/tools/Allow-LAN-Firewall.bat` | 19 | W | H | 1 | d0b73228 |
| `deploy/lan-portable/tools/Status.bat` | 8 | W | H | 1 | d0b73228 |
| `deploy/lan-portable/tools/Verify-Package.bat` | 9 | W | H | 1 | d0b73228 |
| `deploy/lan-portable/tools/portable-lib.ps1` | 235 | W | H | 5 | d0b73228 |
| `deploy/lan-portable/tools/portable.ps1` | 1075 | W | H | 29 | d0b73228 |
| `deploy/portable/README.txt` | 87 | W | H | 6 | 201bebb1, 4c10b6e7, f6f39653 |
| `deploy/portable/close-firewall.cmd` | 12 | W | H | 1 | 4c10b6e7 |
| `deploy/portable/config/evidence.env` | 57 | W | H | 5 | 201bebb1, 4c10b6e7, f6f39653 |
| `deploy/portable/evidence.ps1` | 426 | W | H | 3 | 201bebb1, 4c10b6e7 |
| `deploy/portable/open-firewall.cmd` | 12 | W | H | 1 | 4c10b6e7 |
| `deploy/portable/start.cmd` | 6 | W | H | 1 | 4c10b6e7 |
| `deploy/portable/status.cmd` | 6 | W | H | 1 | 4c10b6e7 |
| `deploy/portable/stop.cmd` | 6 | W | H | 1 | 4c10b6e7 |
| `deploy/windows/README.en.md` | 38 | W | C (mới) | 1 | 4c10b6e7 |
| `deploy/windows/README.md` | 59 | E | C (có sẵn) | 1 | 4c10b6e7 |

</details>

<details><summary>docs (39)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `docs/HUONG_DAN_SU_DUNG_VA_CAU_HINH_AI.md` | 136 | E | C (có sẵn) | 1 | 4c10b6e7 |
| `docs/SRS_v1.3.md` | 1624 | E | H | 1 | 4c10b6e7 |
| `docs/TAI_LIEU_MO_TA_HE_THONG.md` | 186 | E | C (có sẵn) | 1 | 4c10b6e7 |
| `docs/ai-model-recommendations.md` | 124 | W | H | 1 | 4c10b6e7 |
| `docs/architecture-decisions/ADR-005-search-v1.md` | 286 | E | H | 2 | 4c10b6e7 |
| `docs/architecture-decisions/ADR-006-retrieval-accuracy-bounds-and-ai-resilience.md` | 100 | W | H | 1 | 4c10b6e7 |
| `docs/architecture-decisions/ADR-007-stage-policy-hybrid-auto.md` | 63 | W | H+C | 4 | 4c10b6e7, 4c237fbe |
| `docs/architecture-decisions/ADR-008-effectivity-two-axes.md` | 62 | W | H | 1 | 79b7dcee |
| `docs/architecture-decisions/ADR-009-comprehensive-search-synthesis.md` | 74 | W | H | 4 | 4c10b6e7, 79b7dcee |
| `docs/en/ARCHITECTURE_OVERVIEW.md` | 75 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/en/SYSTEM_DESCRIPTION.md` | 163 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/en/USER_ADMIN_AND_AI_GUIDE.md` | 118 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/evidence/2026-11-05-retrieval-accuracy-performance/REPORT.md` | 198 | W | H | 8 | 4c10b6e7 |
| `docs/evidence/2026-11-07-embedding-admin/REPORT.md` | 79 | W | H | 1 | f6f39653 |
| `docs/evidence/2026-11-07-g5-rerank/REPORT-50-cau.md` | 103 | W | H | 6 | 4c10b6e7 |
| `docs/evidence/2026-11-07-g5-rerank/REPORT-tiebreak.md` | 76 | W | H | 2 | 4c10b6e7 |
| `docs/evidence/2026-11-07-g5-rerank/REPORT.md` | 123 | W | H | 6 | 4c10b6e7 |
| `docs/evidence/2026-11-08-ai-ocr/REPORT.md` | 156 | W | H | 1 | 201bebb1 |
| `docs/evidence/2026-11-08-model-registry-ui/REPORT.md` | 44 | W | H | 1 | 201bebb1 |
| `docs/evidence/2026-11-08-user-lookup/REPORT.md` | 101 | W | H | 2 | 201bebb1 |
| `docs/implementation-status.md` | 357 | W | H | 27 | 201bebb1, 4c10b6e7, 4c237fbe, 79b7dcee, f6f39653 |
| `docs/search-v1-runbook.md` | 187 | W | H | 2 | 4c10b6e7 |
| `docs/thiet-ke-tra-cuu-hieu-luc.md` | 276 | W | H | 3 | 4c10b6e7, 4c237fbe, 79b7dcee |
| `docs/threat-model.md` | 39 | E | H | 1 | 201bebb1 |
| `docs/vi/ARCHITECTURE_OVERVIEW.md` | 75 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/vi/kiro/README.vi.md` | 33 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/vi/kiro/specs/ai-synthesis.vi.md` | 66 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/vi/kiro/specs/audit-log.vi.md` | 49 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/vi/kiro/specs/citation-pinning.vi.md` | 60 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/vi/kiro/specs/document-management.vi.md` | 77 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/vi/kiro/specs/effectivity.vi.md` | 74 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/vi/kiro/specs/embedding.vi.md` | 63 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/vi/kiro/specs/model-registry.vi.md` | 72 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/vi/kiro/specs/ocr.vi.md` | 72 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/vi/kiro/specs/search.vi.md` | 73 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/vi/kiro/specs/windows-lan-portable.vi.md` | 73 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/vi/kiro/steering/product.vi.md` | 40 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/vi/kiro/steering/structure.vi.md` | 42 | W | C (mới) | 1 | 4c10b6e7 |
| `docs/vi/kiro/steering/tech.vi.md` | 56 | W | C (mới) | 1 | 4c10b6e7 |

</details>

<details><summary>evaluation (13)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `evaluation/coverage/README.md` | 60 | W | H | 5 | 4c10b6e7, 79b7dcee |
| `evaluation/coverage/check_tiebreak_stability.py` | 105 | W | H | 1 | 4c10b6e7 |
| `evaluation/coverage/compare_reproduction.py` | 77 | W | H | 1 | 4c10b6e7 |
| `evaluation/coverage/compare_rerank.py` | 248 | W | H | 9 | 4c10b6e7 |
| `evaluation/coverage/diagnose_missing.py` | 150 | W | H | 1 | 4c10b6e7 |
| `evaluation/coverage/g3_relations_reference.json` | 36 | W | H | 1 | 79b7dcee |
| `evaluation/coverage/measure_g3_relations.py` | 69 | W | H | 1 | 79b7dcee |
| `evaluation/coverage/run_coverage.py` | 103 | W | H | 1 | 79b7dcee |
| `evaluation/coverage/run_rerank_benchmark.py` | 244 | W | H | 9 | 4c10b6e7 |
| `evaluation/coverage/select_subset.py` | 91 | W | H | 2 | 4c10b6e7 |
| `evaluation/coverage/summarize_rrf.py` | 76 | W | H | 1 | 4c10b6e7 |
| `evaluation/coverage/topics.json` | 157 | W | H | 2 | 4c10b6e7, 79b7dcee |
| `evaluation/search_eval/README.md` | 120 | E | H | 1 | 4c10b6e7 |

</details>

<details><summary>frontend/src (38)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `frontend/src/App.test.tsx` | 131 | E | H | 1 | 4c10b6e7 |
| `frontend/src/App.tsx` | 439 | E | H | 8 | 201bebb1, 4c237fbe |
| `frontend/src/api/client.ts` | 1467 | E | H | 28 | 201bebb1, 4c237fbe, 79b7dcee, f6f39653 |
| `frontend/src/components/AiAnswerView.test.tsx` | 87 | W | H | 1 | 201bebb1 |
| `frontend/src/components/AiAnswerView.tsx` | 264 | W | H | 5 | 201bebb1 |
| `frontend/src/components/AiInterpretation.tsx` | 76 | W | H | 2 | 201bebb1 |
| `frontend/src/components/ChatAgentDock.tsx` | 452 | E | H | 6 | 201bebb1, 4c10b6e7 |
| `frontend/src/components/DocumentCard.tsx` | 232 | W | H | 3 | 201bebb1 |
| `frontend/src/components/DraftReviewPanel.test.tsx` | 121 | E | H | 1 | 201bebb1 |
| `frontend/src/components/DraftReviewPanel.tsx` | 199 | E | H | 8 | 201bebb1, 79b7dcee |
| `frontend/src/components/EffectivityBadges.tsx` | 52 | W | H | 3 | 79b7dcee |
| `frontend/src/components/EffectivityReviewPanel.tsx` | 276 | W | H | 2 | 79b7dcee |
| `frontend/src/components/EmbeddingManager.test.tsx` | 115 | W | H | 1 | f6f39653 |
| `frontend/src/components/EmbeddingManager.tsx` | 487 | W | H | 2 | f6f39653 |
| `frontend/src/components/LabelReviewPanel.tsx` | 80 | W | H | 1 | 79b7dcee |
| `frontend/src/components/OpenOriginalButton.test.tsx` | 62 | W | H | 1 | 201bebb1 |
| `frontend/src/components/OpenOriginalButton.tsx` | 99 | W | H | 4 | 201bebb1 |
| `frontend/src/components/SynthesisPanel.tsx` | 133 | W | H | 9 | 201bebb1, 79b7dcee |
| `frontend/src/components/ai/AssignmentsPanel.test.tsx` | 167 | W | H | 3 | 201bebb1 |
| `frontend/src/components/ai/AssignmentsPanel.tsx` | 296 | W | H | 4 | 201bebb1 |
| `frontend/src/components/ai/CheckResult.tsx` | 38 | W | H | 1 | 201bebb1 |
| `frontend/src/components/ai/ModelProfilesPanel.test.tsx` | 244 | W | H | 1 | 201bebb1 |
| `frontend/src/components/ai/ModelProfilesPanel.tsx` | 178 | W | H | 2 | 201bebb1 |
| `frontend/src/components/ai/ProfileEditor.tsx` | 343 | W | H | 1 | 201bebb1 |
| `frontend/src/components/ai/aiConfig.test.ts` | 169 | W | H | 2 | 201bebb1 |
| `frontend/src/components/ai/aiConfig.ts` | 443 | W | H | 3 | 201bebb1 |
| `frontend/src/components/documentDisplay.ts` | 302 | W | H | 3 | 201bebb1 |
| `frontend/src/components/effectivityLabels.ts` | 19 | W | H | 1 | 79b7dcee |
| `frontend/src/pages/AdminPortal.test.tsx` | 168 | E | H | 2 | 201bebb1, f6f39653 |
| `frontend/src/pages/AdminPortal.tsx` | 1297 | E | H | 49 | 4c10b6e7, 4c237fbe, 79b7dcee, f6f39653 |
| `frontend/src/pages/EvidenceChat.answer.test.tsx` | 170 | W | H | 2 | 201bebb1 |
| `frontend/src/pages/EvidenceChat.test.tsx` | 520 | E | H | 5 | 201bebb1, 4c237fbe |
| `frontend/src/pages/EvidenceChat.tsx` | 1039 | E | H | 31 | 201bebb1, 4c10b6e7, 4c237fbe |
| `frontend/src/pages/SearchPage.test.tsx` | 166 | W | H | 2 | 201bebb1 |
| `frontend/src/pages/SearchPage.tsx` | 644 | W | H | 18 | 201bebb1, 4c10b6e7, 79b7dcee |
| `frontend/src/samplePrompts.ts` | 6 | W | H | 1 | 4c10b6e7 |
| `frontend/src/styles.css` | 3493 | E | H | 8 | 201bebb1, 4c10b6e7, 79b7dcee, f6f39653 |
| `frontend/src/types.ts` | 594 | E | H | 11 | 201bebb1, 4c10b6e7, 4c237fbe, 79b7dcee, f6f39653 |

</details>

<details><summary>scripts (9)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `scripts/benchmark_search.py` | 492 | E | H | 1 | 4c10b6e7 |
| `scripts/build-lan-portable.ps1` | 391 | W | H | 7 | d0b73228 |
| `scripts/build_embeddings.py` | 72 | W | H | 3 | 79b7dcee, f6f39653 |
| `scripts/extract_effectivity.py` | 39 | W | H | 1 | 79b7dcee |
| `scripts/import_official_corpus.py` | 434 | W | H | 8 | 4c10b6e7 |
| `scripts/local_reranker_server.py` | 163 | W | H | 2 | 4c10b6e7 |
| `scripts/package-portable.ps1` | 181 | W | H | 2 | 4c10b6e7 |
| `scripts/rebuild_node_tree.py` | 222 | W | H | 2 | 4c10b6e7 |
| `scripts/verify_db_restore.py` | 136 | W | H | 1 | 4c10b6e7 |

</details>

<details><summary>test-data (1)</summary>

| Tệp | Dòng | Loại ghi | Giai đoạn | Số lệnh | Phiên |
|---|---:|---|---|---:|---|
| `test-data/README.md` | 39 | W | H | 1 | 4c10b6e7 |

</details>

## Tệp trong Git bị loại khỏi thống kê và lý do

Không có tệp văn bản pháp luật đầu vào nào nằm trong Git (PDF/DOC/DOCX/TXT nghiệp vụ nằm ở thư mục bị `.gitignore`). Các tệp sau bị loại vì không phải sản phẩm do Kiro phát triển:

- `backend/app/documents/fonts/Tinos-Bold.ttf`: phông chữ bên thứ ba
- `backend/app/documents/fonts/Tinos-Regular.ttf`: phông chữ bên thứ ba
- `backend/requirements-dev.lock`: tệp khóa phụ thuộc (sinh bởi trình quản lý gói)
- `docs/openapi.json`: lược đồ OpenAPI sinh tự động bởi `scripts/export_openapi.py`
- `evaluation/corpus_public_real/manifest.json`: bảng kê corpus PDF công khai (siêu dữ liệu tài liệu đầu vào)
- `frontend/pnpm-lock.yaml`: tệp khóa phụ thuộc (sinh bởi trình quản lý gói)
- `src-tauri/Cargo.lock`: tệp khóa phụ thuộc (sinh bởi trình quản lý gói)
- `src-tauri/icons/icon.ico`: biểu tượng nhị phân
- `src-tauri/icons/icon.png`: biểu tượng nhị phân

## Tệp chưa tính (ứng viên từ lệnh shell)

Các tệp dưới đây được nhắc trong lệnh shell của Kiro có động từ ghi (`Set-Content`, `Out-File`, `>`, `Copy-Item`…) nhưng không có lệnh ghi/sửa bằng công cụ chỉnh sửa. Việc nhắc tới **không** chứng minh Kiro đã ghi tệp (có thể chỉ đọc hoặc kiểm tra), nên **không được tính** vào số liệu:

- `.github/workflows/ci.yml`
- `.gitignore`
- `.kiro/settings/permissions.yaml`
- `LICENSE`
- `backend/app/documents/management_access.py`
- `backend/app/documents/management_read.py`
- `backend/app/documents/management_write.py`
- `backend/app/documents/pdf_worker.py`
- `backend/app/migrations/0016_document_management.sql`
- `backend/app/storage/lookup_visibility.py`
- `backend/tests/test_document_management.py`
- `backend/tests/test_lookup_visibility.py`
- `docs/KE_HOACH_TRIEN_KHAI_TIM_KIEM_V1_Evidence_RAG.md`
- `frontend/package.json`
- `frontend/src/components/AdminDocumentDetail.tsx`
- `frontend/src/components/AdminDocumentManager.tsx`
- `frontend/src/pages/AdminDocuments.test.tsx`
- `scripts/export_openapi.py`
- `scripts/seed_local_runtime.py`
- `scripts/smoke_app_runtime.py`
- `scripts/start-local-stack.ps1`
- `scripts/validate_migrations.py`
- `scripts/validate_no_literal_runtime_paths.py`
- `scripts/verify.ps1`
- `src-tauri/Cargo.toml`
- `store.py`
- `test-data/cau-hoi-kiem-thu-vong-1.md`

## Đường dẫn Kiro đã ghi nhưng không nằm trong Git

110 đường dẫn trong repository có lệnh ghi của Kiro nhưng không có trong Git ở commit này (bị `.gitignore`, như `.agents/`, `test-data/van-ban`; đã xóa; hoặc là bản tạm). Không tính vào số liệu tệp trong Git.

## Snapshot 11/11/2026 (commit 861fa34)

Bảng riêng này ghi số dòng thực tế trong các blob của commit `861fa34`, đếm bằng `git show <commit>:<tệp>`. Bảng lịch sử đóng góp phía trên vẫn giữ nguyên phạm vi commit `34cff8b`.

| Tệp | Dòng |
|---|---:|
| `.kiro/specs/citation-pinning/design.md` | 39 |
| `.kiro/specs/citation-pinning/tasks.md` | 13 |
| `.kiro/specs/effectivity/design.md` | 41 |
| `.kiro/specs/effectivity/requirements.md` | 61 |
| `.kiro/specs/effectivity/tasks.md` | 15 |
| `README.en.md` | 152 |
| `README.md` | 178 |
| `backend/app/documents/node_effectivity.py` | 92 |
| `backend/app/effectivity/extract.py` | 967 |
| `backend/app/effectivity/node_paths.py` | 106 |
| `backend/app/effectivity/resolver.py` | 316 |
| `backend/app/effectivity/store.py` | 748 |
| `backend/app/storage/chat_retrieval.py` | 268 |
| `backend/app/storage/comprehensive.py` | 1.165 |
| `backend/app/workflow/chat_answer.py` | 520 |
| `backend/tests/test_effectivity_node_scope_pg.py` | 167 |
| `backend/tests/test_effectivity_rules.py` | 638 |
| `deploy/lan-portable/HUONG_DAN_SU_DUNG.vi.md` | 179 |
| `deploy/lan-portable/USER_GUIDE.en.md` | 164 |
| `docs/HUONG_DAN_SU_DUNG_VA_CAU_HINH_AI.md` | 140 |
| `docs/TAI_LIEU_MO_TA_HE_THONG.md` | 186 |
| `docs/ai-model-recommendations.md` | 130 |
| `docs/amendments-and-effective-snapshots.md` | 11 |
| `docs/en/SYSTEM_DESCRIPTION.md` | 163 |
| `docs/en/USER_ADMIN_AND_AI_GUIDE.md` | 125 |
| `docs/implementation-status.md` | 384 |
| `docs/pdf-anchor-coordinate-contract.md` | 16 |
| `docs/schema-node-effectivity.md` | 19 |
| `docs/search-v1-runbook.md` | 187 |
| `docs/vi/kiro/specs/citation-pinning.vi.md` | 60 |
| `docs/vi/kiro/specs/effectivity.vi.md` | 76 |
| `evaluation/search_eval/README.md` | 120 |
| `frontend/src/components/EffectivityReviewPanel.tsx` | 280 |
| `frontend/src/components/SynthesisPanel.tsx` | 164 |
| `frontend/src/pages/EvidenceChat.test.tsx` | 652 |
| `frontend/src/pages/EvidenceChat.tsx` | 1.524 |
| `frontend/src/pages/SearchPage.tsx` | 662 |
| `frontend/src/styles.css` | 3.838 |
