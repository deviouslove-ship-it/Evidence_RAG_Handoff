# KIRO_WORK_SUMMARY — Công việc Kiro đã tham gia trong dự án Evidence RAG

**Ngôn ngữ / Language:** Tiếng Việt · [English](KIRO_WORK_SUMMARY.en.md)

Tài liệu phục vụ hồ sơ **Kiroween 2026**. Bản đầu lập ngày 09/11/2026 từ bản ghi phiên Kiro còn lưu trên máy tác giả,
lịch sử Git, mã nguồn và tài liệu repo; cập nhật ngày 11/11/2026 theo xác nhận của chủ dự án và các bổ sung sau build. Kiroween còn diễn ra đến hạn 04/12/2026, nên đây chưa phải tổng kết cuối kỳ. Mọi giờ trong tài liệu là giờ Việt Nam (UTC+7).

Các số liệu đóng góp ở mục 1 và 8 là snapshot chốt đến 09/11/2026; không bao gồm cập nhật 10–11/11 và không phải tổng kết cuối Kiroween.

## 0. Xác nhận của chủ dự án và cách đọc bằng chứng

**Xác nhận của chủ dự án (Vu Tuan Anh):** Kiro được dùng trong dự án từ **30/10/2026 đến ít nhất 11/11/2026**; việc sử dụng trên **cả máy cơ quan và máy nhà** được xác nhận đến 09/11. Tính đến 11/11, Kiro vẫn đang được dùng và Kiroween chưa kết thúc (hạn 04/12/2026). Kiro IDE dùng **Claude Sonnet 5.5** và **Claude Opus 5.5**; công việc do các model này thực hiện trong Kiro được ghi nhận là công việc Kiro hỗ trợ.

Đây là lời xác nhận của chủ dự án, không phải nhật ký. Nhật ký Kiro còn lưu cục bộ chỉ có trên **một máy** và hiện bao phủ đến phiên rà soát ngày 09/11/2026 (mục 2). Không có nhật ký trong tay cho 30/10–04/11, máy còn lại và các cập nhật 10–11/11; các mốc này dựa trên xác nhận của chủ dự án, không dùng để quy từng tệp hay tăng các số liệu lịch sử.

> **Nguyên tắc.** Tài liệu này không khẳng định toàn bộ mã nguồn do Kiro tạo. Mỗi mục được gắn một trong ba loại bằng chứng:
> **A** – **nhật ký Kiro**: có bản ghi phiên, lệnh ghi/sửa tệp, báo cáo cuối phiên;
> **B** – **xác nhận của chủ dự án, không có nhật ký**: có trong source, nằm trong khoảng thời gian chủ dự án xác nhận dùng Kiro, nhưng không có bản ghi để quy từng tệp cho Kiro hay cho tác giả;
> **C** – **tái dựng từ code hoặc tài liệu**: mô tả được suy ra từ mã hiện có, không dựa trên bản ghi phiên.
>
> Các thống kê số tệp và số dòng ở mục 1 và mục 8 chỉ tính từ loại A. Chúng không bị tăng lên bởi xác nhận của chủ dự án.

## 1. Tóm tắt

| Chỉ tiêu | Giá trị | Nguồn |
|---|---|---|
| Phiên Kiro cho workspace này còn lưu cục bộ | **7** (5 phiên trò chuyện + 2 bước workflow của agent `wf-coder`) | thư mục phiên Kiro của người dùng |
| Khoảng thời gian có bản ghi | **05/11/2026 17:27 → 09/11/2026** (phiên rà soát này) | `session.json`, `messages.jsonl` |
| Mô hình ghi trong phiên | `claude-sonnet-5.5` (5 phiên), `claude-opus-5.5` (3 phiên: 2 workflow + 1 phiên trò chuyện) | `session.json` |
| Lượt làm việc (turn) / lệnh công cụ | 62 lượt, 3.924 lệnh tính đến lúc lập thống kê (shell 1.403, đọc tệp 723, `str_replace` 993, `fs_write` 358, tìm kiếm 319…): **3.704 lệnh (1.274 lệnh ghi/sửa)** thuộc bản ghi lịch sử trước 09/11 17:19 và **220 lệnh (95 lệnh ghi/sửa)** thuộc lượt hiện tại | đếm từ `messages.jsonl`; số lệnh lượt hiện tại còn tăng |
| Workflow Kiro đã chạy | 2 lần `bundled://goal` (G1.0 và G1→G5), agent `wf-coder`, `claude-opus-5.5`, effort `high` | `workflow-state.json` |
| Tệp sản phẩm trong Git có ít nhất một lệnh ghi/sửa của Kiro | **257 / 471** (55%): mã 161/300, tài liệu `.md`/`.txt` 88/142, cấu hình 8/29. Trong đó **194** tệp từ bản ghi lịch sử và **63** tệp lần đầu được Kiro chạm tới ở lượt hiện tại (59 tạo mới). **208** tệp có lệnh `fs_write` (tạo hoặc ghi đè toàn bộ), 49 tệp chỉ sửa cục bộ | mục 8; mẫu số đã loại 9 tệp không phải sản phẩm |
| Dòng trong các tệp đó | 54.957 / 76.975 dòng (71%) — **cận trên**; 29.926 dòng (39%) nằm trong tệp có `fs_write`. Riêng mã: 46.189 / 60.609 (76%); tài liệu: 8.364 / 14.620 (57%) | mục 8; sửa một tệp không có nghĩa viết cả tệp |
| Spec / steering / hook trong `.kiro/` | Không phiên nào ghi dùng chế độ spec. Ngày 09/11/2026 repo được bổ sung ban đầu 10 nhóm spec và 3 steering **dựng lại từ code**, cùng 2 hook; spec hiệu lực và ghim trích dẫn được cập nhật 11/11. Đây **không phải** tài liệu lịch sử của Kiro | mục 7 |

Hai điều cần đọc kỹ trước khi dùng tài liệu này làm hồ sơ:

1. **Nhật ký Kiro cục bộ chỉ bắt đầu từ 05/11/2026 17:27, chỉ trên một máy và hiện kết thúc ở phiên rà soát 09/11.** Chủ dự án xác nhận Kiro được dùng từ 30/10 đến ít nhất 11/11; việc dùng trên cả hai máy được xác nhận đến 09/11. Khoảng 30/10–04/11, 10–11/11 và phần công việc trên máy còn lại **không có nhật ký trong tay**; các mốc này thuộc loại **B** (xác nhận của chủ dự án) và không được gán cho từng tệp.
2. **Git không ghi nhận Kiro.** Cả 9 commit đều do một tài khoản GitHub (`deviouslove-ship-it`), không có dòng đồng tác giả; commit đầu (08/11/2026 20:32) là ảnh chụp 404 file của thư mục làm việc. Vì vậy lịch sử Git không phân biệt được ai viết gì.

## 2. Các phiên Kiro còn truy cập được

