# ADR-006 — Độ chính xác truy xuất, giới hạn tải và khả năng chịu lỗi của AI

- Ngày: 05/11/2026
- Trạng thái: Đã triển khai
- Thay thế một phần: ADR-005 (mục “Hạn chế đã biết” về cap 5.000, legacy chat không có
  timeout, tổng số luôn chính xác); ADR-004 (thời gian chờ model).
- Bằng chứng: `docs/evidence/2026-11-05-retrieval-accuracy-performance/REPORT.md`

## 1. Bối cảnh

Rà soát 05/11 tái hiện được: chat chọn sai văn bản khi hỏi theo số hiệu, không tìm được
câu không dấu và chữ hoa tiếng Việt, có thể trích phiên bản đã bị thay thế; truy xuất chat
mất 1,9–6,8 s trên 100.000 node và không có giới hạn đồng thời; Search v1 với từ phổ biến
chạy khoảng 30 s; model AI ngừng hoạt động làm mỗi lượt chat chờ hết thời gian chờ.

## 2. Quyết định

### 2.1. Truy xuất căn cứ cho chat (`PostgresAuthorizedNodeSearch`)

- Chọn phiên bản như Search v1: mỗi văn bản được phép lấy phiên bản `approved` mới nhất
  còn hiệu lực tại `as_of_date` và có provenance verified; lọc phạm vi danh mục/loại văn
  bản ngay ở bước này.
- Ứng viên lấy theo kênh, mỗi kênh tối đa 1.500 khoản: số hiệu (khóa chuẩn hóa như
  Search v1), Điều N, đủ từ khóa (chỉ mục có dấu và không dấu), tiêu đề. Kênh “một trong
  các từ” và kênh nhãn của bản ghi cũ chỉ chạy khi các kênh trên thiếu kết quả.
- Phần tốn kém (tsvector, điểm, kiểm span/trang, hiệu lực) chỉ chạy trên tập ứng viên.
- Thứ tự: khớp số hiệu + Điều, số hiệu, Điều, đủ từ, đủ từ đúng dấu, điểm `ts_rank_cd`.
- Từ khóa bỏ phần “Điều/khoản/điểm N” và số hiệu khi các phần này đã có kênh riêng.
- Tối đa 4 lượt truy xuất DB đồng thời mỗi process (chờ, không từ chối); dùng chung
  `EVIDENCE_SEARCH_STATEMENT_TIMEOUT_MS`; hết hạn trả SSE `turn_error` mã `QUERY_TIMEOUT`.

### 2.2. Chữ hoa tiếng Việt dưới locale `C`

`lower()`/`to_tsvector('simple')` của PostgreSQL chỉ hạ chữ ASCII khi DB dùng locale `C`.
Truy vấn hạ chữ bằng collation `pg_c_utf8` (PostgreSQL 17+, phát hiện lúc chạy), nếu
không có thì dùng `translate` bảng chữ hoa tiếng Việt. Mẫu “Điều N” dùng lớp ký tự
`[ĐđÐ][Ii][Ềề][Uu]`.

### 2.3. Kế hoạch truy vấn ổn định

- Danh sách phiên bản được phép tính ở câu lệnh riêng rồi truyền mảng vào truy vấn trang;
  join cũ bị planner ước lượng sai và quét lại cho từng node.
- Mọi giao dịch tìm kiếm/chat đặt `plan_cache_mode = force_custom_plan`: asyncpg dùng
  prepared statement, generic plan bỏ qua giá trị tham số và có thể quét toàn bảng.
- Không thêm b-tree `document_nodes(document_version_id)`: đã thử, planner dùng nó thay GIN
  và làm truy vấn không kết quả chậm từ khoảng 15 ms lên khoảng 2,8 s.

### 2.4. Giới hạn đếm trên trang tìm kiếm (owner chốt N = 8.000)

