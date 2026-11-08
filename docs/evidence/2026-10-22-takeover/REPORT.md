# Báo cáo tiếp quản kỹ thuật — 22/10/2026

**WP:** Tiếp quản POC hiện có; phần WP 0.0/0.1 và lát cắt backend, frontend, retrieval.

**Trạng thái:** Xong một phần. Nền tảng POC đã chạy kiểm tra tại máy này; chưa đạt các gate S0/S3 hay nghiệm thu sản phẩm.

**Đã làm**

- Xác định mã từ phiên AI trước ở trạng thái POC, chưa có repository Git và chưa có output test/build. Lưu snapshot nguồn trước khi sửa tại thư mục audit của root công cụ do owner cấp; [manifest 50 thay đổi nguồn](source-change-manifest.json) gồm 35 sửa, 14 thêm, 1 bỏ. Không tạo lịch sử Git giả.
- Đồng bộ byte nguyên bản 5 tài liệu bàn giao từ root đến vị trí chuẩn trong docs; [hash đối chiếu](document-sync.json). Không sửa SRS, hồ sơ chính hoặc parts.
- Sửa lỗi backend không khởi tạo vì response HTTP 204; chuẩn hóa lỗi API/OpenAPI; chặn SSE replay sai run, dọn RAM và kết quả khi xóa/hết hạn, idempotency retry, không phát kết quả sau cancel. Sửa validator citation thiếu ID, chuẩn hóa tiếng Việt gây đổi nghĩa, parser số hiệu và response extractive có evidence.
- Sửa frontend gửi fact rỗng, dùng principal giả, nhãn mode giả và ghép câu hỏi mới với căn cứ cũ; kiểm phản hồi lỗi API và build TypeScript.
- Thiết lập Python, Node, pnpm, uv, package/cache dev trong root chương trình do owner cấp; tạo lockfile dev, script xác minh, OpenAPI và workflow self-hosted Windows. [Inventory phiên bản, hash và real path tương đối](development-inventory.json) chỉ là môi trường phát triển, không phải manifest release.
- Đọc [RAG-Anything tại commit afb67c43](https://github.com/HKUDS/RAG-Anything/tree/afb67c43d391b1b1008a6fee9f020a232067b9e5); ghi [ADR-003](../../architecture-decisions/ADR-003-rag-anything-selective-adoption.md). Áp dụng xếp hạng tham chiếu Điều/số hiệu trên ứng viên đã qua ACL và nhóm chứng cứ theo version, không thêm framework/model. Một lượt review độc lập xác nhận 4 lỗi session/retry/cancel/stale UI; đã sửa và có regression test.

**Test và số đo thực**

| Kiểm tra | Kết quả tại máy Windows này |
|---|---|
| [Bộ verify](verification/summary.json) | 12/12 check exit 0 |
| [Backend pytest](verification/backend-tests.txt) | 66 passed, 1 skipped, 1 warning; skipped là PostgreSQL integration chưa được cấp DB disposable |
| [Mypy](verification/backend-typing.txt) và [Ruff](verification/backend-lint.txt) | 38 source files type clean; lint clean |
| [Frontend test](verification/frontend-tests.txt), [build](verification/frontend-build.txt) | 8 passed trên 4 file; Vite build thành công |
| [OpenAPI](verification/openapi.txt), [migration pairing](verification/migration-pairs.txt), [source policy](verification/source-policy.txt) | Đạt kiểm tra tĩnh; migration chưa chạy trên DB |
| [Polarity](verification/polarity-fixtures.txt), [temporal](verification/temporal-fixtures.txt) | Fixture tổng hợp đạt, không phải Gold |
| [Smoke UI localhost](ui-smoke.json) | Nhãn Local và lỗi chưa đăng nhập đúng; document không tràn ngang ở 320/768/1280 px |

Python 3.11.15, Node 24.16.0, pnpm 9.12.3, uv 0.11.28; môi trường dev và package vật lý nằm trong root công cụ. Warning backend duy nhất đến từ alias anyio cũ trong Starlette testclient. Kiểm tra phụ thuộc xác nhận package đang cài tương thích; không chứng minh clean install Windows. Regression test tham chiếu Điều 5/Điều 50 chỉ dùng dữ liệu tổng hợp, **không cho phép suy ra tăng Recall hay giảm hallucination trên kho thật**.

**Quyết định/ADR mới:** [ADR-003](../../architecture-decisions/ADR-003-rag-anything-selective-adoption.md) về ứng dụng có chọn lọc ý tưởng giữ cấu trúc nguồn và xếp hạng; không cài RAG-Anything/LightRAG/MinerU. ADR-000/SRS v1.3 vẫn là hợp đồng chính.

**CHƯA XONG / bị hoãn**

1. PostgreSQL/pgvector, migration up/down, truy vấn ACL SQL, snapshot hiệu lực, backup/restore và service Windows chưa chạy trên DB/máy đích. SQL search mới được sửa theo schema và kiểm tĩnh; phần xếp lại tham chiếu chỉ tác dụng nếu ứng viên đúng đã được SQL trả về.
2. Identity/RBAC production, Admin Portal, ingestion và review PDF bất biến, bbox/rotation/CropBox, citation-click thật còn thiếu. Frontend hiện là shell; truy vấn không có auth sẽ fail-closed như smoke test.
3. Không có corpus PDF công khai thật, Gold 150–200 ca được duyệt, trap set, model/API key/local runtime hoặc phép đo B0–B7/P50/P95. Không biết RAG-Anything có nâng chất lượng pháp lý tiếng Việt ở app này cho đến khi đo ablation cùng ACL/snapshot/corpus.
4. Model Router mới là hợp đồng/mock; không có LLM/embedding/reranker thực, AI attempt budget/egress chưa kiểm thực tế. Stop ngăn phát output của lượt bị hủy nhưng chưa ngắt tác vụ model thật; SSE hai pha chưa được thử qua mạng/proxy production.
5. Tauri native chưa build/chạy; Orb/login/panel/tray/DPI còn thiếu. Release dependency manifest/SBOM/license/footprint/clean-install và GitHub self-hosted CI run chưa có bằng chứng. Source scanner là kiểm tra literal hẹp, không thay audit secret/egress đầy đủ.

**Thứ tự tiếp tục:** hoàn tất WP 0.1 manifest/CI/footprint; WP 0.2 PostgreSQL/pgvector + ACL/migration/backup; WP 0.3 parser PDF/corpus thật; WP 0.5 auth/E2E mỏng + native shell; sau đó ingestion/review, Registry API/Local và Gold/ablation retrieval. Bất kỳ graph/multimodal expansion nào chỉ mở sau baseline và không dùng cạnh suy đoán để xác nhận hiệu lực.

**Rủi ro / cần người quyết:** quyền truy cập tài liệu và egress theo category; nguyên tắc nghiệp vụ về hiệu lực/sửa đổi; reviewer duyệt nguồn/Gold; máy Windows đích và cấu hình provider/model thực. Những phần còn lại là công việc kỹ thuật tiếp tục làm độc lập khi có hạ tầng và dữ liệu phù hợp.
