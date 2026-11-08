# Rà soát độ chính xác, độ đầy đủ và thời gian truy xuất — 05/11/2026

Phạm vi: backend tìm kiếm văn bản (Search v1), truy xuất căn cứ cho chat, kiểm lại
căn cứ sau mỗi lượt, nhật ký kiểm toán; đọc lại phía frontend/desktop để tìm nguy cơ
treo. Mọi số đo dùng dữ liệu **HƯ CẤU** trên PostgreSQL 18.6 dev, cùng máy, schema
tạm (tạo rồi xóa). Không phải nghiệm thu nghiệp vụ hay số đo trên máy Windows đích.

## Lỗi xác nhận và cách sửa

| # | Lỗi (đã tái hiện) | Nguyên nhân | Sửa |
|---|---|---|---|
| 1 | Chat chọn sai văn bản khi hỏi theo số hiệu (`Điều 5 Nghị định 15/2020/NĐ-CP`, viết thường/không dấu, hoặc chỉ ghi số hiệu) | SQL so khớp `d.document_number = '15/2020/nđ-cp'` (chuỗi đã hạ chữ) nên không bao giờ khớp `15/2020/NĐ-CP`; số hiệu không tiền tố không được nhận | Dùng khóa số hiệu chuẩn hóa chung với Search v1 (`query_document_number_key`, `number_key_sql`) |
| 2 | Chat không tìm được câu hỏi không dấu (`xu phat vi pham`) | Chat chỉ dùng chỉ mục có dấu | Thêm kênh folded (GIN `text_folded`), xếp kết quả đúng dấu lên trước |
| 3 | Chữ hoa tiếng Việt không khớp (`ỦY BAN`, `QUYẾT ĐỊNH`, `ĐIỀU 2`) | DB dùng locale `C`: `lower()`/`to_tsvector` chỉ hạ chữ ASCII (`'Định'` ≠ `'định'`), `~*` không gộp `Đ/đ` | Hạ chữ Unicode trong SQL (`pg_c_utf8` khi có, `translate` khi không); mẫu `Điều N` dùng lớp ký tự `[ĐđÐ][Ii][Ềề][Uu]` |
| 4 | Chat có thể trích phiên bản văn bản đã bị thay thế | Chat không lọc phiên bản theo ngày hiệu lực như Search v1 | Chọn phiên bản approved mới nhất còn hiệu lực tại `as_of_date` có provenance verified (giống Search v1) |
| 5 | Một khoản có thể xuất hiện lặp nếu có nhiều khoảng hiệu lực trùng ngày | `LEFT JOIN` hiệu lực không giới hạn | `LATERAL … LIMIT 1` như Search v1 |
| 6 | Chat chậm 1,8–6,8 s/lượt trên 100.000 node; không giới hạn đồng thời, không `statement_timeout` → có thể chiếm hết pool 10 kết nối, làm chậm đăng nhập/tìm kiếm/mở PDF | Planner quét toàn bộ node và tính `to_tsvector` cho mọi dòng; kênh tiêu đề OR kéo cả văn bản vào ứng viên | Kênh ứng viên có giới hạn (1.500/kênh), kênh OR chỉ chạy khi kênh chính thiếu; tính điểm/kiểm span chỉ trên tập ứng viên; 4 lượt DB đồng thời; `statement_timeout`; hết hạn trả `QUERY_TIMEOUT` thay vì `QUERY_FAILED` |
| 7 | Search v1 với từ phổ biến: ~30 s thực thi (50 s thời gian chờ), luôn `SEARCH_TIMEOUT` | Join `selected_versions` bị quét lại cho từng node (99.000 lần) và cửa sổ `document_order` lặp theo từng khoản | Tính danh sách phiên bản ở câu lệnh riêng, truyền mảng; giới hạn một trang văn bản trước khi join khoản |
| 8 | Sau 5 lần chạy cùng câu lệnh trên một kết nối, tìm kiếm có thể chậm từ ~15 ms lên ~2,8 s (tái hiện trong lúc sửa; chưa đo đủ để khẳng định mã gốc bị ảnh hưởng) | asyncpg dùng prepared statement; PostgreSQL có thể chuyển sang generic plan bỏ qua giá trị tham số | `SET LOCAL plan_cache_mode = force_custom_plan` trong giao dịch tìm kiếm/chat |
| 9 | Mỗi lượt chat đọc toàn bộ từng PDF (≤ 32 MB/tệp) vào RAM để băm lại; hết hạn 5 s bị báo sai là `CITATION_INVALID` | Kiểm lại dùng `read_immutable_pdf` | Băm theo khối 1 MB, bỏ qua nếu kích thước/mtime/ctime không đổi từ lần khớp trước; mở PDF cho người dùng vẫn băm lại toàn bộ. Hết hạn trả `QUERY_TIMEOUT`. Kiểm ACL các căn cứ bằng 1 truy vấn thay vì 12 |
| 10 | Mở nhật ký kiểm toán chặn event loop khi băm lại tới 10.000 sự kiện | Băm trên luồng async | Chuyển sang `asyncio.to_thread` |