- `EVIDENCE_SEARCH_COUNT_CAP` (mặc định 8.000, cho phép 500–100.000) là số khoản tối đa
  được kiểm nguồn, chấm điểm và đếm cho một lượt tìm.
- Dưới ngưỡng: tổng số và thứ tự chính xác như trước. Vượt ngưỡng: `totals.capped = true`,
  `totals.clauses = N`, kết quả xếp hạng trong N khoản đầu tiên tìm được; giao diện ghi
  “hơn N khoản”, phân trang không ghi tổng số trang, số khoản mỗi văn bản ghi “ít nhất”.
- Khi đã vượt ngưỡng, không trả `PHRASE_NOT_FOUND` vì cụm từ chính xác có thể nằm trong
  phần chưa xét.
- Audit `search.query` ghi `capped` để chỉnh N theo dữ liệu thật (mục tiêu: khoảng 95% câu
  tìm kiếm thực tế được đếm đủ).
- Cơ sở chọn N: ngân sách thời gian (đo trên máy dev: 5.000 ≈ 0,8 s, 10.000 ≈ 1,6 s) và tỷ
  lệ câu bị cắt; cần đo lại trên máy Windows đích.

### 2.5. Căn cứ hết hiệu lực (owner chọn phương án C)

Căn cứ `repealed`/`suspended`/`not_yet_effective`:

- chặn toàn bộ kết luận khi đó là căn cứ xếp đầu, hoặc khớp Điều + số hiệu người dùng hỏi
  đích danh;
- trường hợp khác chỉ bị loại khỏi kết luận và gợi ý, vẫn hiện thẻ căn cứ kèm nhãn hiệu
  lực; kết quả tối đa “có điều kiện”; mục “Lưu ý khi áp dụng thực tế” nêu căn cứ bị loại.

### 2.6. AI chọn căn cứ (API và Local)

- Kết nối tới model tối đa 5 s (`connect`), phần đọc vẫn theo `EVIDENCE_AI_TIMEOUT_SECONDS`.
- Hồ sơ model không kết nối được, hết thời gian hoặc bị hủy do vượt ngân sách chọn căn cứ
  bị bỏ qua 60 s ở các lượt sau (lưu trong RAM của process). “Kiểm tra kết nối” thành
  công trong Admin Portal xóa trạng thái này ngay.
- Prompt chỉ gửi 8 căn cứ đầu (đúng số căn cứ được dùng làm kết luận), mỗi căn cứ tối đa
  1.200 ký tự, để model chạy CPU vẫn kịp ngân sách.

### 2.7. Kiểm lại căn cứ sau mỗi lượt

ACL/provenance của các căn cứ kiểm bằng một truy vấn mỗi `as_of_date`; PDF băm theo khối
1 MB và bỏ qua nếu kích thước/mtime/ctime không đổi từ lần khớp trước. Mở PDF cho người
dùng vẫn băm lại toàn bộ. Hết thời gian kiểm lại trả `QUERY_TIMEOUT`, không báo
`CITATION_INVALID`.

## 3. Hệ quả

- Không đổi migration, quy tắc ACL hay chứng cứ gốc. API thêm `totals.capped` và
  `totals.count_cap` (OpenAPI đã cập nhật).
- Câu rất rộng ở trang tìm kiếm: xếp hạng trong N khoản đầu tiên, không phải toàn kho.
- Chat với câu rất rộng: xếp hạng trong tối đa 1.500 ứng viên mỗi kênh.
- Giới hạn đồng thời và trạng thái tạm bỏ qua model là theo process; nhiều worker cần
  store chung.

## 4. Việc tiếp theo (đề xuất)

Lưu sẵn tsvector đã hạ chữ khi ingest (giảm chi phí chấm điểm, sửa chữ hoa ở kênh có dấu
của Search v1), cache thứ tự kết quả theo trang, cộng điểm cụm âm tiết liền nhau, từ điển
viết tắt pháp lý, kênh embedding khi có model và Gold. Chi tiết ở báo cáo 05/11.
