# Trạng thái triển khai

> **[Không triển khai – xem ADR-010]** Mọi nội dung về bộ câu hỏi Gold, trap set, calibration và held-out trong tài liệu này không được triển khai theo [ADR-010](architecture-decisions/ADR-010-khong-trien-khai-bo-cau-hoi-gold.md). Phần còn lại giữ nguyên.

Cập nhật 11/11/2026. Tài liệu này chỉ ghi trạng thái **hiện hành**; diễn biến từng đợt nằm
trong các báo cáo ở mục “Lịch sử”. Không coi ứng dụng là đã nghiệm thu: chưa có văn bản
nghiệp vụ được duyệt, chưa có Gold [Không triển khai – xem ADR-010]; model thật mới chỉ được thử trên DB tạm (G1–G5).

## Tinh chỉnh đề xuất và phạm vi node cho hiệu lực cấp Điều/Khoản/Điểm (11/11/2026)

- **Phân biệt `replace` và `modify`, bảo toàn `source_path`/`target_path`** (`backend/app/effectivity/extract.py`, `store.py`, `node_paths.py`):
  mẫu câu chủ động/bị động thay thế đơn vị cụ thể ("Điều X thay thế Điều Y", "Thay thế khoản 2 Điều 4 như sau",
  "Quy định tại Điều 5 thay thế quy định tại Điều 3", Phụ lục, Mẫu) tạo đề xuất `action="replace"`, `scope="node"`,
  giữ đủ cả `source_path` và `target_path`; chỉ hạ xuống `modify` khi câu là `thay thế (cụm )từ`. Hai đề xuất thay thế
  cùng một đích từ hai nguồn hoặc hai ngày khác nhau đều được giữ lại qua khóa phân biệt (`|src=...|from=...`).
- **Ngày hiệu lực riêng của từng mục**: mỗi mục sửa đổi/thay thế/bãi bỏ ưu tiên đọc `"từ ngày D"` trong chính lời dẫn
  của mục đó (bỏ qua phần trích dẫn trong ngoặc kép và phần sau `"như sau"`), không có mới dùng `effective_from` của cả
  văn bản; nếu một mục nêu nhiều ngày khác nhau thì để `valid_from=None` để người duyệt nhập.
- **Tách nhiều đích trong cùng câu**: câu dạng `"Điều 5 và Điều 6 thay thế Điều 3 và Điều 4"` hoặc `"khoản 1 và khoản 2 Điều 4"`
  được tách thành một đề xuất riêng cho từng đơn vị đích, giữ nguyên nhóm nguồn (`"Điều 5 và Điều 6"`).
- **Thay thế một phần không nêu Điều cụ thể**: câu `"Thay thế một phần / một số điều của Thông tư X"` (khi các khoản con
  chưa bao phủ qua `covered_by_items`) tạo bản nháp `replace` với `scope="node"` và `target_path=None` (độ tin cậy `0.7`,
  khóa `|partial`); hệ thống chặn phê duyệt (`RELATION_TARGET_REQUIRED`) cho đến khi người duyệt gắn `target_node_id`.
- **Phạm vi `node` cho `modify` và `repeal_partial`** (`extract.py`, `store.py`, `storage/chat_retrieval.py`, `storage/comprehensive.py`):
  khi câu nêu rõ Điều/Khoản/Điểm đích ("Sửa đổi khoản 2 Điều 4 của Thông tư X", "Bãi bỏ Điều 3 của Thông tư X"), quan hệ
  mang `scope="node"` và gắn vào nút đích. Sau khi duyệt, nút bị bãi bỏ nhận trạng thái `repealed` (`verified`, ẩn khỏi
  kết quả tìm kiếm mặc định qua `lookup_visibility.py`), nút bị sửa nhận `modified` (`unverified`); nhãn quan hệ và nhóm
  văn bản trong tìm kiếm toàn diện/chat vẫn tính các quan hệ cấp nút này.
- **Kiểm thử**: bộ kiểm thử backend đạt **312 passed** với PostgreSQL (`277 passed, 35 skipped` khi không đặt `EVIDENCE_TEST_DATABASE_URL`),
  bổ sung kiểm thử đơn vị trong `backend/tests/test_effectivity_rules.py` và kiểm thử tích hợp PostgreSQL trong
  `backend/tests/test_effectivity_node_scope_pg.py`.

## Quản lý văn bản (09/11/2026)