| Mã phiên | Tiêu đề (do Kiro đặt) | Thời gian | Chế độ / mô hình | Lượt | Lệnh công cụ | File ghi/sửa | Kết quả chính |
|---|---|---|---|---|---|---|---|
| `4c10b6e7` | Rà soát hồ sơ Kiro cho Kiroween (phiên gốc, đổi tên theo yêu cầu hiện tại) | 05/11 17:35 → nay | vibe, Autopilot, Sonnet 5.5 | 46 | 1.668 | 143 | Nhiều đợt: tối ưu/độ chính xác tìm kiếm, gói LAN v1, Word/TXT, thiết kế tra cứu–hiệu lực, G0, benchmark reranker, bộ 50 câu, khóa phá hòa RRF, `.bat` thử giao diện |
| `b63f6d04` | Migrate Project Data From C To E Drive | 07/11 08:51–09:16 | vibe, Sonnet 5.5 | 3 | 72 | 24 | Kiểm kê dữ liệu ổ C, soạn cấu hình quyền; có một sai sót đã hoàn lại (mục 3, A24) |
| `4c237fbe` | goal · work #1 (workflow G1.0) | 07/11 10:54–11:55 | `wf-coder`, Opus 5.5 | 2 | 181 | 20 | G1.0 chính sách giai đoạn AI + Hybrid Auto |
| `79b7dcee` | goal-g1-g5-tra-cuu-hieu-luc · work #1 | 07/11 11:57–15:20 | `wf-coder`, Opus 5.5 | 2 | 419 | 82 | G1→G5: hiệu lực, tìm toàn diện, nhóm nội dung, tổng hợp, đo bao phủ |
| `f6f39653` | Embedding management in Admin Portal | 07/11 19:41–21:22 | vibe, Autopilot, Opus 5.5 | 2 | 192 | 30 | Quản lý embedding chạy nền trong Admin Portal |
| `201bebb1` | Fix AI interpretation and OCR | 08/11 10:22–15:35 | vibe, Autopilot, Sonnet 5.5 | 4 | 972 | 114 | Sửa tra cứu USER, Diễn giải AI, OCR PDF scan, giao diện Model Registry |
| `d0b73228` | Package Evidence RAG As Portable Windows LAN | 08/11 16:00–17:21 | vibe, Autopilot, Sonnet 5.5 | 1 | 223 | 26 | Gói Windows LAN Portable offline |

Ngoài 7 phiên trên còn 2 phiên Kiro ngày 05/11 (16:59–17:26) thuộc một thư mục làm việc khác, không liên quan dự án và không được thống kê.

## 3. Bảng công việc có bằng chứng Kiro trực tiếp (loại A)

Cột "Bằng chứng" ghi mã phiên (8 ký tự đầu) và các tệp kiểm chứng được trong repo. "Hoàn thành" nghĩa là báo cáo cuối phiên nêu đã kiểm, **không phải** nghiệm thu nghiệp vụ.
Các con số là số liệu do Kiro báo cáo ở cuối phiên; lần rà soát này chưa chạy lại chúng (xem mục 9).