Không đổi quy tắc ACL, nội dung chứng cứ gốc hay migration. API chỉ thêm `totals.capped`
và `totals.count_cap` ở đợt 2 (OpenAPI đã cập nhật).
Đã thử thêm chỉ mục b-tree `document_nodes(document_version_id)` nhưng planner dùng nó
thay GIN và làm Search v1 chậm từ ~15 ms lên ~2,8 s, nên đã bỏ.

## Độ chính xác chat (8 ca HƯ CẤU, cùng dữ liệu)

| Ca | Trước | Sau |
|---|---|---|
| `Điều 5 Nghị định 15/2020/NĐ-CP quy định gì` → Điều 5 đúng văn bản | Đạt | Đạt |
| `điều 5 nghị định 15/2020/nd-cp` | Sai văn bản | Đạt |
| Chỉ số hiệu `15/2020/NĐ-CP` → mọi kết quả thuộc văn bản đó | Lẫn văn bản khác | Đạt |
| Không dấu `xu phat vi pham hanh chinh buu chinh` | Đạt | Đạt |
| `ủy ban nhân dân cấp tỉnh chịu trách nhiệm` (nội dung viết hoa) | Sai | Đạt |
| `quyết định về phân cấp` (tiêu đề viết hoa) | Sai | Đạt |
| `cấp phép viễn thông` (phân biệt `cấp`/`cáp`) | Đạt | Đạt |
| `lệ phí trước bạ nhà đất` → chỉ phiên bản còn hiệu lực | Lẫn phiên bản cũ | Đạt |

Tổng: **3/8 → 8/8**. Đây là ca kiểm lỗi do người rà soát dựng, không phải Gold nghiệp vụ.

## Thời gian (100.000 node HƯ CẤU, p50, ≥ 5 lần đo sau warm-up)

| Luồng | Trước | Sau |
|---|---:|---:|
| Chat `báo cáo định kỳ` (1.000 khoản khớp) | 1.874 ms | 151 ms |
| Chat `quản lý nhà nước` (99.000 khoản khớp) | 4.313 ms | 226–321 ms |
| Chat `Điều 1 Nghị định … quy định gì` | 6.773 ms | 342 ms |
| Chat `cải cách hành chính là gì` | 3.863 ms | 311 ms |
| Search v1 từ khóa hẹp (1.000 khoản) | 66 ms | 55–59 ms |
| Search v1 không có kết quả (sau ≥ 5 lần chạy) | — | 15 ms |
| Search v1 từ khóa có trong 99% node | ~30.000 ms thực thi (timeout) | 3.500–6.500 ms |

24 lượt chat đồng thời: tất cả hoàn tất, wall 1,8 s, khoảng trống event loop lớn nhất
36 ms, slot trở về 4/4, DB còn phản hồi. HTTP thật (uvicorn): 35 lượt chat liên tiếp
không lỗi, lâu nhất 26 ms, server còn sống.

