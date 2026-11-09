# Runbook — Tìm kiếm văn bản và truy xuất căn cứ cho chat

Cập nhật 05/11/2026. Áp dụng cho `GET /api/v1/search`, `GET /api/v1/search/approximate`,
trang “Tìm kiếm văn bản” và bước truy xuất căn cứ của chat. Quyết định kiến trúc:
`docs/architecture-decisions/ADR-005-search-v1.md` và
`docs/architecture-decisions/ADR-006-retrieval-accuracy-bounds-and-ai-resilience.md`.

## 1. Điều kiện tiên quyết

- PostgreSQL chạy, migration tự áp dụng khi backend khởi động (`apply_migrations`). Kiểm:

```sql
SELECT name FROM schema_migrations ORDER BY name;      -- 0001 … 0007
SELECT indexname FROM pg_indexes WHERE tablename = 'document_nodes';
-- phải có document_nodes_search_word_gin, document_nodes_search_folded_gin
```

- Phải có văn bản đã duyệt: `document_versions.review_status='approved'`,
  `document_nodes.review_status='approved'`, `source_provenance.verified_at IS NOT NULL`,
  và người dùng có quyền danh mục/văn bản. Thiếu thì trả `NO_AUTHORIZED_DOCUMENTS` — đúng
  thiết kế, không phải lỗi.
- Mỗi văn bản chỉ dùng **một phiên bản**: bản `approved` có `version_number` lớn nhất còn
  hiệu lực tại `as_of_date` (`valid_from`/`valid_to` rỗng nghĩa là không giới hạn) và có
  provenance verified. Áp dụng cho cả tìm kiếm và chat.

## 2. Cấu hình

| Biến môi trường | Mặc định | Phạm vi | Ý nghĩa |
|---|---|---|---|
| `EVIDENCE_SEARCH_STATEMENT_TIMEOUT_MS` | `5000` | 100–60000 | Ngân sách DB của một lượt tìm kiếm và của truy xuất chat |
| `EVIDENCE_SEARCH_COUNT_CAP` | `8000` | 500–100000 | Số khoản tối đa được kiểm nguồn, chấm điểm, đếm (owner chốt 05/11) |
| `EVIDENCE_SEARCH_RATE_PER_MINUTE` | `30` | 1–600 | Lượt tìm kiếm/phút/người dùng, theo process |
| `EVIDENCE_SEARCH_MAX_PAGE_DEPTH` | `1000` | 50–10000 | `page × page_size` tối đa |
| `EVIDENCE_QUERY_TIMEOUT_SECONDS` | `45` | ≤ 300 | Ngân sách cả lượt chat (AI chọn căn cứ dùng 70%) |
| `DATABASE_URL` | — | — | Bắt buộc; in-memory chỉ cho test |

Giới hạn cố định trong mã:

- Câu tìm ≤ 500 ký tự, ≤ 20 từ, cụm từ ≤ 200 ký tự; `page_size` và `clause_page_size` ≤ 50
  (mặc định 20 và 5).
- Tối đa 4 lượt tìm kiếm DB đồng thời mỗi process; quá 100 ms chờ trả `SEARCH_BUSY` (429).
- `approximate_matches_hidden` đếm tối đa 500 và chỉ tính khi tìm từ khóa có ≤ 200 khoản.
- Chat: 12 căn cứ mỗi lượt; tối đa 1.500 ứng viên mỗi kênh; 4 lượt truy xuất DB đồng thời
  mỗi process (lượt sau chờ, không bị từ chối).
- Audit `search.query` có hạn 250 ms; hết hạn chỉ ghi cảnh báo, vẫn trả kết quả.
- Mọi giao dịch tìm kiếm/chat đặt `plan_cache_mode = force_custom_plan`.

## 3. Hành vi cần biết

### 3.1. Trang tìm kiếm

- Có ngoặc kép → tìm cụm từ: `exact_phrase` (đúng dấu), `phrase_folded` (không dấu); không
  có cụm từ thì chuyển sang đủ từ và trả `PHRASE_NOT_FOUND`. Không ngoặc kép → đủ từ, có
  dấu hoặc không dấu. Số hiệu (`15/2020/NĐ-CP`, `ND`, chữ thường) đưa văn bản lên đầu.