| # | Tính năng | Nội dung Kiro thực hiện | Kết quả được báo cáo | File / commit liên quan | Trạng thái | Bằng chứng |
|---|---|---|---|---|---|---|
| A1 | Rà soát độ chính xác và hiệu năng tìm kiếm/chat (05/11) | Rà backend: tìm kiếm, truy xuất căn cứ cho chat, kiểm lại căn cứ, nhật ký kiểm toán. Sửa lỗi chuẩn hóa số hiệu (`15/2020/nđ-cp` ≠ `NĐ-CP`), câu hỏi không dấu, chữ hoa tiếng Việt khi cơ sở dữ liệu dùng locale `C`, chat trích phiên bản đã bị thay thế, khoản lặp khi khoảng hiệu lực trùng ngày | 8 ca thử tự dựng: 3/8 → 8/8; 35 lượt chat liên tiếp không lỗi; 193 test backend đạt | `backend/app/storage/search.py`, `authorized_search.py`, `search_paging.py`, `citations.py`, `workflow/fixed_pipeline.py`, `scripts/benchmark_search.py`, `docs/architecture-decisions/ADR-006-…`, `docs/evidence/2026-11-05-retrieval-accuracy-performance/REPORT.md` | Hoàn thành | `4c10b6e7` 05/11; báo cáo trên |
| A2 | Giới hạn đếm kết quả N = 8.000 và xử lý căn cứ hết hiệu lực (phương án C) | Người dùng chọn phương án và N; Kiro cài đặt `EVIDENCE_SEARCH_COUNT_CAP`, hiển thị "hơn 8.000 khoản"; chỉ bỏ cả kết luận khi căn cứ đầu/đúng Điều được hỏi hết hiệu lực, còn lại loại riêng khoản đó và nêu trong "Lưu ý khi áp dụng thực tế" | Câu có trong 99% khoản: 1,1–1,3 s (trước đó hết thời gian chờ); lỗi đếm "kết quả gần đúng" 5 s → 40 ms; 4 tình huống hiệu lực đúng quy tắc | `backend/app/config.py`, `storage/search.py`, `workflow/fixed_pipeline.py`, `docs/search-v1-runbook.md` | Hoàn thành | `4c10b6e7` 05/11 |
| A3 | Rà soát luồng AI Local/API và độ treo | Kiểm tra chính sách kết nối (Local chỉ máy nội bộ/LAN, API cần HTTPS và quyền). Sửa lỗi model "sẵn sàng" nhưng đã ngừng làm mỗi lượt chat chờ khoảng 30 s: model không kết nối được bị bỏ qua 60 s | Không còn treo ở kịch bản đã thử | `backend/app/model_registry/runtime.py`, `adapters/openai_compatible.py`, `workflow/ai_selection.py` | Hoàn thành | `4c10b6e7` 05/11 |
| A4 | Dọn dữ liệu AI cũ, câu hỏi mẫu, tài liệu, build lại web và desktop | Xóa 20 provider, 10 hồ sơ model, 12 định tuyến cũ (có sự kiện kiểm toán `maintenance.delete_legacy_model_registry` và bản sao lưu); thay câu hỏi mẫu bằng 3 câu chung; xóa nội dung tài liệu mâu thuẫn; build lại `frontend/dist` và tệp desktop | 73 test frontend, 193 test backend đạt; 17/17 test native đạt | `frontend/src/samplePrompts.ts`, `README.md`, `00_README.md`, `docs/SRS_v1.3.md` | Hoàn thành | `4c10b6e7` 05/11 |
| A5 | Gói chạy LAN/portable bản 1 | Script khởi động tính đường dẫn theo vị trí script, dò IP lúc chạy, tự tạo CSDL trống, 4 tài khoản khởi tạo buộc đổi mật khẩu lần đầu, mở/đóng tường lửa | Gói 216 MB (zip 77 MB), chạy thử trên máy phát triển | `deploy/portable/*`, `scripts/package-portable.ps1`, `scripts/start-local-stack.ps1` (chế độ `-Lan`) | Hoàn thành; **chưa thử trên máy thứ hai** | `4c10b6e7` 06/11 |
| A6 | Khảo sát và nạp bộ văn bản thử; hỗ trợ Word/TXT; cấu hình Gemini | Khảo sát 717 tệp (324/378 PDF là bản scan); sao 295 tệp có lớp chữ vào `test-data/van-ban` (thư mục này không đưa lên Git); thêm hỗ trợ `.docx`, `.doc`, `.txt` bằng cách vẽ thành PDF có lớp chữ (không cần Word); đường dẫn `/v1beta/openai`; script nạp theo thư mục | 242 tệp Word chạy không lỗi; trích `.doc` khớp bản Word 99,9% trên 3 tệp; lần nạp đầu chỉ 14/293 văn bản duyệt được (dẫn đến A8) | `backend/app/documents/convert.py`, migration `0008_source_format`, `scripts/import_official_corpus.py`, `docs/ai-model-recommendations.md`, `test-data/README.md` | Hoàn thành | `4c10b6e7` 06/11 |
| A7 | Thiết kế "tra cứu toàn diện + hiệu lực + tổng hợp" | Trao đổi và chốt cùng người dùng 8 vấn đề kiến trúc, hai trục hiệu lực (hiệu lực × xác minh), nhóm văn bản, Hybrid Auto, quyền xác nhận, trần tổng hợp; viết bản thiết kế chốt và bộ 15 câu hỏi kiểm thử | Bản thiết kế được người dùng duyệt | `docs/thiet-ke-tra-cuu-hieu-luc.md`, `test-data/cau-hoi-kiem-thu-vong-1.md` | Hoàn thành (thiết kế) | `4c10b6e7` 06–07/11; sáu tệp "artifact" của phiên |
| A8 | G0 – neo khoản nhiều trang | Mỗi khoản lưu đoạn nguồn từng trang, cây Điều–Khoản–Điểm có `parent_id`/`path`/`citation_label`, chia khoản > 4.000 ký tự, cờ nghi ngờ lớp chữ, công cụ dựng lại cây | Từ 14/293 lên 286/293 văn bản duyệt được; 0/21.724 khoản không neo; 193 test backend | `documents/node_writer.py`, `tree_parser.py`, `spans.py`, migration `0009_node_structure`, `scripts/rebuild_node_tree.py` | Hoàn thành | `4c10b6e7` 07/11 |
| A9 | G1.0 – chính sách giai đoạn AI, Hybrid Auto | Số lượt gọi model theo giai đoạn do quản trị đặt (thay giới hạn cứng 2), Local→API khi local không đạt hoặc "phân tích sâu", Local Only tuyệt đối không gọi API, nhật ký dùng và trần chi phí | `verify.ps1` 12/12 (backend 206, frontend 74, 10 cặp migration) | migration `0010_ai_policy`, `model_registry/runtime.py`, `stages.py`, ADR-007 | Hoàn thành | workflow `wf_9ba3807d…`, phiên `4c237fbe` 07/11 |
| A10 | G1 – hiệu lực văn bản | Đọc ngày hiệu lực và quan hệ sửa đổi/bãi bỏ bằng quy tắc; đề xuất cho người duyệt; hai trục trạng thái; "Còn hiệu lực + Đã xác minh" chỉ sinh từ xác nhận của người | HTTP 27/27 | `backend/app/effectivity/*`, migration `0011_effectivity`, ADR-008, `frontend/src/components/EffectivityReviewPanel.tsx` | Hoàn thành | workflow `wf_ffe44206…`, phiên `79b7dcee` 07/11 |
| A11 | G2 – tìm toàn diện 4 kênh + embedding | Kênh chính xác, theo nghĩa (vector), khái niệm, quan hệ; hợp bằng RRF; bộ kết quả cố định theo lượt; chỉ mục vector không cố định chiều | HTTP 17/17 | `storage/comprehensive.py`, `embeddings.py`, `scripts/build_embeddings.py`, migration `0012_comprehensive_search`, ADR-009 | Hoàn thành | `79b7dcee` 07/11 |
| A12 | G3 – quan hệ cấp Điều/Khoản/Điểm | Nhận biết sửa đổi/bãi bỏ ở mức điều khoản, kế thừa vào kết quả tìm | 31/31 quan hệ đối chiếu đúng (đối chiếu do tác nhân soạn, chưa được cán bộ xác nhận); HTTP 11/11 | `effectivity/node_paths.py`, `evaluation/coverage/g3_relations_reference.json` | Hoàn thành (chưa nghiệm thu nghiệp vụ) | `79b7dcee` 07/11 |
| A13 | G4 – nhóm nội dung và tổng hợp có kiểm chứng | 11 nhóm nội dung ban đầu, gán nhãn bằng quy tắc và model, tổng hợp theo lô, kiểm bằng mã trước khi hiển thị ý | Local 10/10; API 11/11 (gồm 3 lượt gọi API thật, 12/12 ý qua kiểm tra) | `synthesis/*`, migration `0013_content_groups`, `api/v1/synthesis.py` | Hoàn thành | `79b7dcee` 07/11 |
| A14 | G5 – đo bao phủ | 8 chủ đề, 24 câu, 42 căn cứ bắt buộc; đo theo từng kênh | Tìm thấy 40/42; `verify.ps1` 12/12 (backend 218, frontend 74, 13 cặp migration) | `evaluation/coverage/*`, `docs/implementation-status.md` | Hoàn thành (căn cứ bắt buộc do tác nhân soạn, chưa xác nhận) | `79b7dcee` 07/11 |
| A15 | So sánh reranker | Đo RRF thuần, rerank LLM, Qwen3-Reranker-0.6B trên CPU (Recall@k, MRR, NDCG, thời gian, RAM); chẩn đoán hai căn cứ không tìm thấy là lỗi truy xuất, không phải xếp hạng; người dùng quyết định giữ RRF làm mặc định | RRF: R@10 0,762; LLM 0,691; Qwen3 0,810 — khác biệt MRR/NDCG nằm trong khoảng tin cậy chứa 0; 32–48 s mỗi câu với hai bản rerank | `evaluation/coverage/*`, `scripts/local_reranker_server.py`, `storage/cross_encoder.py`, `docs/evidence/2026-11-07-g5-rerank/REPORT.md` | Hoàn thành | `4c10b6e7` 07/11 |
| A16 | Bộ 50 câu, dựng lại dữ liệu và sao lưu | Soạn thêm 26 câu; dựng lại CSDL 100 văn bản (7.230 vector, 42 phút); `pg_dump` và kiểm khôi phục (số dòng, tổng kiểm văn bản và vector, 98 chỉ mục, HNSW) | RRF 50 câu: R@10/20/50/toàn bộ 0,865/0,892/0,932/0,960, MRR 0,790 | `scripts/verify_db_restore.py`, `evaluation/coverage/topics.json`, `…/REPORT-50-cau.md` | Hoàn thành | `4c10b6e7` 07/11 |
| A17 | Khóa phá hòa RRF ổn định | Thay UUID ngẫu nhiên bằng khóa (số hiệu, SHA-256 tệp, vị trí khoản) ở `_rrf`, kênh chính xác và kênh quan hệ | Hai CSDL nhập độc lập: thứ tự giống hệt 50/50 câu (trước 45/50 và 41/50); backend 225, frontend 77 | `storage/search_paging.py`, `storage/comprehensive.py`, `evaluation/coverage/check_tiebreak_stability.py` | Hoàn thành | `4c10b6e7` 08/11 08:07 |
| A18 | Quản lý embedding trong Admin Portal | Đổi/thêm model embedding trên giao diện, kiểm tương thích, tạo lại vector bằng tác vụ chạy nền có tiến độ, chỉ chuyển chỉ mục sau khi kiểm xong, giữ vector cũ | `verify.ps1` 12/12 và chạy thử với Ollama thật | migration `0014_embedding_jobs`, `storage/embedding_jobs.py`, `frontend/src/components/EmbeddingManager.tsx` | Hoàn thành | `f6f39653` 07/11 |
| A19 | Sửa chức năng tra cứu USER | Ca lỗi "Thủ tục bổ nhiệm, miễn nhiệm": chấm mức liên quan theo cụm từ, loại khối danh mục dài/lặp, phân tích câu hỏi không tách âm tiết, hiển thị nhận định ngắn, mở đúng PDF gốc | Kiểm trên CSDL thật 100 văn bản qua HTTP và Chrome headless; 12/12 | `storage/relevance.py`, `storage/chat_retrieval.py`, `workflow/chat_answer.py`, `docs/evidence/2026-11-08-user-lookup/REPORT.md` | Hoàn thành; chưa kiểm TXT và desktop Tauri | `201bebb1` 08/11 |
| A20 | Diễn giải AI và OCR PDF scan | Model nhận câu hỏi và chỉ nhận căn cứ đã lọc; kiểm chứng bằng mã chặt hơn; quy trình OCR trang scan có duyệt từng trang | "Xử phạt nồng độ cồn" trả "chưa tìm thấy" thay vì ý sai chủ đề; "Mở văn bản gốc" đúng tệp, đúng trang, đúng quyền | `synthesis/focus.py`, `focused.py`, `checks.py`, `documents/ocr.py`, `native_pdf.py`, migration `0015_ocr_page_review`, `docs/evidence/2026-11-08-ai-ocr/REPORT.md` | Hoàn thành; chưa kiểm Tauri/TXT | `201bebb1` 08/11 |
| A21 | Thiết kế lại giao diện Model Registry | Hai form AI Local và AI API, kho khóa API mã hóa bằng DPAPI (khóa không trả lại qua API), kiểm tra kết nối trước khi lưu/áp dụng, phân công model theo chức năng | `verify.ps1` 12/12; backend 288, frontend 86 | `model_registry/secret_store.py`, `diagnostics.py`, `frontend/src/components/ai/*`, `docs/evidence/2026-11-08-model-registry-ui/REPORT.md` | Hoàn thành; chưa gọi thật OpenAI/Gemini | `201bebb1` 08/11 |
| A22 | Windows LAN Portable offline | Gói chạy một lệnh `Start-Server.bat`, kèm sao lưu/khôi phục, kiểm gói, mở tường lửa; builder trong repo | Gói 4,5 GB (zip 3,6 GB) đặt ngoài repo; kiểm thử chấp nhận trên máy phát triển | `deploy/lan-portable/*`, `scripts/build-lan-portable.ps1` | Hoàn thành; **chưa thử trên máy Windows vật lý khác** | `d0b73228` 08/11 |
| A23 | Tệp `.bat` mở app để thử giao diện | Mở/tắt PostgreSQL, Ollama và web trên cổng loopback; kiểm đăng nhập và tìm kiếm | Kiểm bật–tắt, không sót tiến trình | `Mo-ung-dung-test.bat`, `Dung-ung-dung-test.bat`, `ung-dung-test.ps1` | Hoàn thành | `4c10b6e7` 08/11 08:50 |
| A24 | Kiểm kê dữ liệu ổ C, cấu hình quyền Kiro | Kiểm kê dữ liệu, soạn quyền theo workspace; tệp `.kiro/settings/permissions.yaml` trong repo **giống từng byte** tệp Kiro soạn lúc 09:08 (SHA-256 `58EF3EDA…C95C209`) và được người dùng áp dụng 09:17. **Sai sót:** Kiro sửa nhầm biến môi trường của công cụ khác, người dùng phản đối, Kiro đã hoàn lại | Quyền áp dụng; dữ liệu Kiro chuyển sang ổ E | `.kiro/settings/permissions.yaml` | Hoàn thành một phần (phần ghi vào cài đặt người dùng do người dùng tự chạy) | `b63f6d04` 07/11 |
| A25 | Rà soát hồ sơ Kiroween (giai đoạn 1) | Kiểm kê Git, `~/.kiro`, phiên, specs/steering/hooks/MCP; lập tài liệu này | — | `KIRO_WORK_SUMMARY.vi.md`, `KIRO_WORK_SUMMARY.en.md` | Hoàn thành | `4c10b6e7` 09/11 |
| A26 | Hồ sơ Kiroween: specs, steering, hooks, tài liệu song ngữ (**lượt hiện tại**) | Dựng lại 10 nhóm spec (30 tệp EARS/design/tasks), 3 steering, 2 hook qua `createHook` (lệnh hook chạy thử trực tiếp), 14 bản dịch tiếng Việt, và bản Việt/Anh của README, tóm tắt Kiro, dòng thời gian, mô tả hệ thống, hướng dẫn, triển khai, tổng quan kiến trúc | Commit `34cff8b`: 66 tệp (59 mới, 7 sửa). Chưa chạy lại kiểm thử; IDE chưa tự kích hoạt hook | `.kiro/*`, `docs/en/*`, `docs/vi/*`, `*.en.md`, `*.vi.md` | Hoàn thành | `4c10b6e7`, 09/11 từ 17:19 |
| A27 | Thống kê lại đóng góp của Kiro (**lượt hiện tại**) | Tính lại thống kê theo nguyên tắc mục 8.1: đưa Markdown và cấu hình vào, chỉ loại dữ liệu đầu vào và tệp không phải sản phẩm; tách tệp tác động và tệp `fs_write`; tách lịch sử và lượt hiện tại | Mục 8, phụ lục thống kê | `KIRO_STATS_APPENDIX.vi.md`, `KIRO_STATS_APPENDIX.en.md` | Hoàn thành | `4c10b6e7`, 09/11 |