## Kiểm chứng

- Backend: **193 passed** với PostgreSQL thật (không skip); `ruff`, `mypy`
  (`backend/pyproject.toml`), `export_openapi.py --check`, `validate_migrations.py` đạt.
- Cập nhật 1 test (`test_replay_rechecks_current_acl`) vì kiểm lại căn cứ nay gọi
  `get_authorized_citations` (theo lô).
- Frontend: 73 passed, lint/build đạt sau các thay đổi giao diện (mục “Đợt 2”).
- Rust: không đổi mã; 17 test đạt; build release lại để nhúng bản web mới.

## Giới hạn còn lại

- Search v1: câu rất rộng nay dừng ở giới hạn đếm 8.000 khoản (khoảng 1,1–1,3 s trên
  máy dev) và xếp hạng trong phần đã xét; muốn xếp hạng toàn kho mà vẫn nhanh cần P1-1.
- Chat: với câu quá rộng, mỗi kênh lấy tối đa 1.500 ứng viên rồi mới xếp hạng, nên thứ
  tự trong nhóm “khớp đủ từ” có thể không phải tốt nhất tuyệt đối. Số hiệu/Điều luôn
  được ưu tiên.
- DB dev vẫn 0 văn bản approved, 0 provenance verified; chưa có Gold nên không có số
  recall/precision nghiệp vụ.

## Phương án nâng cấp

Thứ tự theo giá trị/rủi ro. Mục cần owner quyết định được ghi rõ.

### P1 — thời gian tìm kiếm

1. **Lưu sẵn tsvector**: thêm cột generated `search_tsv`, `search_tsv_folded`
   (hạ chữ Unicode khi ingest) và GIN trên cột; SQL dùng cột thay vì gọi `to_tsvector`
   cho từng dòng. Ước tính (chưa đo) truy vấn 99% node từ ~4–6 s xuống ~1 s và sửa luôn
   lỗi chữ hoa ở kênh có dấu của Search v1. Cần migration + reindex, cập nhật ADR-005
   (hiện yêu cầu chỉ mục biểu thức).
2. **Cache thứ tự kết quả theo trang**: mỗi lần “trang sau/xem thêm khoản” đang tính lại
   toàn bộ tập ứng viên. Cache danh sách id văn bản theo (người dùng, câu, bộ lọc,
   revision chuẩn hóa/ACL) 60 s.
3. **Tổng số cho câu quá rộng** — *owner chọn phương án B với N = 8.000, đã triển khai
   05/11* (mục “Đợt 2”).
4. **Admission/rate limit dùng chung** (PostgreSQL/Redis) trước khi chạy nhiều worker.

### P2 — độ chính xác

5. **Cụm âm tiết**: tiếng Việt là từ nhiều âm tiết (`quản lý`, `nhà nước`); bộ phân tích
   `simple` tách từng âm tiết. Cộng điểm cho cặp âm tiết liền nhau (`quản <-> lý`) hoặc
   dùng tách từ tiếng Việt khi ingest.
6. **Từ điển viết tắt/đồng nghĩa pháp lý**: `UBND`↔`Ủy ban nhân dân`, `NĐ`↔`Nghị định`,
   `TT`, `QĐ`, `HĐND`… mở rộng truy vấn có kiểm soát, curator quản lý.
7. **Hybrid retrieval**: schema đã có `embedding_indices`/`node_embeddings` (pgvector).
   Thêm kênh embedding (model local qua Model Registry), hợp nhất RRF với lexical, rerank
   top-50. Chỉ bật khi có model và Gold chứng minh tốt hơn.