- Dưới `EVIDENCE_SEARCH_COUNT_CAP`: `totals` và thứ tự chính xác. Vượt ngưỡng:
  `totals.capped=true`, `totals.clauses=N`; xếp hạng trong N khoản đầu tiên; giao diện ghi
  “hơn N khoản”, phân trang chỉ ghi số trang hiện tại, số khoản mỗi văn bản ghi “ít nhất”.
  Khi đã vượt ngưỡng không trả `PHRASE_NOT_FOUND`.
- Audit ghi `capped` để chỉnh N: mục tiêu khoảng 95% câu tìm kiếm thực tế được đếm đủ.

### 3.2. Chat

- Câu có ngoặc kép dùng bộ tìm cụm từ của trang tìm kiếm; câu không ngoặc kép dùng các kênh:
  số hiệu (kèm Điều nếu có), “Điều N” (khi không có số hiệu khớp), đủ từ khóa (có dấu và
  không dấu), tiêu đề văn bản; kênh “một trong các từ” và nhãn bản ghi cũ chỉ chạy khi thiếu.
- Từ nghi vấn (“là gì”, “như thế nào”…) bị bỏ; phần Điều/khoản/điểm và số hiệu được tách
  khỏi từ khóa khi đã có kênh riêng.
- Căn cứ hết hiệu lực: xem ADR-006 §2.5 (phương án C).

## 4. Vận hành

### Khởi động

```powershell
.\scripts\start-local-stack.ps1 -ProgramsRoot E:\Programs
Invoke-RestMethod http://127.0.0.1:8000/health
```

Trong Local Mode, trang tìm kiếm chỉ gọi API cùng origin.

### Trạng thái rỗng

| `empty_reason` | Nghĩa | Việc cần làm |
|---|---|---|
| `NO_AUTHORIZED_DOCUMENTS` | Không có văn bản đã duyệt người dùng được xem | Duyệt văn bản; kiểm ACL danh mục |
| `NO_RESULTS` | Có văn bản nhưng không khớp | Bớt từ khóa/bộ lọc |
| `PHRASE_NOT_FOUND` | Không có đúng cụm từ; kết quả kèm là đủ từ | Tắt “Tìm chính xác cụm từ” nếu muốn tìm từ rời |

### Lỗi thường gặp

| Mã | HTTP | Xử lý |
|---|---|---|
| `QUERY_EMPTY` | 422 | Nhập từ khóa hoặc cụm từ |
| `QUERY_TOO_LONG` | 422 | Rút dưới 500 ký tự (cụm từ dưới 200) |
| `TOO_MANY_TERMS` | 422 | Tối đa 20 từ |
| `PAGE_TOO_DEEP` | 422 | Thu hẹp bằng bộ lọc hoặc từ khóa cụ thể hơn |
| `RATE_LIMITED` | 429 | Chờ vài giây; giới hạn theo process |
| `SEARCH_BUSY` | 429 | Máy chủ đang xử lý 4 lượt; thử lại sau vài giây |
| `SEARCH_TIMEOUT` | 504 | Thu hẹp từ khóa/bộ lọc; kiểm tải DB và `statement_timeout` |
| `QUERY_TIMEOUT` (SSE chat) | — | Truy xuất hoặc kiểm lại căn cứ vượt ngân sách; thử lại |
| `DATABASE_NOT_CONFIGURED` | 503 | Chưa cấu hình DB |
| `INVALID_REQUEST` | 422 | Tham số sai (`page_size` > 50, UUID sai…) |

### Kiểm tra chỉ mục được dùng

```sql
SET enable_seqscan = off;
EXPLAIN (COSTS OFF)
SELECT 1 FROM document_nodes n
WHERE to_tsvector('simple'::regconfig, n.text_indexed)
      @@ plainto_tsquery('simple'::regconfig, 'báo cáo');
-- plan phải chứa document_nodes_search_word_gin
```

Không thêm b-tree trên `document_nodes(document_version_id)`: planner sẽ dùng nó thay GIN
và làm truy vấn chậm hàng giây (ADR-006 §2.3).

### Chuẩn hóa dữ liệu

- `GET /api/v1/system/mode` trả `search_normalization_status`
  (`current|stale|unavailable`), revision và số node cũ. `stale` nghĩa là có node chuẩn
  hóa bằng bảng biến thể dấu cũ; tìm kiếm có thể bỏ sót biến thể.