## 4. Công việc có trong source, không có nhật ký Kiro (loại B)

Các mục này tồn tại trong repo nhưng **không có lệnh ghi/sửa của Kiro trong bản ghi phiên còn lưu**. Chủ dự án xác nhận Kiro được dùng từ 30/10 đến ít nhất 11/11/2026; việc dùng trên hai máy được xác nhận đến 09/11, còn cập nhật 10–11/11 không có log để quy từng tệp. Vì vậy một phần có thể do Kiro hỗ trợ nhưng không thể quy từng tệp cho Kiro hay cho tác giả. Các tệp có mốc trước 30/10 (hồ sơ yêu cầu, khung ban đầu) nằm ngoài khoảng xác nhận.

| Thành phần | Căn cứ để nói "có trong source" | Vì sao chưa xác định |
|---|---|---|
| Hồ sơ yêu cầu và thiết kế gốc: `docs/HOSO_BAN_GIAO.md`, `docs/SRS_v1.3.md` (bản ban đầu), `docs/history/SRS_v1.2.1.md`, `docs/PROMPT_KHOI_DONG.md`, `parts/*`, ADR-000…004 | Tệp sớm nhất có mốc 21–22/10/2026; `PROJECT_TIMELINE.md` nói tác giả viết mô tả, đặc tả, kế hoạch trước 30/10 | Trước mọi bản ghi Kiro; Kiro chỉ sửa một số đoạn của SRS ngày 05/11 |
| Khung ban đầu: `backend/app/auth_acl/*`, `evidence/*`, `memory/*`, `vietnamese_nlp/*`, `api/v1/auth.py`, `execution.py`, `guards.py`; migration `0001…0007`; `src-tauri/*` (Tauri 2, 12 tệp); các thành phần giao diện nền (`LoginPanel`, `DesktopOrb`, …) | Có trong repo; mốc sửa sớm nhất 22/10 | 0/4 tệp `auth_acl`, 0/3 `evidence`, 0/2 `memory`, 0/3 `vietnamese_nlp`, 0/12 `src-tauri`, migration 0001–0007 không có lệnh ghi của Kiro |
| Search v1 bản đầu (ADR-005, `storage/search.py`) và báo cáo `docs/evidence/2026-10-22-*`, `2026-10-26-*`, `2026-10-27-*`, `2026-10-31-*`, `2026-11-01-app-audit` | Báo cáo và benchmark có trong repo, mốc 22/10–01/11 | Không có phiên Kiro nào ghi cho giai đoạn này; Kiro chỉ sửa `search.py`, `search_paging.py` từ 05/11 (A1, A2) |
| Quản lý văn bản trong Admin Portal và hiển thị tra cứu (commit `ba596ce`, 09/11): `documents/management_{access,read,write}.py`, migration `0016_document_management`, `storage/lookup_visibility.py`, `AdminDocumentManager.tsx`, `AdminDocumentDetail.tsx`, các test đi kèm | Có trong repo và Git | **17 trong 52 file của commit này không có lệnh ghi của Kiro**; khoảng 08/11 17:21 → 09/11 17:19 không có phiên Kiro nào được ghi, trong khi 3 commit (09:25, 10:00, 12:04) nằm trong khoảng đó |
| Tài liệu mô tả hệ thống và hướng dẫn: `docs/TAI_LIEU_MO_TA_HE_THONG.md`, `docs/HUONG_DAN_SU_DUNG_VA_CAU_HINH_AI.md` (commit `74e7e60`, `caa2e7a`) | Có trong Git | Không có lệnh ghi của Kiro |
| CI, giấy phép, công bố: `.github/workflows/ci.yml`, `LICENSE`, `NOTICE`, `PROJECT_TIMELINE.md` | Có trong Git (commit do tác giả) | Do tác giả cam kết/ghi; không thuộc phạm vi Kiro |
| Thiết kế giao diện qua MCP Stitch: `.stitch/DESIGN.md`, `SITE.md`, `metadata.json` (hệ thống thiết kế, sơ đồ màn hình, ba màn hình) | Có trong Git; máy chủ MCP `stitch` ở mức người dùng (từ xa, `https://stitch.googleapis.com/mcp`, khóa API gửi qua header và không ghi lại ở đây); mọi `mcp.log` còn lưu (10 thư mục nhật ký, 05/11–09/11/2026) ghi nó kết nối và liệt kê công cụ lúc bắt đầu phiên; ba tệp có mốc 22/10/2026 (chỉ mang tính tham khảo) | Không có lệnh ghi của Kiro và không có nhật ký lệnh gọi thiết kế Stitch nên không nêu được ngày sử dụng. Dùng cho thiết kế giao diện: loại B (chủ dự án xác nhận) |
| Công cụ nhỏ: `tools/*`, `scripts/seed_local_runtime.py`, `smoke_app_runtime.py`, `validate_*`, `evaluation/scripts/*` | Có trong repo | Không có lệnh ghi của Kiro |