8. **Hiệu lực trong pipeline** — *owner chọn phương án C, đã triển khai 05/11*: chỉ dừng
   toàn bộ kết luận khi căn cứ xếp đầu, hoặc căn cứ khớp Điều + số hiệu được hỏi đích
   danh, bị bãi bỏ/tạm đình chỉ/chưa có hiệu lực. Trường hợp khác chỉ loại căn cứ đó khỏi
   kết luận và gợi ý, kết quả tối đa “có điều kiện”, kèm lưu ý nêu rõ căn cứ bị loại
   (mục “Lưu ý khi áp dụng thực tế”). Không đổi API.
9. **Đánh giá có Gold**: mở rộng `evaluate_search.py` cho truy xuất chat (recall@k, MRR,
   tỉ lệ đúng số hiệu/Điều) để chỉnh trọng số bằng số liệu thay vì cảm nhận.

### P3 — vận hành

10. Ghi thời gian từng bước (ACL, phiên bản, ứng viên, xếp hạng, kiểm span) và bật
    `pg_stat_statements`/slow query log.
11. `ANALYZE` sau mỗi đợt ingest/duyệt lớn để planner có thống kê đúng.
12. Ingest lưu `text_indexed` đã chuẩn hóa NFC + hạ chữ (kèm backfill) để mọi kênh khớp
    chữ hoa mà không cần hạ chữ lúc truy vấn.

## Chạy lại

```text
$env:EVIDENCE_TEST_DATABASE_URL = "<DSN disposable>"
python -m pytest backend/tests -q
python scripts/smoke_app_runtime.py --output <dir> --soak-turns 35
python scripts/benchmark_search.py --documents 1000 --nodes-per-document 100 --output <dir>
```

Bản gốc các tệp đã sửa nằm ở `.agents/backup-2026-11-05-original/` (không thuộc bản phát
hành; xóa khi không cần khôi phục).

## Đợt 2 (05/11/2026): giới hạn đếm, hiệu lực, AI, giao diện, tài liệu

### Quyết định owner đã triển khai

- **Giới hạn đếm N = 8.000** (`EVIDENCE_SEARCH_COUNT_CAP`): dưới ngưỡng đếm và xếp hạng
  chính xác; vượt ngưỡng trả `totals.capped`, giao diện ghi “hơn 8.000 khoản”, không ghi
  tổng số trang, số khoản mỗi văn bản ghi “ít nhất”. Cơ sở chọn N: thời gian đo theo N
  (1.000 ≈ 0,16 s; 2.000 ≈ 0,25 s; 5.000 ≈ 0,83 s; 10.000 ≈ 1,6 s; 20.000 ≈ 2,6 s) và tỷ
  lệ khoản chứa từ phổ biến trên 3 văn bản thật của DB dev (“quy định” 36%, “cơ quan” 23%,
  “trách nhiệm” 7%, “báo cáo” 3%). Audit ghi `capped` để chỉnh N theo dữ liệu thật.
- Sửa kèm: đếm “gần đúng” dùng một tsquery OR có chỉ mục thay vì duyệt từng từ trên mọi
  khoản (trước: hết thời gian chờ 5 s với câu không có kết quả trên 100.000 node; sau:
  khoảng 40 ms).
- **Hiệu lực phương án C**: xem ADR-006 §2.5; đã thử 4 tình huống (khoản thứ 12 bị bãi
  bỏ, khoản đầu bị bãi bỏ, Điều + số hiệu được hỏi bị tạm đình chỉ, Điều không kèm số hiệu).

### AI (API và Local)

| Vấn đề | Sửa |
|---|---|
| Model đã `ready` rồi ngừng chạy: mọi lượt chat chờ hết thời gian chờ (tới khoảng 30 s) | Hồ sơ không kết nối được, hết thời gian hoặc bị hủy do vượt ngân sách bị bỏ qua 60 s; kiểm tra kết nối thành công xóa ngay |
| Kết nối tới máy không phản hồi dùng cả thời gian chờ đọc | Giới hạn kết nối 5 s |
| Prompt 12 căn cứ × 2.000 ký tự, model chạy CPU khó kịp ngân sách | 8 căn cứ đầu (đúng số dùng làm kết luận) × 1.200 ký tự |