- Backfill: `python scripts/backfill_search_normalization.py --dry-run`, rồi chạy không
  `--dry-run`; chỉ tính lại `text_normalized`/`text_folded`, không đổi chứng cứ gốc.
- Sau mỗi đợt nạp/duyệt lớn, chạy `ANALYZE document_nodes;` để planner có thống kê đúng.

## 5. Hiệu năng tham chiếu

Đo trên máy dev, dữ liệu HƯ CẤU 1.000 văn bản × 100 khoản, không ép tắt seqscan:

| Luồng | p50 |
|---|---:|
| Tìm kiếm từ khóa, 1.000 khoản khớp | khoảng 100–140 ms |
| Tìm kiếm không kết quả | 15–40 ms |
| Tìm kiếm từ có trong 99% khoản (chạm giới hạn 8.000) | 1,1–1,3 s |
| Truy xuất chat | 0,15–0,35 s |

Mục tiêu tạm p95 300 ms chỉ chốt sau khi đo trên máy Windows đích. Chạy lại:
`python scripts/benchmark_search.py --documents 1000 --nodes-per-document 100`.

## 6. Kiểm thử

```powershell
$env:PYTHONPATH = "E:\Source\Evidence_RAG_Handoff\backend"
$env:EVIDENCE_TEST_DATABASE_URL = "postgresql://evidence_dev_admin:<password>@127.0.0.1:55432/postgres"
E:\Programs\EvidenceRAG\backend-venv\Scripts\python.exe -m pytest backend/tests -q

$node = "E:\Programs\EvidenceRAG\runtimes\node\node.exe"
$pnpm = "E:\Programs\EvidenceRAG\tools\pnpm\node_modules\pnpm\bin\pnpm.cjs"
& $node $pnpm --dir frontend test
& $node $pnpm --dir frontend build
& $node $pnpm --dir frontend lint
```

Test PostgreSQL tạo schema tạm rồi xóa; không ghi vào dữ liệu nghiệp vụ. CI phải đặt
`EVIDENCE_TEST_DATABASE_URL`; thiếu DSN thì `verify.ps1`/conftest dừng. Browser E2E (fixture
API): `$env:CHROME_PATH="<chrome.exe>"` rồi `pnpm --dir frontend run e2e:search`.

## 7. Đánh giá chất lượng

Chỉ chạy khi có Gold [Không triển khai – xem ADR-010] đã được người nắm nghiệp vụ duyệt và văn bản đã duyệt:

```powershell
python evaluation/scripts/evaluate_search.py `
  --base-url http://127.0.0.1:8000 --token-env EVIDENCE_ACCESS_TOKEN `
  --queries evaluation/search_eval/queries_gold.json --output evaluation/search_eval/reports
```

Case `approved_by=null` bị tách vào `hucau_metrics`; không có case duyệt thì
`quality_status=not_evaluated`. Không báo “đúng/đủ” khi chưa có báo cáo Gold [Không triển khai – xem ADR-010].

## 8. Sao lưu và rollback

- Migration 0006 chỉ thêm chỉ mục; rollback bằng `0006_search_index.down.sql`. Không
  rollback schema khi chưa sao lưu.
- Không xóa `document_nodes`, `source_spans`, `source_pages` để “làm sạch” tìm kiếm.
- Tạm tắt trang tìm kiếm: ẩn mục điều hướng ở frontend hoặc chặn `/api/v1/search` ở reverse
  proxy; chat vẫn hoạt động.

## 9. Việc còn chờ owner

- Duyệt Gold [Không triển khai – xem ADR-010], chốt p95 trên máy đích; định nghĩa `exact_phrase_precision` (tử số: khoản
  gắn `exact_phrase` có đúng cụm từ; mẫu số: tổng khoản gắn `exact_phrase`; ca âm = 0).
- Chuẩn hóa `doc_type` free-text cũ (giao diện nạp mới đã chọn từ
  `decree/circular/decision/other`).
- OCR cho PDF scan (không có node thì không tìm được); highlight bbox trong PDF.
- Rate limit/giới hạn đồng thời dùng store chung trước khi chạy nhiều worker.