Lưu ý: thay đổi không có bản ghi Kiro **không** được thống kê là của Kiro, kể cả khi nằm trong khoảng thời gian chủ dự án xác nhận.

## 5. Thông tin tái dựng từ code và tài liệu (loại C)

Các mô tả dưới đây dựa trên việc đọc mã và tài liệu hiện có, không dựa trên bản ghi phiên. Chúng mô tả hệ thống đang có, không khẳng định ai đã xây.

| Nội dung | Căn cứ trong source |
|---|---|
| Vai trò `SYS_ADMIN`, `AUDITOR`, `CURATOR`, `REVIEWER`, `USER`; phân quyền theo danh mục (`category_acl`, `can_query`, `can_review`) | `backend/app/auth_acl/*`, `migrations/0002_auth_admin`, `0011_effectivity` |
| Quy trình nạp → bản nháp → duyệt bởi người khác → văn bản đã duyệt; chống nạp trùng bằng SHA-256 nội dung | `documents/draft.py`, `review.py`, `deduplication.py`, migration `0001`, `0005` |
| Trích dẫn gắn nguồn: mỗi căn cứ có số hiệu, nhãn Điều/Khoản/Điểm, trang, mã băm tệp, lời trích khớp từng ký tự với văn bản nguồn | `storage/citations.py`, `docs/citation-contract.md`, `docs/pdf-anchor-coordinate-contract.md` |
| Nạp PDF: pypdfium2 trích chữ và hộp ký tự trong tiến trình con cô lập; OCR (Tesseract) chỉ khi trang trống hoặc nghi lớp chữ lỗi | `documents/native_pdf.py`, `pdf_worker.py`, `isolated.py`, `ocr.py` |
| Hệ thống chạy hoàn toàn cục bộ được: Local Only không gọi API ngoài; API chỉ khi được cấu hình và cho phép | `model_registry/*`, `docs/threat-model.md` |
| Ứng dụng web React 18 + Vite 5 + TypeScript 5; backend FastAPI + asyncpg; PostgreSQL với pgvector; shell Tauri 2 cho bản desktop | `frontend/package.json`, `backend/pyproject.toml`, `src-tauri/*`, các migration |
| Quản lý văn bản trong Admin Portal (mô tả trong commit `ba596ce` và hướng dẫn) | `documents/management_*.py`, `AdminDocumentManager.tsx` — mô tả chức năng suy ra từ mã, không xác định tác nhân |
| 10 nhóm spec, 3 steering, 2 hook bổ sung ngày 09/11/2026 | `.kiro/specs/*`, `.kiro/steering/*`, `.kiro/hooks/*`; mỗi tệp ghi rõ là dựng lại từ code |
| Hệ thống thiết kế giao diện và sơ đồ màn hình (Stitch): chữ Segoe UI, bảng màu, bố cục ba cột, ba màn hình (không gian chứng cứ của người dùng, ô chat nổi, Admin Portal) | `.stitch/DESIGN.md`, `.stitch/SITE.md`, `.stitch/metadata.json` (`stitchProjectId` `local-evidence-rag-ui`); mô tả thiết kế như đã viết trong các tệp này, không khẳng định cách tạo ra |

## 6. Dòng thời gian phát triển

Mốc trước 05/11 suy ra từ thời gian sửa tệp và là **chỉ số tham khảo**: tệp đã đổi trong thư mục làm việc được đồng bộ lại lúc 17:14 ngày 09/11, nên thời gian sửa không còn đáng tin với các tệp đó.