- Admin Portal có danh sách lọc và phân trang, chi tiết phiên bản, sửa metadata/OCR,
  xử lý lại, gửi duyệt và quản lý trạng thái tra cứu theo quyền. Xem
  [hướng dẫn quản lý văn bản](HUONG_DAN_SU_DUNG_VA_CAU_HINH_AI.md#quản-lý-văn-bản).
- Migration `0016` giữ dữ liệu cũ và thêm trạng thái tạm ngừng, phiên bản hiệu chỉnh,
  nhật ký OCR và bộ đếm vô hiệu hóa cache tra cứu. Kiểm thử với PostgreSQL 18.6 và
  pgvector 0.8.7 trên dữ liệu hư cấu, gồm nâng cấp giữ nguyên hash và vector cũ.
- `verify.ps1` đạt 12/12 bước, backend 295 kiểm thử và frontend 94 kiểm thử đạt.
  Chrome kiểm tra cổng Admin tại 360, 768 và 1280 px. Chưa đo chất lượng truy xuất
  trên bộ dữ liệu và model AI của máy nhà. OCR Tesseract trên tài liệu scan thật cũng
  chưa được kiểm chứng trong môi trường này.
- Quan hệ hiệu lực cấp nút bị ảnh hưởng bởi bản hiệu chỉnh được đưa lại vào hàng đợi
  duyệt. API hỗ trợ xác định nút đích, còn giao diện Hiệu lực chưa có bộ chọn nút đích.

## Diễn giải AI và PDF scan OCR (08/11/2026)

Báo cáo: [evidence/2026-11-08-ai-ocr/REPORT.md](evidence/2026-11-08-ai-ocr/REPORT.md).

- Diễn giải AI (`synthesis/focus.py`, `focused.py`, `checks.verify_claim`): tách vấn đề hỏi và nội
  dung; chỉ khoản đủ nội dung và đúng vấn đề được diễn giải; vấn đề “chặt” (phạt, thời hạn, thẩm
  quyền, điều kiện, hiệu lực…) không có khoản thì trả lời “chưa tìm thấy”, không gọi model. Mỗi ý
  qua các lớp kiểm từ ngữ (sự kiện, chủ đề, mức hỗ trợ, phủ định/ngoại lệ/điều kiện, hiệu lực,
  trùng); sai số/ngày/Điều là loại. Giao diện `AiAnswerView`: câu trả lời trước, căn cứ hỗ trợ sau.
- OCR (`documents/ocr.py`, migration `0015`): Tesseract qua cấu hình, chẩn đoán từng trang, tự xoay
  trang; reviewer xác nhận từng trang trước khi chữ OCR thành căn cứ; parser không tách dòng xuống
  hàng “Điều N của …” thành Điều mới. Đã thử 5 nghị định scan thật qua HTTP.
- `verify.ps1` 12/12: backend 257 passed, frontend 60 passed. 50 câu G5: R@toàn bộ 0,960 (không đổi).

## Tra cứu của USER sau rà soát 08/11/2026

Báo cáo: [evidence/2026-11-08-user-lookup/REPORT.md](evidence/2026-11-08-user-lookup/REPORT.md).

- Hỏi đáp chạy trên bộ kết quả G2 (câu có số hiệu/Điều giữ tra cứu tham chiếu); mức liên quan theo
  cụm từ (`storage/relevance.py`): `direct`, `related`, `weak`; danh mục liệt kê văn bản là “chỉ nhắc
  đến”. Câu trả lời có cấu trúc viết từ siêu dữ liệu (`workflow/chat_answer.py`), mỗi văn bản một thẻ,
  trích đoạn nguyên văn ≤ 520 ký tự, mở rộng được. Diễn giải AI là nút riêng (G4, `only_relevant`).
- Một trang “Tìm kiếm văn bản” trên G2 (bỏ trang “Tìm toàn diện”); `GET /api/v1/search` giữ cho tương thích.
- `GET /api/v1/citations/{id}/original`: tệp đã nạp (PDF, kể cả scan) hoặc tệp Word/TXT gốc, kiểm ACL và
  SHA-256. Giao diện mở PDF ở tab riêng tại trang, tải Word/TXT đúng định dạng; bỏ PDF nhúng.
- RRF, ngưỡng theo nghĩa 0,8, rerank tắt: không đổi. 50 câu G5: R@toàn bộ 0,960 (không đổi), MRR@10
  0,780 → 0,792, NDCG@10 0,589 → 0,629, R@10 0,865 → 0,851–0,865 (dao động của bước `expand`).
- `verify.ps1` 12/12: backend 239 passed, frontend 57 passed.

## Thành phần đã triển khai

| Hạng mục | Vị trí chính | Trạng thái |
|---|---|---|
| Xác thực, RBAC/ABAC, vòng đời tài khoản | `backend/app/auth_acl/`, `admin_services.py`, `api/v1/auth.py`, `admin.py` | scrypt, khóa sau 5 lần sai, buộc đổi mật khẩu, chặn tự xóa |
| Danh mục và ACL | `admin_services.py`, Admin Portal | CRUD, xóa mềm kèm thu hồi ACL, cờ `remote_processing_allowed` |
| Nạp PDF, chống trùng, duyệt nguồn | `documents/`, Admin Portal | Nạp theo lô tuần tự; trùng byte bị chặn (409), trùng nội dung được cảnh báo; tách `CURATOR`/`REVIEWER`; loại văn bản chọn từ 7 mã (thêm Luật, Chỉ thị, Thông tư liên tịch) |
| Nạp Word và TXT | `documents/convert.py`, migration `0008` | `.docx`, `.doc` (Word 97–2003, đọc bảng đoạn văn), `.txt` (UTF-8/UTF-16/cp1258) được vẽ thành PDF có lớp chữ, cùng đầu vào cho cùng PDF (chống trùng vẫn đúng). Tệp gốc lưu ở `sources/` kèm `source_format`, `source_file_sha256`. Không có OCR cho Word chỉ chứa ảnh; không hỗ trợ RTF/HTML đổi đuôi `.doc` |
| Nạp hàng loạt theo cây thư mục | `scripts/import_official_corpus.py`, `test-data/` | Mỗi thư mục là một danh mục; dry-run trước; chạy lại không nạp trùng. Xem `test-data/README.md` |
| Cấu hình API Gemini/OpenAI | `model_registry/runtime.py`, `adapters/openai_compatible.py`, Admin Portal | Endpoint `/v1`, `/v1beta/openai` (Gemini), `/openai/v1`, `/api/v1`; tham số `reasoning_effort`, `token_limit_field` (`max_completion_tokens` cho GPT-5.x); mẫu cấu hình nhanh trong biểu mẫu. Chưa gọi thử Gemini/OpenAI thật (không có khóa) |
| Tìm kiếm văn bản (Search v1) | `storage/search.py`, `search_paging.py`, trang Tìm kiếm | Cụm từ, từ khóa, không dấu, số hiệu; phân trang trong PostgreSQL; giới hạn đếm 8.000 khoản (ADR-006) |
| Truy xuất căn cứ cho chat | `storage/authorized_search.py` | Kênh ứng viên có giới hạn, chọn phiên bản theo hiệu lực, chữ hoa tiếng Việt, 4 lượt DB đồng thời, `statement_timeout` |
| Pipeline cố định | `workflow/fixed_pipeline.py` | Analyze → Retrieve → Validate → Explain; quy tắc hiệu lực phương án C (ADR-006) |
| AI chọn căn cứ (API/Local) | `model_registry/`, `workflow/ai_selection.py` | Registry/Router trong DB, chính sách egress, số lần gửi theo chính sách giai đoạn (mặc định 2, ADR-007), Hybrid Auto, trần chi phí, tạm bỏ qua model lỗi 60 s, kết nối tối đa 5 s |
| Bộ nhớ phiên và SSE | `memory/service.py`, `main.py`, `EvidenceChat.tsx` | Chỉ RAM, giới hạn dung lượng, dừng/thử lại/xóa từng mục |
| Trích dẫn và PDF gốc | `storage/citations.py`, `documents/provenance.py`, `PdfViewer.tsx` | Kiểm lại ACL, provenance, span và SHA-256 khi mở |
| Nhật ký kiểm toán chuỗi băm | `audit.py` | `pg_advisory_xact_lock`; kiểm chuỗi chạy ngoài event loop |
| Desktop Windows (Tauri 2) | `src-tauri/` | Orb nổi, kéo thả theo vùng làm việc đa màn hình/DPI, khay hệ thống |

Quyết định kiến trúc: `docs/architecture-decisions/ADR-000` … `ADR-009`. Vận hành tìm
kiếm và chat: `docs/search-v1-runbook.md`.

## Kiểm chứng gần nhất (06/11/2026)

- Sau khi thêm Word/TXT và cấu hình Gemini: `verify.ps1` đạt 12/12 (backend **193 passed** với
  PostgreSQL thật, frontend **73 passed**, `ruff`/`mypy` sạch, 8 cặp migration, OpenAPI cập nhật).
- Bộ chuyển đổi chạy trên 242 tệp `.doc`/`.docx` thật không lỗi (2 tệp `.doc` thực chất là HTML bị từ chối
  rõ ràng); văn bản trích từ `.doc` khớp bản Word tự xuất ở mức 99,9% (3 tệp đối chiếu); không phát hiện
  tệp mã hóa chữ cũ (TCVN3/VNI).
- HTTP thật (uvicorn, DB tạm): xem trước và tạo bản nháp từ `.docx`, `.doc`, `.txt`; từ chối đúng
  (`INVALID_PDF_MAGIC`, `UNSUPPORTED_FILE_TYPE`, `DOCUMENT_TEXT_EMPTY`, `TXT_ENCODING_UNSUPPORTED`); nạp lại
  cùng tệp bị chặn `DUPLICATE_PDF_HASH` giữa hai tiến trình khác nhau; duyệt TXT, tìm thấy qua tìm kiếm,
  mở PDF trích dẫn đúng.

## Kiểm chứng ngày 05/11/2026

- Backend: **193 passed** với PostgreSQL 18.6 thật (schema tạm), không skip; `ruff`,
  `mypy`, kiểm OpenAPI, cặp migration (7) đạt.
- Frontend: **73 passed** (14 file), `eslint` 0 cảnh báo, `vite build` đạt.
- HTTP thật qua uvicorn (schema tạm, dữ liệu HƯ CẤU): đăng nhập, tìm kiếm, SSE, 35 lượt
  chat liên tiếp, 20 health đồng thời, đăng xuất thu hồi token; không lỗi.
- Giao diện: chụp Chrome headless với backend thật — hỏi đáp ở 1024/1366/1920 px, tìm
  kiếm ở 1024/1366 px, các tab Admin Portal ở 1366 px; không tràn ngang, không lỗi console.
- Gói chạy sẵn (`scripts/package-portable.ps1`, 06/11/2026): thư mục tự chứa, sạch, chép sang
  máy khác chạy `start.cmd`; chi tiết và phạm vi kiểm chứng ở `deploy/windows/README.md`.
- Chế độ LAN (`start-local-stack.ps1 -Lan`, 06/11/2026): backend phục vụ bản web cùng
  origin, nghe `0.0.0.0`. Đã kiểm qua IP LAN của chính máy dev: trang hiển thị đủ (Chrome
  headless), tài nguyên băm tên được cache, đăng nhập/danh mục/tìm kiếm/đăng xuất đạt,
  đường dẫn thoát thư mục trả 404, PostgreSQL không truy cập được qua IP LAN. **Chưa kiểm
  từ máy khác** (tường lửa chưa mở vì cần quyền quản trị).
- Native Rust: 17 test đạt; build release lại 05/11 (nhúng bản web mới) tại
  `E:\Programs\EvidenceRAG\cache\cargo-target\release\vietnamese-evidence-desktop.exe`,
  mở được cửa sổ “Evidence RAG”. Chưa tạo/ký bộ cài NSIS.

Số đo kỹ thuật (HƯ CẤU, 100.000 node, máy dev): truy xuất chat 0,15–0,35 s; tìm kiếm từ
khóa hẹp khoảng 0,1 s; không kết quả 15–40 ms; từ có trong 99% khoản 1,1–1,3 s (đã chạm
giới hạn đếm). Đây không phải số trên máy Windows đích hay chất lượng nghiệp vụ.

## G0: cây Điều/Khoản/Điểm và neo nhiều trang (07/11/2026)

Thiết kế chốt: [thiet-ke-tra-cuu-hieu-luc.md](thiet-ke-tra-cuu-hieu-luc.md) (G0 → G5).

- Khoản vắt qua trang được neo vào nhiều đoạn nguồn, mỗi trang một đoạn, theo thứ tự đọc
  (`node_source_spans`, migration `0009`); lời trích vẫn khớp từng ký tự với PDF. Duyệt văn bản và
  mở trích dẫn kiểm mọi đoạn (`node_source_text_valid`); đường tìm kiếm kiểm đoạn đầu.
- Dòng lặp lại (ví dụ "Điều 5") được đặt theo thứ tự đọc khi nó nối liền khoản trước; nếu không
  nối liền thì chỉ nhận khi duy nhất trong trang.
- Ghi parent_id (Chương → Mục → Điều → Khoản → Điểm), page_end, path có cấu trúc và
  citation_label ("Điểm a khoản 2 Điều 5"); nhãn này hiện trên thẻ căn cứ, kết quả tìm kiếm, trích dẫn.
- Khoản dài hơn 4.000 ký tự được chia "(phần N)" để một lượt hỏi đáp không vượt giới hạn bộ nhớ phiên.
- Trang có lớp chữ gần như không dấu (OCR dở của máy quét) tạo tác vụ rà soát
  page_N_text_layer_suspect; không chặn duyệt.
- Giới hạn chữ mỗi văn bản thành cấu hình EVIDENCE_MAX_DOCUMENT_CHARACTERS (mặc định 2.000.000);
  tiến trình đọc PDF không gửi hộp ký tự về nữa (giảm bộ nhớ).
- scripts/rebuild_node_tree.py: dựng lại cây cho bản nháp và bản chờ duyệt (chạy thử, rồi --apply);
  dữ liệu cũ không lưu chữ trang được đọc lại từ PDF gốc. Không đụng bản đã duyệt.

Kiểm chứng: backend **193 passed** (PostgreSQL thật, gồm chạy xuống rồi lên lại cả 9 migration),
ruff/mypy sạch. Nạp và duyệt 293 văn bản thử vào DB tạm: **286 duyệt được** (trước G0: 14),
0 khoản không neo được trong 21.724 khoản, 2.553 khoản nhiều trang, khoản dài nhất 4.486 ký tự. 7 văn
bản không duyệt được vì có trang cần OCR (DOCUMENT_TEXT_NOT_READY), đúng quy tắc. HTTP thật: tìm
bằng cụm từ nằm ở trang thứ hai của khoản ra đúng "Khoản 1 Điều 1" (trang 4); mở trích dẫn trả đủ
lời trích hai trang và PDF; lượt hỏi đáp chạy bình thường. DB dev: 12 phiên bản cũ đọc lại từ PDF,
648 khoản không neo được còn 0 (sao lưu trước ở .agents/backup-2026-11-07-g0/).

Chưa làm trong G0 (theo thiết kế, thuộc G1 trở đi): hiệu lực, nhóm văn bản, tìm theo nghĩa, tổng hợp.

## G1.0: chính sách gọi model, Hybrid Auto, trần chi phí (07/11/2026)

Quyết định: [ADR-007](architecture-decisions/ADR-007-stage-policy-hybrid-auto.md) (thay "tối đa 2 lượt LLM").

- Migration `0010_ai_policy`: `stage_policies` (số lần gửi 1–10, token ra, thời gian chờ, đồng thời theo
  chế độ và giai đoạn), `stage_routes.escalation_profile_id`, giá và trần chi phí ngày/tháng trên hồ sơ,
  `ai_usage_events` (không lưu nội dung). Thiếu chính sách thì vẫn dùng `LLM_ATTEMPT_BUDGET` (mặc định 2).
- `LOCAL` = Local Only: tuyến LOCAL không nhận hồ sơ nâng cấp; runtime không đọc nó; hồ sơ `public` bị từ chối.
- `API` = Hybrid Auto: tuyến chính được là model local; hồ sơ nâng cấp (`public`) chỉ cho `answer`/`summarize`,
  gọi một lần khi local đã chạy mà không kết quả nào qua kiểm tra của ứng dụng, hoặc gọi trước khi người
  dùng bật "Phân tích sâu". Không có căn cứ thì không gọi model. Giữ đủ điều kiện egress của ADR-004.
- Đạt trần chi phí: không gọi hồ sơ đó, kết quả hạ về nguyên văn, phản hồi có `ai_limited`.
  Phản hồi có `external_ai_used`; giao diện hiện "Đã dùng API ngoài cho lượt này."
- Admin Portal: ô hồ sơ nâng cấp (chỉ chế độ API), giới hạn gọi model theo giai đoạn, giá và trần chi phí
  của hồ sơ, mức dùng ngày/tháng. API mới `POST /api/v1/admin/model-registry/policies`.

Kiểm chứng: `verify.ps1` đạt 12/12 (backend **206 passed** với PostgreSQL thật, gồm
`test_ai_policy.py` và kiểm tuyến nâng cấp/chính sách/trần chi phí trên DB; frontend **74 passed**,
`ruff`/`mypy`/`eslint` sạch, 10 cặp migration, OpenAPI cập nhật). HTTP thật (schema tạm, dữ liệu HƯ CẤU):
tìm kiếm, SSE, 5 lượt chat liên tiếp, 20 health đồng thời, đăng xuất thu hồi token, không lỗi
(`docs/evidence/2026-11-07-g1-0/http-smoke.json`). Chưa gọi model thật (không có khóa API, chưa có model local).

Sau G4, mọi giai đoạn của Registry đều được ứng dụng gọi (xem G1–G4 bên dưới).

## G1–G5: hiệu lực, tìm toàn diện, nhóm nội dung, tổng hợp, bao phủ (07/11/2026)

Quyết định: [ADR-008](architecture-decisions/ADR-008-effectivity-two-axes.md) (hiệu lực hai trục,
G1, G3), [ADR-009](architecture-decisions/ADR-009-comprehensive-search-synthesis.md) (G2, G4, G5).
Migration mới `0011_effectivity`, `0012_comprehensive_search`, `0013_content_groups` (đều có `.down.sql`).

**G1 — hiệu lực cấp văn bản** (`backend/app/effectivity/`, `api/v1/effectivity.py`, tab "Hiệu lực"
trong Admin Portal). Bảng `document_effective_intervals`, `effectivity_attestations`; cột
`verification_state`; `node_amendments`/`node_references` mở rộng; `category_acl.can_review` (ô
"Danh mục được xác nhận hiệu lực" khi sửa tài khoản REVIEWER). Ngày ban hành, ngày hiệu lực, cơ quan
đọc bằng quy tắc khi tạo bản nháp, hiện ở màn duyệt nguồn và được xác nhận cùng lúc duyệt (sửa được qua
`publication_date`, `effective_from`). Duyệt nguồn tự đọc quan hệ (thay thế, bãi bỏ toàn bộ/một phần,
sửa đổi, danh mục hết hiệu lực, phần đầu Văn bản hợp nhất), khớp số hiệu, khớp lại đích "chưa có trong
kho" và xuất bản snapshot. Hàng đợi duyệt theo lô nhóm theo văn bản nguồn; mỗi quan hệ một bản ghi
kiểm toán chung mã lô; người đề xuất không tự duyệt. Bản xác nhận "còn hiệu lực" chỉ khẳng định đến
ngày xác minh; quan hệ mới chạm đích chuyển nó sang "cần xác minh lại" (trigger). Tìm kiếm, thẻ căn cứ,
hỏi đáp có trường `effectivity` (hai trục, ghi chú, người/thời điểm xác minh, ngày dữ liệu); tìm kiếm có
`clause_level_warning`, `data_date`. Hỏi đáp không bị chặn khi chưa xác minh, có ghi chú (D12).
Script: `scripts/extract_effectivity.py` (chạy lại không thêm trùng). Giai đoạn AI `relation`
(`POST /api/v1/admin/effectivity/ai-proposals`) chỉ đề xuất cho câu quy tắc không đọc được; số hiệu
phải có nguyên văn trong câu.

**G2 — tìm toàn diện** (`storage/comprehensive.py`, `storage/embeddings.py`, trang "Tìm toàn diện").
`POST /api/v1/search/comprehensive` + `GET …/{result_set_id}`: bốn kênh (chính xác, theo nghĩa, khái
niệm, quan hệ) hợp RRF, bộ kết quả cố định trong RAM, phân trang đọc lại quyền, rerank theo lô bằng
LLM local, phạm vi tìm trung thực, ba nhóm D9, lọc trạng thái/xác minh trên toàn tập, nhóm văn bản.
Từ điển khái niệm `concept_terms` (đề xuất → người khác duyệt). Vector không cố định 768 chiều; chỉ mục
HNSW theo chiều model; `scripts/build_embeddings.py` (tiếp tục được, `--rebuild` khi đổi model). Cấu hình:
`EVIDENCE_SEMANTIC_TOP_N` (200), `EVIDENCE_SEMANTIC_RELATIVE_THRESHOLD` (0,8), `EVIDENCE_RERANK_TOP_N`
(40), `EVIDENCE_RERANK_BATCH_SIZE` (10), `EVIDENCE_RESULT_SET_TTL_SECONDS` (1800),
`EVIDENCE_CONCEPT_MIN_TERMS` (1). Rerank không bao giờ gửi tới hồ sơ `public`; embedding chỉ gửi khi bật
chính sách riêng (xem "Quản lý embedding" bên dưới).

**Quản lý embedding trong Admin Portal (07/11/2026)** (`storage/embedding_jobs.py`, `storage/embeddings.py`,
`components/EmbeddingManager.tsx`, migration `0014_embedding_jobs` có `.down.sql`; báo cáo
[evidence/2026-11-07-embedding-admin/REPORT.md](evidence/2026-11-07-embedding-admin/REPORT.md)).
Hồ sơ model có vai trò "embedding" riêng (tùy chọn số chiều yêu cầu). Mục "Embedding": kiểm tra model (kết nối,
model có trên dịch vụ, vector thử, số chiều, lưu trữ `vector` ≤ 2000 / `halfvec` ≤ 4000, chính sách dữ liệu), đếm
nút cần tạo, xác nhận rồi xếp hàng tác vụ nền trong tiến trình API (`EVIDENCE_EMBEDDING_WORKER`, mặc định bật):
tiến độ, tốc độ, thời gian còn lại, lỗi; tạm dừng/tiếp tục/thử lại/hủy; thử lại có giãn cách và giảm lô; tác vụ
mất tiến trình được chạy tiếp sau ~60 giây. Tìm theo nghĩa luôn dùng hồ sơ của chỉ mục đang hoạt động; chỉ mục
mới dựng HNSW `CONCURRENTLY`, kiểm tra (đủ nút, đúng chiều, HNSW hợp lệ, tạo lại một vector mẫu) rồi chuyển trong
một transaction; lỗi thì giữ chỉ mục cũ. Trạng thái chỉ mục: đang sử dụng, đang tạo, tạm dừng, lỗi, hoàn thành,
đã thay thế; không tự xóa vector/chỉ mục; đổi về model cũ dùng lại vector đã có. Embedding qua API ngoài chỉ khi
chế độ API, `EVIDENCE_REMOTE_PROCESSING_ALLOWED` và `EVIDENCE_REMOTE_EMBEDDING_ALLOWED` cùng bật, mọi văn bản
được phép xử lý ngoài và (khi tìm) người dùng được phép AI ngoài. `scripts/build_embeddings.py` dùng chung các bước.

**G3 — cấp Điều/Khoản/Điểm.** Đọc "Sửa đổi/Bổ sung/Bãi bỏ/Thay thế cụm từ … khoản X Điều Y như sau",
ghép đích theo cây G0 (parent_id); ngày hiệu lực riêng cấp Điều ("Điều 2 của Thông tư này có hiệu lực
từ …"); ngoại lệ cấp nút ghi cho cả cây con; mức rà soát cấp điều khoản tính tự động; cảnh báo chung
và ghi chú "chưa xác định khoản này có bị ảnh hưởng" tự gỡ khi đủ.

**G4 — nhóm nội dung, tổng hợp** (`backend/app/synthesis/`, `api/v1/synthesis.py`, khung "Tổng hợp
theo nhóm" dưới kết quả tìm toàn diện, khung rà soát nhãn trong tab "Hiệu lực"). 11 nhóm ban đầu và 27
quy tắc cụm từ trong CSDL; nhãn AI gán lười khi tổng hợp, duyệt theo lô. Tổng hợp theo nhóm/đợt trong
trần của quản trị viên (`/api/v1/admin/synthesis-settings`), báo "Đã tổng hợp N trong M căn cứ, K nhóm
còn lại", nút "Tổng hợp tiếp", "Mở rộng phạm vi", "Phân tích sâu". Ba lớp Nguyên văn / Diễn giải / Gợi ý;
mọi ý AI qua kiểm tra bằng mã (mã căn cứ, số, ngày, số hiệu, Điều/Khoản, từ kết luận nghiệp vụ).

**G5 — chất lượng** (`evaluation/coverage/`): 8 chủ đề, 24 cách hỏi, 42 lượt căn cứ bắt buộc; đo theo
kênh; đo quan hệ G3; công cụ đổi model và tính lại vector. Rerank chuyên dụng: bổ sung 07/11/2026 ở mức
**thử nghiệm, tắt theo mặc định** (xem mục dưới).

**G5 bổ sung — thử Qwen3-Reranker-0.6B trên CPU** (`docs/evidence/2026-11-07-g5-rerank/REPORT.md`, 100 tệp
thử, cùng 24 câu hỏi và 42 căn cứ bắt buộc, chưa được cán bộ xác nhận). Cấu hình: `EVIDENCE_RERANK_BACKEND`
(`llm` mặc định, hoặc `cross_encoder`), `EVIDENCE_CROSS_ENCODER_URL` (chỉ loopback),
`EVIDENCE_CROSS_ENCODER_TIMEOUT_SECONDS` (120), `EVIDENCE_CROSS_ENCODER_INSTRUCTION`. Dịch vụ:
`scripts/local_reranker_server.py` (venv riêng, không thêm gói vào venv ứng dụng). Kết quả: RRF thuần
Recall@10 0,762, MRR@10 0,674, NDCG@10 0,554, 2,5 giây; rerank LLM hiện tại 0,691 / 0,729 / 0,549, 47,7 giây,
Ollama 11,2 GB; Qwen3-Reranker 0,810 / 0,713 / 0,536, 32,3 giây, dịch vụ rerank đỉnh 4,8 GB. Mọi chênh
lệch MRR/NDCG so với RRF có khoảng tin cậy 95% chứa 0. Chưa đổi mặc định. Hai căn cứ chưa tìm thấy
(58/2026 Điều 11, 96/2026 Điều 3) là lỗi truy xuất ứng viên do ngưỡng kênh theo nghĩa 0,8; hạ xuống 0,6
đưa 42/42 căn cứ vào nhóm ứng viên nhưng chúng đứng ngoài top 40, và cả hai reranker đều không đưa vào top 10.
Giao diện không gửi `rerank`; trước đây API mặc định `true`.

**G5 bổ sung 2 — RRF thuần mặc định, 50 câu, dữ liệu 100 tệp lưu lâu dài** (`docs/evidence/2026-11-07-g5-rerank/REPORT-50-cau.md`,
`DATA-INVENTORY.md`). `rerank` của "Tìm toàn diện" nhận `true`/`false`/vắng; vắng dùng `EVIDENCE_RERANK_DEFAULT` (mặc định `false`):
mặc định thực tế là RRF thuần, rerank LLM (`EVIDENCE_RERANK_BACKEND=llm`) và Qwen3-Reranker (`cross_encoder`) giữ làm tùy chọn, đã kiểm cả hai
còn chạy khi `rerank:true`. Ngưỡng theo nghĩa giữ 0,8 (`EVIDENCE_SEMANTIC_RELATIVE_THRESHOLD`, 0,6 chỉ để thử). Bộ kiểm thử 17 chủ đề, 50 câu,
74 cặp (26 câu mới soạn từ văn bản, chưa xác nhận nghiệp vụ). RRF thuần trên 50 câu: Recall@10/20/50/toàn bộ 0,865/0,892/0,932/0,960,
MRR@10 0,790, NDCG@10 0,594, trung vị 2,2 giây. DB `evidence_rerank_eval` (100 văn bản, 7.230 vector) dựng lại một lần (embedding 42 phút),
sao lưu ngay bằng `pg_dump -Fc` (37 MB) và khôi phục thử thành công (`scripts/verify_db_restore.py`: số dòng, tổng kiểm văn bản và vector, 98 chỉ mục,
HNSW đều khớp). Không xóa DB, kho tài liệu, model hay bản sao lưu. Hồi quy `verify.ps1` 12/12 (backend 218, frontend 74).

**G5 bổ sung 3 — khóa phá hòa ổn định** (`docs/evidence/2026-11-07-g5-rerank/REPORT-tiebreak.md`). Khi hai khoản bằng điểm, thay UUID bằng khóa
(số hiệu văn bản, SHA-256 tệp, vị trí khoản theo tiền tố `path`) ở `_rrf`, kênh chính xác (`candidates_sql`) và kênh quan hệ; công thức RRF, kênh,
ngưỡng, embedding không đổi. Hai CSDL nhập độc lập từ cùng 100 tệp: thứ tự giống hệt 50/50 câu (trước 45/50 cho kênh chính xác, 41/50 khi thêm quan hệ).
Recall@10/20/toàn bộ của 50 câu không đổi (0,865/0,892/0,960). Hồi quy `verify.ps1` 12/12 (backend 225, frontend 77, gồm thay đổi khác trong cây mã).
Chưa kiểm qua hai lần nhập: kênh theo nghĩa (HNSW xấp xỉ) và kênh khái niệm (bước `expand` của LLM).

### Kiểm chứng (DB tạm `evidence_scratch`, 293 tệp thử, 286 văn bản duyệt được, 20.749 khoản)

- Đọc quy tắc lần đầu: 671 đề xuất quan hệ cấp văn bản, 293 quan hệ liên quan, 1.557 câu ứng viên AI,
  8,6 giây; lần sau thêm 85 quan hệ cấp nút. Chuỗi thật (HTTP, `docs/evidence/2026-11-07-g1/http-g1.json`,
  27/27 đạt): 66/2023 sửa 55/2021 và 56/2021 từ 01/01/2024; 43/VBHN-BCA nhận ra là hợp nhất của 55, 66,
  56, 53/2025; 110/2021 bãi bỏ 29/2016 từ 15/11/2021 (14/11/2021: "Chưa xác định"; 15/11/2021: "Hết hiệu
  lực, Đã xác minh"); 58/2026 thay 32/2017, 36/2017 và 96/2026 thay 17/2020 từ 01/07/2026 (đích chưa có
  trong kho → "chưa có trong kho", chờ khớp lại); 28/2024: Điều 2 từ 01/08/2024. Không có khoảng nào
  "Còn hiệu lực + Đã xác minh" khi thiếu bản xác nhận (đếm 0 cả cấp văn bản và cấp nút); bản xác nhận
  tự chuyển "cần xác minh lại"; tài khoản không có `can_review` thấy 0 đề xuất; lô 6 quan hệ = 6 bản ghi
  kiểm toán.
- G2 (`docs/evidence/2026-11-07-g2/http-g2.json`, 17/17 đạt): 4 kênh có kết quả (ví dụ 7 / 62 / 213 / 53),
  phân trang 326 mục không trùng không sót, thứ tự giữ nguyên, người khác mở bộ kết quả bị 403, 55 khoản
  chỉ nhờ kênh theo nghĩa, 51 khoản chỉ nhờ kênh quan hệ, tắt từng kênh đo được phần đóng góp, nhóm "Hết
  hiệu lực" đếm 92 và thu gọn, "Đối chiếu lịch sử" gộp một danh sách 732 mục, rerank 40/326.
- G3: 31/31 quan hệ cấp Điều/Khoản đối chiếu (66/2023, 28/2024) đọc đúng, ghép đúng nút (precision 1,0,
  recall 1,0 — `docs/evidence/2026-11-07-g5/g3-relations.json`); HTTP 11/11 đạt: Điều 12 (55/2021) "Hết
  hiệu lực" cấp nút từ 2024; Điều 2 (28/2024) "Chưa có hiệu lực" ngày 15/07/2024, kế thừa văn bản sau
  01/08/2024; mức rà soát cấp điều khoản của 55/2021 tự tính = đã đủ, ghi chú sửa đổi một phần biến mất.
- G4 (`docs/evidence/2026-11-07-g4/`): Local Only 10/10 đạt (kể cả bật "Phân tích sâu": 0 lượt gọi API);
  Hybrid Auto với DeepSeek-V4.1-Flash qua `api.river.ai` 11/11 đạt (3 lượt gọi, 4.103 token vào, 2.838
  token ra, ước tính 0,0046 theo giá đã nhập; 12/12 ý qua kiểm tra bằng mã); không có căn cứ → 0 lượt gọi
  model; "N trong M" đúng; "Tổng hợp tiếp" xử lý đợt sau.
- G5 (`docs/evidence/2026-11-07-g5/coverage.json`): đủ kênh tìm thấy 40/42 căn cứ bắt buộc (0,952); chỉ
  kênh chính xác 0,548; chỉ theo nghĩa 0,786; chỉ khái niệm 0,810; kênh quan hệ không chạy riêng được (cần
  văn bản khớp từ kênh khác làm gốc) nên đo riêng = 0. 7/8 chủ đề đủ ở mọi cách hỏi; thiếu: 58/2026 Điều 11
  và 96/2026 Điều 3 với hai cách hỏi chủ đề nội quy giam giữ.
- Model local: Ollama chạy độc lập (`E:\Programs\EvidenceRAG\tools\ollama`, model ở
  `E:\Programs\EvidenceRAG\models\ollama`), `qwen3-embedding:0.6b` (1.024 chiều, ~2,7 khoản/giây trên CPU,
  20.749 khoản ≈ 2 giờ), `qwen3:1.7b` cho rerank/expand/label/relation/summarize; mọi giá trị chỉ nằm
  trong Registry. Khóa API chỉ đặt vào biến môi trường của tiến trình khi chạy thử.
- `verify.ps1 -ProgramsRoot E:\Programs` đạt 12/12 (`docs/evidence/2026-11-07-g5/verify/`): backend
  **218 passed** với PostgreSQL thật (gồm `test_effectivity_rules.py` cho 5 quy tắc cứng,
  `test_synthesis_checks.py`, chạy xuống rồi lên lại cả 13 migration), frontend **74 passed**,
  ruff/mypy/eslint sạch, 13 cặp migration, OpenAPI cập nhật.

### Chưa kiểm chứng / giới hạn

- Danh sách căn cứ bắt buộc, 31 quan hệ đối chiếu G3 và tên 11 nhóm nội dung do tác tử lập từ văn bản,
  **chưa được cán bộ nghiệp vụ xác nhận**; dữ liệu thử được duyệt hàng loạt.
- Tô sáng tọa độ hộp ký tự (PDF bbox highlight) trên trình xem PDF và cổng WP 0.3/1.5: **[Không triển khai]** (trình xem mở đúng trang PDF kèm trích đoạn nguyên văn `quote_exact`, xem [pdf-anchor-coordinate-contract.md](pdf-anchor-coordinate-contract.md)).
- `qwen3:1.7b` trên CPU trả lời chậm (tóm tắt có lượt quá 30 s, bị tính "unreachable" và tạm bỏ qua 60 s);
  chất lượng diễn giải local thấp hơn API. Chưa đo trên máy Windows đích, chưa có GPU.
- Bộ kết quả cố định và trạng thái tổng hợp chỉ ở RAM một tiến trình; nhiều worker cần store chung.
- Giao diện mới (Tìm toàn diện, Tổng hợp, tab Hiệu lực, nhãn) chỉ kiểm bằng lint/kiểu/test hiện có và
  build; chưa chụp màn hình, chưa có test giao diện riêng cho các phần này.
- Danh mục hết hiệu lực (dạng bảng) cho đề xuất độ tin cậy 0,5 không kèm ngày; người duyệt phải điền ngày.
- DB dev chưa được áp migration 0011–0013 (ứng dụng tự áp khi khởi động; đã sao lưu ở
  `.agents/backup-2026-11-08-g1-g5/dev-db-public.dump`).

## Dữ liệu dev hiện có

- 12 phiên bản tài liệu: 9 nháp, 3 chờ duyệt, **0 đã duyệt**, 0 provenance verified,
  797 node, tất cả đã neo được nguồn (dựng lại cây 07/11). Vì vậy tìm kiếm và chat trên DB dev
  trả `NO_AUTHORIZED_DOCUMENTS` — đúng thiết kế. 9 bản nháp cũ không có node (PDF chỉ gồm trang
  cần OCR).
- Model Registry dev **trống** (0 provider, 0 hồ sơ, 0 định tuyến). Theo chỉ đạo owner
  05/11 đã xóa 20 provider, 10 hồ sơ và 12 định tuyến cũ (adapter/giai đoạn không còn hỗ
  trợ, tên model không có thật); có sự kiện audit
  `maintenance.delete_legacy_model_registry`, bản sao lưu ở
  `.agents/backup-2026-11-05-original/dev-db-model-registry.json`. Cấu hình model mới qua
  Admin Portal → Mô hình AI & Kiểm toán.

## Cổng phụ thuộc bên ngoài

1. **Gold [Không triển khai – xem ADR-010] 150–200 ca và văn bản được duyệt** do người nắm nghiệp vụ duyệt — chưa có;
   chưa có số recall/precision.
2. **Model thật**: đã thử trên DB tạm với Ollama local (`qwen3-embedding:0.6b`, `qwen3:1.7b`) và
   DeepSeek-V4.1-Flash qua `api.river.ai` (khóa thử của chủ sở hữu); DB dev vẫn chưa cấu hình model.
   Hỏi đáp vẫn trích dẫn nguyên văn (`answer_generated: false`).
3. **Máy Windows đích**: đo lại hiệu năng và giới hạn đếm; ký số bộ cài MSI/NSIS.
4. Rate limit, giới hạn đồng thời và trạng thái tạm bỏ qua model đang theo **một process**;
   chạy nhiều worker cần store chung.

## Cấu hình AI trên Admin Portal (08/11/2026)

Mục "Mô hình AI & Kiểm toán" gồm: **1. Mô hình AI** (form AI Local và form AI API riêng),
**2. Phân công AI** (gán model cho từng chức năng), **Embedding**, **3. Nhật ký**.
Tham số có giá trị mặc định hoặc suy ra từ hệ thống nằm trong "Nâng cao".
- Trước khi lưu/áp dụng có kiểm tra: cấu hình → khóa → kết nối → model có tồn tại → gọi thử
  (JSON hoặc embedding). Endpoint mới: `POST /api/v1/admin/model-registry/test` (nháp, không lưu)
  và `POST /api/v1/admin/model-registry/{profile_id}/test` (hồ sơ đã lưu, ghi tình trạng `ready`).
- Khóa API nhập trên form được mã hóa bằng DPAPI (`secret:<tên>`, `EVIDENCE_SECRET_STORE_DIR`),
  không hiển thị lại. `env:NAME` vẫn dùng được. `/probe` cũ giữ nguyên nhưng giao diện không dùng.
- Một hồ sơ có thể phục vụ nhiều chức năng sinh văn bản; `embedding` luôn đứng riêng.
  Hồ sơ cũ (một chức năng) và route đã lưu không đổi.

## Việc đề xuất tiếp theo

Lưu sẵn tsvector đã hạ chữ khi ingest; cache thứ tự kết quả theo trang; cộng điểm cụm âm
tiết liền nhau; từ điển viết tắt pháp lý; kênh embedding khi có model và Gold [Không triển khai – xem ADR-010]. Chi tiết:
[báo cáo 05/11](evidence/2026-11-05-retrieval-accuracy-performance/REPORT.md).

## Lịch sử

| Ngày | Báo cáo |
|---|---|
| 08/11/2026 | [Thiết kế lại giao diện Model Registry](evidence/2026-11-08-model-registry-ui/REPORT.md) |
| 08/11/2026 | [Diễn giải AI và OCR PDF scan](evidence/2026-11-08-ai-ocr/) |
| 05/11/2026 | [Độ chính xác, thời gian truy xuất, AI, giao diện](evidence/2026-11-05-retrieval-accuracy-performance/REPORT.md) |
| 01/11/2026 | [Rà soát độ đúng, độ đầy đủ và độ ổn định](evidence/2026-11-01-app-audit/REPORT.md) |
| 31/10/2026 | [Triển khai Search v1](evidence/2026-10-31-search-v1/REPORT.md), [rà soát Search](evidence/2026-10-31-search-review/REPORT.md) |
| 27/10/2026 | [Rà soát phiên nhớ/SSE/model](evidence/2026-10-27-audit/REPORT.md), [chống trùng nội dung](evidence/2026-10-27-content-dedup/REPORT.md) |
| 22/10/2026 | [Tiếp quản](evidence/2026-10-22-takeover/REPORT.md), [desktop native](evidence/2026-10-22-desktop-native/REPORT.md) |

Số liệu trong các báo cáo cũ phản ánh thời điểm đó; khi khác với tài liệu này, tài liệu
này là bản hiện hành.