Kiểm: endpoint không kết nối được → lượt 1 thử 1 lần, lượt 2 không gửi request (0,1 ms),
sau “Kiểm tra kết nối” thành công lượt 3 gọi lại model. Kiểm tra cấu hình: chế độ chỉ đọc
từ môi trường; `LOCAL` chỉ cho loopback/`localhost` và LAN đã khai báo; `API` cần HTTPS,
domain được phép, người dùng và mọi danh mục nguồn cho phép; fallback chỉ cùng vùng dữ
liệu; mỗi lượt tối đa 2 lần gửi. Không tìm thấy lỗi khác trong luồng này.

Theo xác nhận của owner, đã xóa dữ liệu Model Registry cũ của DB dev (20 provider, 10 hồ
sơ, 12 định tuyến) trong một giao dịch có ghi audit; bản sao lưu JSON nằm trong thư mục
backup.

### Giao diện

Chụp Chrome headless với backend thật (dữ liệu HƯ CẤU) ở 1024/1366/1920 px:

| Vấn đề | Sửa |
|---|---|
| Thẻ dữ kiện (số hiệu, điều khoản) ở cột 1024 px vỡ thành chữ dọc từng ký tự | Thẻ toàn chiều rộng, xuống dòng hợp lý |
| Hiện mã kỹ thuật: “Trạng thái lượt tra cứu: conditional”, “source_verified=passed”, “Trạng thái claim: …”, “Kết nối: unknown”, “Vai trò: answer” | Nhãn tiếng Việt |
| Trước khi hỏi đã báo “Chưa tìm thấy tài liệu được phép truy cập” | “Chưa có căn cứ — nhập câu hỏi…”; thông báo cũ chỉ sau khi tra cứu |
| Tiêu đề cột bị cắt “…” | Rút gọn chữ, toàn văn trong tooltip |
| Một số lớp CSS không có quy tắc: hộp đổi mật khẩu trên thanh trên cùng, thông báo Admin, danh sách tài khoản (tên/username/trạng thái dính liền), lưới biểu mẫu | Bổ sung CSS theo token sẵn có |
| “Loại văn bản” khi nạp PDF là ô nhập tự do (`decree`) trong khi bộ lọc tìm kiếm dùng 4 mã | Danh sách chọn Nghị định/Thông tư/Quyết định/Văn bản khác |

Sau sửa: không tràn ngang, không lỗi console. PDF trong ảnh chụp báo lỗi hiển thị vì
fixture chỉ là tệp PDF tối thiểu để kiểm mã băm, không phải lỗi giao diện. Câu hỏi mẫu
(chat và Orb) đổi sang câu chung không phụ thuộc văn bản cụ thể
(`frontend/src/samplePrompts.ts`).

### Tài liệu và tệp đã dọn

- Viết lại `README.md`, `00_README.md`, `docs/implementation-status.md`,
  `docs/search-v1-runbook.md`, `backend/app/migrations/README.md`,
  `configs/ai-runtime.env.example`; thêm ADR-006; ghi chú cập nhật trong ADR-005 và SRS
  §26.8. README cũ ghi sẵn mật khẩu tài khoản, sai vai trò (`curator`/`reviewer` có
  `USER`), “bố cục 2 cột”, “định tuyến 6 giai đoạn” — đã bỏ.
- Xóa bản sao ở thư mục gốc của hồ sơ, SRS v1.2.1, ADR-000 và prompt (trùng byte với
  `docs/`); bản SRS v1.3 ở gốc là bản cũ thiếu §26 nên mâu thuẫn với `docs/SRS_v1.3.md`.
  Chuyển kế hoạch Search v1 vào `docs/`.
- Xóa tệp tạm/cache: `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `__pycache__`,
  `backend-lint-baseline.local`, `ui-server.local` (PID cũ), kế hoạch cũ của phiên trước
  `docs/superpowers/`, ba thư mục benchmark trung gian của đợt 01/11 không được báo cáo dẫn.