| Ngày | Sự kiện | Loại |
|---|---|---|
| 21–22/10/2026 | Hồ sơ yêu cầu (SRS 1.2.1, prompt khởi động), khung mã đầu tiên, các báo cáo kiểm toán/"takeover" đầu tiên | B |
| 26–27/10 | Báo cáo kiểm toán mã, loại trùng nội dung; có bản `pg_dump` của CSDL dev | B |
| 30/10 | **Mốc bắt đầu khoảng thời gian chủ dự án xác nhận dùng Kiro** (không có nhật ký cục bộ) | B |
| 31/10 | Search v1, bộ benchmark và rà soát; tệp CI | B |
| 01/11 | Báo cáo audit ứng dụng | B |
| **05/11 17:27** | **Bản ghi Kiro sớm nhất cho dự án.** 17:35: rà soát độ chính xác/hiệu năng; chốt N = 8.000 và phương án hiệu lực C; rà soát luồng AI; dọn dữ liệu AI cũ; build web và desktop | A1–A4 |
| 06/11 | Gói LAN/portable v1; khảo sát 717 tệp; hỗ trợ Word/TXT; trả lời hàng loạt câu hỏi kiến trúc; lập kế hoạch vòng thử | A5–A6 |
| 07/11 sáng | Chốt thiết kế; G0 (09:19–10:47); chuyển dữ liệu Kiro sang ổ E (08:51–09:16) | A7, A8, A24 |
| 07/11 10:54–11:55 | Workflow G1.0 | A9 |
| 07/11 11:57–15:20 | Workflow G1→G5 (có tạm dừng và chạy tiếp lúc 14:27) | A10–A14 |
| 07/11 15:29 → 21:00 | Benchmark reranker; kiểm kê dữ liệu 100 văn bản; bộ 50 câu; dựng lại CSDL, `pg_dump` | A15, A16 |
| 07/11 19:41–21:22 | Quản lý embedding trong Admin Portal | A18 |
| 08/11 08:07 | Khóa phá hòa RRF ổn định | A17 |
| 08/11 08:50 | Tệp `.bat` mở app thử giao diện | A23 |
| 08/11 10:22–15:35 | Sửa tra cứu USER, Diễn giải AI, OCR, giao diện Model Registry | A19–A21 |
| 08/11 16:00–17:21 | Windows LAN Portable offline | A22 |
| 08/11 20:32 | **Commit đầu tiên lên Git**: ảnh chụp 404 file (289bf62); 20:34–21:02 thêm tài liệu, CI | B |
| 09/11 09:25–12:04 | Commit quản lý văn bản (`ba596ce`), làm rõ tài liệu (`caa2e7a`), giấy phép và công bố (`08b0021`); **không có phiên Kiro nào được ghi trong khoảng này** | B |
| 09/11 | Mốc chốt của số liệu nhật ký ban đầu; chủ dự án sau đó xác nhận Kiro tiếp tục được dùng đến ít nhất 11/11 | B |
| 09/11 17:19 trở đi | Phiên rà soát hồ sơ này; bổ sung `.kiro` specs/steering/hooks và tài liệu song ngữ | A25, C |
| 11/11/2026 | Cập nhật sau build bằng Kiro IDE; Kiroween vẫn đang diễn ra đến hạn 04/12 | B |

## 7. Kiểm kê tài liệu Kiro trong dự án

| Hạng mục | Kết quả |
|---|---|
| `.kiro/specs`, `.kiro/steering`, `.kiro/hooks` trước ngày 09/11/2026 | **Không có** (không tìm thấy ở repo, bản sao lưu, `~/.kiro`) |
| `.kiro/specs` (10 nhóm), `.kiro/steering` (3 tệp), `.kiro/hooks` (2 hook) ban đầu từ 09/11/2026 | **Dựng lại từ code** (loại C), tiếng Anh để Kiro đọc trực tiếp; bản dịch tiếng Việt ở `docs/vi/kiro/`. Spec hiệu lực và ghim trích dẫn cập nhật 11/11; hook được sửa ngày 09/11/2026 (ruff/mypy và eslint/tsc theo phạm vi tệp qua `scripts/kiro-hook-check.ps1`); đã quan sát `PostFileSave` tự kích hoạt khi agent ghi tệp thử, chưa thử lưu tay trong editor |
| `.kiro/settings/permissions.yaml` trong repo | Có (đã nằm trên GitHub từ commit đầu); là tệp Kiro soạn và người dùng áp dụng (A24) |
| `.kiro/specs`, `steering`, `hooks` ở `~/.kiro` và ở bản sao lưu cũ | Không có. Thư mục người dùng chỉ có cài đặt cá nhân, kỹ năng (skills), cơ sở bộ nhớ và nhật ký, không phải tài liệu dự án |
| Bản sao dự án `Evidence_RAG_Handoff-20261109-171404` | Có `.kiro/settings/permissions.yaml` giống từng byte; không có gì khác |
| Cấu hình MCP | Chỉ ở mức người dùng (`~/.kiro/settings/mcp.json`), có 9 máy chủ; chỉ `stitch` liên quan thiết kế giao diện; còn lại là công cụ cá nhân. Không đưa vào repo (chứa đường dẫn riêng của máy, cấu hình cá nhân và header khóa API) |
| MCP: Stitch – thiết kế UI, kết quả trong `.stitch/` | Máy chủ `stitch` (từ xa, streamable-HTTP, `https://stitch.googleapis.com/mcp`, mức người dùng, đang bật). Các `mcp.log` còn lưu ghi `mcp.connect.ok` và `mcp.listTools.ok` của `stitch` lúc bắt đầu phiên; không có lệnh gọi thiết kế Stitch nào trong các `kiro.log` còn lưu. Dùng cho thiết kế giao diện: **loại B** (chủ dự án xác nhận), không có ngày sử dụng |
| Cách làm việc | Mọi phiên còn lưu chạy chế độ trò chuyện tự do (`vibe`) hoặc workflow; cài đặt phiên ghi `specPlanEnabled = false`. **Spec/steering/hook được thêm ban đầu ngày 09/11/2026 là tài liệu dựng lại, không phải lịch sử Kiro; một số spec cập nhật ngày 11/11.** |

## 8. Phương pháp và số liệu thống kê

### 8.1 Nguyên tắc tính (điều chỉnh theo yêu cầu của chủ dự án, 09/11/2026)

1. **Chỉ loại tài liệu nghiệp vụ đầu vào** của Evidence RAG (PDF, DOC, DOCX, TXT văn bản pháp luật, nghị định, thông tư, quyết định, công văn được tải về hoặc nhập vào kho), tệp tải từ Internet, trọng số model, phụ thuộc, runtime, cache và dữ liệu tự sinh. Không có tệp đầu vào nào nằm trong Git (chúng ở thư mục bị `.gitignore`); trong Git chỉ có {NX} tệp bị loại (phông chữ, tệp khóa phụ thuộc, biểu tượng nhị phân, `docs/openapi.json` sinh tự động, bảng kê corpus công khai) — danh sách ở phụ lục.
2. **Không loại tệp chỉ vì là Markdown.** Tài liệu Kiro viết để phát triển dự án (requirements, design, tasks, SRS, ADR, README, báo cáo, hướng dẫn, specs, steering) được tính như mã. Tài liệu được nhập để tra cứu thì không.
3. Tệp được tính khi: có trong Git ở commit `34cff8b`, và có ít nhất một lệnh ghi/sửa của Kiro (`fs_write`, `str_replace`, `fs_append`, `delete_file`, `semantic_rename`, `smart_relocate`, `createHook`) trong bản ghi phiên, bất kể phần mở rộng.
4. **Hai chỉ số khác nhau:** *tệp được tác động* (có ít nhất một lệnh ghi/sửa) và *tệp có lệnh `fs_write`* (Kiro tạo hoặc ghi đè toàn bộ tệp tại thời điểm đó). Tệp chỉ có `str_replace`/`fs_append` được tính là tác động, không phải viết toàn bộ.
5. **Bằng chứng lịch sử và công việc lượt hiện tại được tách riêng.** Lượt hiện tại bắt đầu từ yêu cầu hồ sơ Kiroween (09/11/2026 17:19). Specs, steering, hooks và tài liệu song ngữ tạo trong lượt này là công việc Kiro **trong lượt hiện tại**, không phải bằng chứng về lịch sử phát triển trước đó.
6. Tính đến snapshot 11/11/2026, chủ dự án xác nhận Kiro đã được dùng từ 30/10 và tiếp tục đến 11/11; Kiroween còn đến hạn 04/12. Các số liệu trong tài liệu này chỉ tính bản ghi/commit thuộc phạm vi nêu ở trên, không phải tổng kết cuối kỳ. Phần không có nhật ký **không** được cộng vào số liệu.

### 8.2 Nguồn và định nghĩa

- **Nguồn:** `session.json`, `messages.jsonl` của 7 phiên; `workflow-state.json`; `git ls-tree` ở commit `34cff8b`; mã và tài liệu hiện tại.
- **Tệp tính:** 471 trong 480 tệp đang theo dõi (loại 9).
- **Số tệp là cận dưới:** tệp tạo bằng lệnh shell không được đếm. Có 29 tệp được nhắc trong lệnh shell có động từ ghi nhưng không có lệnh chỉnh sửa; việc nhắc tới không chứng minh đã ghi, nên **không tính** (danh sách ở phụ lục).
- **Số dòng là cận trên về quyền tác giả:** sửa một tệp không có nghĩa viết toàn bộ; thay đổi của người sau đó cũng không tách được. Số dòng trong tệp có `fs_write` gần với "Kiro viết toàn bộ" hơn nhưng vẫn là cận trên.
- Dòng được đếm ở trạng thái commit `34cff8b`. Các tệp thống kê/tóm tắt cập nhật sau commit này thuộc lượt hiện tại và không có trong số liệu.

### 8.3 Tổng hợp theo loại tệp

| Nhóm | Tệp tính | Có lệnh Kiro | Có `fs_write` | Dòng | Dòng trong tệp có lệnh Kiro | Dòng trong tệp có `fs_write` |
|---|---:|---:|---:|---:|---:|---:|
| **Tổng** | 471 | 257 | 208 | 76.975 | 54.957 (71%) | 29.926 (39%) |
| Mã (`.py`, `.ts`, `.tsx`, `.sql`, `.ps1`, `.bat`, `.cmd`, `.rs`, `.css`, `.js`, `.mjs`, `.html`) | 300 | 161 | 120 | 60.609 | 46.189 (76%) | 23.659 (39%) |
| Tài liệu (`.md`, `.txt`) | 142 | 88 | 81 | 14.620 | 8.364 (57%) | 5.914 (40%) |
| Cấu hình và dữ liệu kỹ thuật (`.json`, `.yaml`, `.toml`, `.env`, `.example`, tệp không đuôi) | 29 | 8 | 7 | 1.746 | 404 (23%) | 353 (20%) |

### 8.4 Lịch sử và lượt hiện tại

| Giai đoạn | Tệp | Lệnh công cụ | Lệnh ghi/sửa | Ghi chú |
|---|---:|---:|---:|---|
| Bản ghi lịch sử (05/11 → 09/11 17:19) | 194 (mã 161, tài liệu 27, cấu hình 6) | 3.704 | 1.274 | Con số 194/421 công bố trước đây không đổi; mẫu số nay là 412 tệp tính trong 421 tệp ở commit `08b0021` (loại 9) |
| Lượt hiện tại (từ 09/11 17:19, tính đến lúc lập thống kê) | 63 tệp lần đầu bị Kiro chạm tới (59 tạo mới, 4 có sẵn) và 3 tệp lịch sử được sửa lại | 220 | 95 | Specs, steering, hooks, tài liệu song ngữ, thống kê. Số lệnh còn tăng khi phiên tiếp tục |
| **Cộng** | **257** / 471 (55%) | 3.924 | 1.369 | |

Phân bố lệnh công cụ (tổng): `execute_pwsh` 1.403, `str_replace` 993, `read_file` 723, `fs_write` 358, `grep_search` 319, `list_directory` 29, `update_session_information` 16, `remote_web_search` 13.

### 8.5 Theo khu vực

| Khu vực | Tệp tính | Có lệnh Kiro | Có `fs_write` | Dòng | Dòng trong tệp có lệnh Kiro | Dòng trong tệp có `fs_write` |
|---|---:|---:|---:|---:|---:|---:|
| `(root)` | 15 | 10 | 10 | 1.296 | 971 (75%) | 971 (75%) |
| `.github` | 1 | 0 | 0 | 29 | 0 (0%) | 0 (0%) |
| `.kiro` | 36 | 35 | 35 | 1.349 | 1.274 (94%) | 1.274 (94%) |
| `.stitch` | 3 | 0 | 0 | 69 | 0 (0%) | 0 (0%) |
| `backend/(root)` | 1 | 1 | 0 | 51 | 51 (100%) | 0 (0%) |
| `backend/app/(root)` | 7 | 5 | 0 | 2.871 | 2.865 (100%) | 0 (0%) |
| `backend/app/api` | 13 | 5 | 3 | 2.737 | 2.163 (79%) | 731 (27%) |
| `backend/app/auth_acl` | 4 | 0 | 0 | 347 | 0 (0%) | 0 (0%) |
| `backend/app/documents` | 20 | 11 | 4 | 3.487 | 2.581 (74%) | 1.085 (31%) |
| `backend/app/effectivity` | 7 | 7 | 7 | 2.372 | 2.372 (100%) | 2.372 (100%) |
| `backend/app/evidence` | 3 | 0 | 0 | 197 | 0 (0%) | 0 (0%) |
| `backend/app/memory` | 2 | 0 | 0 | 579 | 0 (0%) | 0 (0%) |
| `backend/app/migrations` | 35 | 17 | 17 | 1.432 | 570 (40%) | 570 (40%) |
| `backend/app/model_registry` | 9 | 7 | 4 | 2.099 | 2.080 (99%) | 486 (23%) |
| `backend/app/storage` | 14 | 10 | 6 | 5.726 | 5.553 (97%) | 3.544 (62%) |
| `backend/app/synthesis` | 6 | 6 | 6 | 1.793 | 1.793 (100%) | 1.793 (100%) |
| `backend/app/vietnamese_nlp` | 3 | 0 | 0 | 186 | 0 (0%) | 0 (0%) |
| `backend/app/workflow` | 6 | 3 | 2 | 1.425 | 1.304 (92%) | 625 (44%) |
| `backend/tests` | 48 | 17 | 11 | 8.832 | 4.541 (51%) | 2.498 (28%) |
| `configs` | 5 | 1 | 1 | 72 | 28 (39%) | 28 (39%) |
| `deploy` | 22 | 22 | 21 | 2.363 | 2.363 (100%) | 2.304 (98%) |
| `docs` | 82 | 39 | 34 | 10.542 | 5.675 (54%) | 3.404 (32%) |
| `evaluation` | 28 | 13 | 12 | 4.456 | 1.536 (34%) | 1.416 (32%) |
| `frontend/(root)` | 7 | 0 | 0 | 136 | 0 (0%) | 0 (0%) |
| `frontend/e2e` | 2 | 0 | 0 | 304 | 0 (0%) | 0 (0%) |
| `frontend/public` | 1 | 0 | 0 | 5 | 0 (0%) | 0 (0%) |
| `frontend/src` | 56 | 38 | 26 | 17.013 | 15.068 (89%) | 5.148 (30%) |
| `parts` | 3 | 0 | 0 | 1.180 | 0 (0%) | 0 (0%) |
| `scripts` | 17 | 9 | 8 | 2.901 | 2.130 (73%) | 1.638 (56%) |
| `src-tauri` | 9 | 0 | 0 | 852 | 0 (0%) | 0 (0%) |
| `test-data` | 2 | 1 | 1 | 131 | 39 (30%) | 39 (30%) |
| `tools` | 4 | 0 | 0 | 143 | 0 (0%) | 0 (0%) |

### 8.6 Theo phần mở rộng

| Đuôi | Tệp tính | Có lệnh Kiro | Có `fs_write` | Dòng | Dòng trong tệp có lệnh Kiro | Dòng trong tệp có `fs_write` |
|---|---:|---:|---:|---:|---:|---:|
| `(none)` | 3 | 0 | 0 | 276 | 0 (0%) | 0 (0%) |
| `.bat` | 9 | 9 | 9 | 107 | 107 (100%) | 107 (100%) |
| `.cmd` | 5 | 5 | 5 | 42 | 42 (100%) | 42 (100%) |
| `.css` | 2 | 1 | 0 | 3.537 | 3.493 (99%) | 0 (0%) |
| `.env` | 2 | 2 | 2 | 100 | 100 (100%) | 100 (100%) |
| `.example` | 2 | 1 | 1 | 29 | 28 (97%) | 28 (97%) |
| `.html` | 1 | 0 | 0 | 13 | 0 (0%) | 0 (0%) |
| `.js` | 1 | 0 | 0 | 25 | 0 (0%) | 0 (0%) |
| `.json` | 15 | 4 | 4 | 1.131 | 225 (20%) | 225 (20%) |
| `.md` | 139 | 85 | 78 | 14.326 | 8.070 (56%) | 5.620 (39%) |
| `.mjs` | 1 | 0 | 0 | 279 | 0 (0%) | 0 (0%) |
| `.ps1` | 8 | 6 | 6 | 2.730 | 2.472 (91%) | 2.472 (91%) |
| `.py` | 180 | 87 | 58 | 38.306 | 27.973 (73%) | 15.363 (40%) |
| `.rs` | 5 | 0 | 0 | 725 | 0 (0%) | 0 (0%) |
| `.sql` | 32 | 16 | 16 | 1.329 | 527 (40%) | 527 (40%) |
| `.toml` | 2 | 1 | 0 | 73 | 51 (70%) | 0 (0%) |
| `.ts` | 16 | 7 | 5 | 3.495 | 3.000 (86%) | 939 (27%) |
| `.tsx` | 40 | 30 | 21 | 10.021 | 8.575 (86%) | 4.209 (42%) |
| `.txt` | 3 | 3 | 3 | 294 | 294 (100%) | 294 (100%) |
| `.yaml` | 4 | 0 | 0 | 108 | 0 (0%) | 0 (0%) |
| `.yml` | 1 | 0 | 0 | 29 | 0 (0%) | 0 (0%) |

Danh sách từng tệp, tệp bị loại và tệp ứng viên chưa tính: [`KIRO_STATS_APPENDIX.vi.md`](KIRO_STATS_APPENDIX.vi.md).

**Dữ liệu nhạy cảm:** lời nhắn của người dùng trong bản ghi có chứa một khóa API (đưa tạm để thử); không trích lại ở đây và không có khóa nào được ghi vào repository.

## 9. Giới hạn chưa xác minh

- Chưa chạy lại bộ kiểm thử trong lần rà soát này; mọi kết quả kiểm thử ở mục 3 là số liệu Kiro báo cáo ở cuối phiên, kèm các báo cáo trong `docs/evidence/` (một phần thư mục này không đưa lên Git).
- Căn cứ bắt buộc, quan hệ đối chiếu và bộ câu hỏi do tác nhân soạn; **chưa được cán bộ chuyên môn xác nhận**.
- Các gói portable (A5, A22) chưa được thử trên máy Windows vật lý thứ hai; bản desktop Tauri và tệp TXT chưa được kiểm trong phiên `201bebb1`.
- Giai đoạn 30/10–04/11, phần công việc trên máy thứ hai, các thay đổi 08/11 17:21 → 09/11 17:19 và cập nhật 10–11/11 không được bản ghi Kiro còn lưu bao phủ đầy đủ; các mốc thiếu log dựa trên xác nhận của chủ dự án.
- Phiên Kiro ghi lại ở mục 2 là lần chạy cho workspace này trên một máy; số liệu thống kê không bao gồm máy còn lại.
- Spec, steering và hook ngày 09/11/2026 dựng từ code; `PostFileSave` đã được quan sát tự kích hoạt khi agent ghi tệp; lưu tay trong editor chưa thử.
- Một số tệp tài liệu phát sinh khác (báo cáo, tệp trong `.agents/`) nằm ngoài Git theo `.gitignore` và không được đưa vào thống kê tệp.
- Số lệnh công cụ của lượt hiện tại là ảnh chụp lúc lập thống kê ngày 09/11; không bao gồm các bổ sung 10–11/11.
- Chỉ số "tệp có `fs_write`" và số dòng đều là cận trên về quyền tác giả của Kiro; số tệp là cận dưới vì không đếm tệp tạo bằng lệnh shell (29 ứng viên chưa tính, xem phụ lục).
- Công việc trong 30/10–04/11, trên máy còn lại, khoảng 08/11 17:21 → 09/11 17:19 và các cập nhật 10–11/11 không được bản ghi phiên lưu lại bao phủ đầy đủ; các mốc không có log dựa trên xác nhận của chủ dự án và không được cộng vào số liệu thống kê cũ.

## Cập nhật sau giai đoạn build (11/11/2026)

Các bổ sung sau mốc build và chốt số liệu ban đầu ngày 09/11 được thực hiện trong Kiro IDE với Claude Sonnet 5.5. Số liệu phiên Kiro và thống kê đóng góp ở các mục phía trên không bao gồm đợt này; Kiroween vẫn tiếp diễn đến 04/12/2026 nên đây chưa phải bản tổng kết cuối kỳ.

- Hoàn thiện màn hình Hỏi đáp hai khung: lịch sử hỏi đáp trong phiên ở khung trái, căn cứ ở khung phải; phân trang căn cứ theo chiều cao khung và bấm `[n]` để nhảy tới căn cứ.
- Bổ sung quan hệ hiệu lực cấp Điều/Khoản/Điểm: đề xuất thay thế, sửa đổi, bổ sung, bãi bỏ; ngày hiệu lực theo từng mục, hỗ trợ tra cứu theo thời điểm và hiển thị ghi chú cảnh báo màu vàng khi hiệu lực cấp nút chưa được xác minh hoặc ngày tra cứu vượt ngày dữ liệu.
- Mã nguồn tại commit `861fa34`; gói Windows LAN Portable r4 gồm 105 văn bản và 7.447 vector.
- Kết quả kiểm thử ghi nhận hôm nay: backend **277 passed, 35 skipped** khi không đặt `EVIDENCE_TEST_DATABASE_URL`; frontend **95 passed**.
