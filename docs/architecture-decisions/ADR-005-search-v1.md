# ADR-005 — Tìm kiếm văn bản (Search v1): FTS PostgreSQL, phân tầng khớp và trích dẫn lười

- Ngày: 31/10/2026
- Trạng thái: Đã triển khai một phần (P0 backend + frontend + test; xem mục "Hệ quả")
- Phạm vi: `GET /api/v1/search` + `/api/v1/search/approximate`, `SearchService`, migration `0006`, trang Tìm kiếm trong User Portal
- Tài liệu nguồn: `docs/KE_HOACH_TRIEN_KHAI_TIM_KIEM_V1_Evidence_RAG.md` (bản owner chốt), `SRS_v1.3.md`
- Cập nhật: phân trang/tổng số tính trong PostgreSQL từ 01/11 (bỏ cap 5.000); từ 05/11 áp
  dụng [ADR-006](ADR-006-retrieval-accuracy-bounds-and-ai-resilience.md) — giới hạn đếm
  `EVIDENCE_SEARCH_COUNT_CAP` (owner chốt 8.000), chọn phiên bản ở câu lệnh riêng, chat
  không ngoặc kép có kênh ứng viên giới hạn và `statement_timeout`. Các mục 4.3 về cap
  5.000 và legacy chat không có timeout không còn đúng.

## 1. Bối cảnh

Trước Search v1, backend chỉ có một kênh lexical thô trong `authorized_search.py`:
`to_tsvector('simple', ...)` tính lại từng dòng, AND toàn bộ từ rồi fallback OR từng từ,
không có phrase/adjacency, trần 12 node, không phân trang, không gộp theo văn bản.
Bảng `lexical_search_index` và `embedding_indices` có trong migration 0001 nhưng
không đoạn code nào dùng. Chưa có API search, chưa có Gold/metric.

Yêu cầu owner: bổ sung Search v1 trên PostgreSQL, không dùng search engine ngoài,
tích hợp vào app hiện có, giữ nguyên hành vi chat, không dùng mô hình AI trong search
(`KE_HOACH...` mục 1–3).

## 2. Kết quả SR-0 — đối chiếu hiện trạng với kế hoạch

| Kế hoạch mô tả | Mã nguồn thực tế | Kết luận |
|---|---|---|
| FTS `simple`, túi từ, không phrase | `authorized_search.py` dòng 193–231 | Khớp |
| `tsvector` tính lại từng dòng, không index | Không có expression index trước 0006 | Khớp |
| Trần 12 node | `fixed_pipeline.py` gọi search không truyền `limit`, mặc định 12 | Khớp |
| Chỉ node approved + provenance verified | Đúng trong SQL search và citation | Khớp |
| `text_indexed` = breadcrumb + title + number + label + content | `draft.py`: `indexed = title + document_number + label + exact_text` | Khớp; vì vậy index chỉ cần `text_indexed`, không concat lại |
| `text_folded`/`text_normalized` sinh lúc ingest | `draft.py` gọi `normalize_text`/`fold_text`; `unicode_norm.NORMALIZER_REVISION = vietnamese-tone-v3` (hoà→hòa, thuý→thúy, kì→kỳ) | Khớp; không cần hàm chuẩn hóa mới; đổi map cần backfill/reingest (chưa có dữ liệu approved) |
| Legal Reference Router | Không có lớp tên đó; `vietnamese_nlp/legal_citation_parser.py` + `canonical_document_number` đủ dùng | Tái sử dụng, bổ sung nhận diện số hiệu trần |
| `official_url` lưu nhưng chưa expose | `document_versions.official_url` + `source_provenance.official_url` | Đúng; Search v1 trả `document_versions.official_url` |
| `pg_trgm`/`unaccent` | Có file extension trong PostgreSQL 18.6 bundled (kiểm tra `share/extension`) | Có sẵn; **chưa bật** trigram (xem mục 4.2) |
| Dữ liệu 0 approved | Probe ngày 31/10/2026: 0 node approved, 0 provenance verified | Khớp; xem mục 6 |

Khác biệt quan trọng phát hiện ở SR-0/SR-1: `authorized_nodes` là `UNION` +
`DISTINCT`; khi truy vấn dạng `n.id IN (SELECT id FROM authorized_nodes)` planner
materialize view rồi lọc bằng `document_nodes_pkey`, **không dùng GIN** (EXPLAIN đã
chụp trong quá trình phát triển). Vì vậy thiết kế đã đổi cách lọc ACL (mục 4.1).

## 3. Quyết định

### 3.1. Kênh tìm kiếm

- Search v1 chỉ dùng PostgreSQL FTS (L2 syllable, `simple`); không tokenizer tiếng Việt,
  không embedding, không reranker, không mô hình AI. Phương án B (dense + RRF) để sau.
- Thêm migration `0006_search_index.sql` với hai GIN expression index:

```sql
CREATE INDEX document_nodes_search_word_gin
  ON document_nodes USING GIN (to_tsvector('simple'::regconfig, text_indexed));
CREATE INDEX document_nodes_search_folded_gin
  ON document_nodes USING GIN (to_tsvector('simple'::regconfig, text_folded));
```

- Đổi `NORMALIZER_REVISION` lên `vietnamese-tone-v3` và thêm cặp `kì→kỳ` (đáp ứng tiêu chí
  kì–kỳ); thay đổi bảng biến thể dấu cần reingest/backfill `text_normalized`/`text_folded`,
  hiện chưa có văn bản approved nên chưa ảnh hưởng dữ liệu.
- Không dùng `pg_trgm` trong v1: `phraseto_tsquery` đã giữ vị trí từ; trigram chỉ thêm
  khi benchmark xác minh cần (điều kiện ở kế hoạch mục 2 điểm 5). Vì vậy không có
  LIKE/`%`/`_` trong đường truy vấn, không phải escape LIKE.
- Không thêm cột sinh; index dùng đúng biểu thức mà query dùng. Migration có `.down.sql`,
  đã chạy up trên DB dev và down/up trong test PG tạm.

### 3.2. ACL và allowed document ids

- Trong cùng transaction (đã `set_config('app.user_id', ...)`), SearchService lấy
  `SELECT DISTINCT document_id FROM authorized_nodes` trước, rồi truyền mảng này vào
  câu truy vấn chính dưới dạng `n.document_id = ANY($11::uuid[])`.
- Lý do: view `UNION DISTINCT` không cho planner dùng GIN khi đứng sau `IN (view)`;
  cách này giữ ACL boundary ở view (nguồn duy nhất), nhưng câu truy vấn trên
  `document_nodes` có thể dùng expression index. Test PG tạm xác nhận plan chứa
  `document_nodes_search_word_gin` (`test_search_postgres.py`, `EXPLAIN` với
  `enable_seqscan=off`).
- Không cache danh sách allowed docs; mỗi request đọc lại trong transaction để thu hồi
  quyền có hiệu lực ngay. Nếu `allowed_documents` rỗng, trả `NO_AUTHORIZED_DOCUMENTS`
  mà không chạy truy vấn văn bản.

### 3.3. Phân tầng khớp

| Tầng | `match_type` | Cách xác định |
|---|---|---|
| T1 | `exact_phrase` | `phraseto_tsquery` trên `text_indexed`, sau đó **xác minh lại trên `text_normalized` của chính node** (không dùng `text_indexed`) |
| T2 | `phrase_folded` | `phraseto_tsquery` trên `text_folded`, xác minh trên `text_folded`; chỉ có khi T1 không khớp |
| T3 | `all_terms` | `plainto_tsquery` trên `text_indexed` (đủ mọi từ, không cần liền nhau) |
| T4 | `any_term` | chỉ trả qua `GET /api/v1/search/approximate`; không trộn vào trang chính |

- Khi truy vấn có ít nhất một T1/T2, danh sách chính chỉ gồm T1/T2; T3 không trộn vào.
  Khi không có T1/T2, T3 được trả kèm `empty_reason=PHRASE_NOT_FOUND` để người dùng
  thấy “không đúng cụm từ, đây là các khoản đủ từ”.
- Không ghép chuỗi tsquery từ input: phrase/terms được truyền tham số vào
  `phraseto_tsquery`/`plainto_tsquery`; input chỉ được tokenize bằng regex chữ-số.
- T2 không bao giờ được gắn `exact_phrase`; nhãn UI tương ứng “Cụm từ (không dấu)”.

### 3.4. Phiên bản, hiệu lực và phạm vi

- Chọn version approved theo `as_of_date`: `valid_from <= as_of` và
  (`valid_to IS NULL` hoặc `valid_to > as_of`), ưu tiên `version_number` lớn nhất.
- `amendment_state` lấy từ `node_effective_intervals` + snapshot đang `is_active`,
  **theo từng khoản**. Không có interval ⇒ `unknown`.
- `effectivity_snapshot_status` = `ok` nếu tồn tại snapshot active, ngược lại `stale`.
  Định nghĩa `stale` đơn giản vì mã hiện tại chưa có job tạo snapshot; đây là điểm cần
  làm rõ khi có Effective Snapshot builder (xem “Hệ quả”).
- `only_active=true` chỉ giữ khoản có `active`; mặc định hiện cả `modified/repealed/
  suspended/not_yet_effective/unknown` kèm nhãn.

### 3.5. Trích dẫn lười và highlight

- Kết quả trả `node_id`, `label`, `page`, `quote_exact`, `snippet`, `snippet_start`,
  `highlights` (offset tuyệt đối trên `quote_exact`), `viewer_url`,
  `source_hash`. Không tạo bản ghi `evidence_id` mỗi lần tìm.
- `viewer_url` = `/api/v1/citations/ev_<node_id>/pdf?as_of_date=...`. Khi người dùng mở,
  API citation hiện có kiểm lại ACL/provenance và hash PDF. Không đổi citation contract.
- Highlight chỉ được trả khi tìm thấy đúng span trên `text_original`; nếu không chắc
  (không match trực tiếp, hoặc phrase chỉ khớp folded) thì `highlights=[]` — không tô.
- Không có overlay PDF (PDF.js text layer/bbox); đó là WP riêng, nằm ngoài Search v1.

### 3.6. Chat compatibility

- `SearchService.search_clauses` là adapter cho chat: nếu câu hỏi không có cụm trong nháy
  kép, delegate nguyên `PostgresAuthorizedNodeSearch.search` (giữ hành vi cũ: 12 căn cứ,
  stopword, xếp hạng theo số hiệu/Điều). Nếu có nháy kép, dùng đường phrase mới; nếu
  không có kết quả thì fallback legacy.
- Golden test `test_chat_characterization.py` khóa: 12 evidence, 8 claims, 3 suggestions,
  trạng thái, `answer_generated=False`, chuỗi 6 SSE event. Test này xanh trước và sau refactor.
- Hệ quả: chat **không** tự động hưởng lợi từ xếp hạng/tier mới ngoài chế độ quote;
  đây là lựa chọn tương thích ngược có chủ đích.

### 3.7. API, an toàn, hiệu năng

- `GET /api/v1/search` và `GET /api/v1/search/approximate`; tham số theo kế hoạch mục 6.
- Giới hạn: q ≤ 500 ký tự, ≤ 20 từ, `page_size` ≤ 50, `page*page_size` ≤ 1000
  (mặc định cấu hình qua `EVIDENCE_SEARCH_*`).
- `statement_timeout` đặt trong transaction search (`EVIDENCE_SEARCH_STATEMENT_TIMEOUT_MS`,
  mặc định 5000 ms); lỗi timeout map `SEARCH_TIMEOUT` (504).
- Rate limit: sliding window trong bộ nhớ theo principal (`EVIDENCE_SEARCH_RATE_PER_MINUTE`,
  mặc định 30/phút). Đây là giới hạn **mỗi process**, không chia sẻ giữa nhiều worker;
  chấp nhận cho Local Mode một process, cần thay bằng Redis/DB nếu chạy đa worker.
- Audit: sau khi tìm, append `audit_events` với **hash SHA-256 của câu truy vấn**, độ dài,
  mode, page/page_size, số kết quả, thời gian; không lưu nội dung thô. Audit lỗi không làm
  hỏng request search.
- Không log/trả tên tài liệu ngoài quyền; `NO_AUTHORIZED_DOCUMENTS` dùng một câu duy nhất.

### 3.8. Frontend

- Trang Search là surface riêng trong User Portal; chat giữ mounted khi chuyển trang.
- State truy vấn nằm trong URL query string (`history.replaceState`), fallback state nội bộ
  khi shell không hỗ trợ history.
- Bộ lọc `doc_type` dùng mã `decree/circular/decision/other`; dữ liệu hiện lưu doc_type dạng
  text tự do nên cần chuẩn hóa vocabulary khi nhập liệu (xem “Hệ quả”).
- `viewer_url` chỉ chấp nhận regex citation `/api/v1/citations/ev_<uuid>/pdf...`; backend
  trả đúng dạng này.
- Không thêm dependency; màu dùng token hiện có.

## 4. Hệ quả

### 4.1. Đã có bằng chứng

- Backend: `187 passed` khi chạy với PostgreSQL thật (`EVIDENCE_TEST_DATABASE_URL`),
  gồm test PG tạm cho migration 0006 up/down, EXPLAIN index, T1/T2/T3, ACL, phân trang,
  hiệu lực từng khoản, phrase vắt qua breadcrumb không bị gắn T1, và E2E API qua ASGI
  (`test_search_postgres.py`).
- Frontend: `65 passed` (14 file), `tsc --noEmit` + `vite build` OK, `eslint --max-warnings=0` OK.
- OpenAPI: `scripts/export_openapi.py --check` OK; có `/api/v1/search` và
  `/api/v1/search/approximate`.
- Trạng thái dữ liệu dev: 0 văn bản approved; probe trả
  `empty_reason=NO_AUTHORIZED_DOCUMENTS` (đúng thiết kế, không phải lỗi search).

### 4.2. Chưa có bằng chứng / còn nợ

- Chưa có Gold search được người nắm nghiệp vụ duyệt; chưa đo recall/precision/
  `wrong_doc_rate`/`wrong_node_rate`/no-result trên văn bản thật. Eval harness mới có
  self-test HƯ CẤU (22 test), `quality_status=not_evaluated`.
- Chưa đo p50/p95 trên máy Windows đích/quy mô ~100k node; chưa chạy load test.
- Chưa chạy HTTP server thật + browser E2E; mới có ASGI E2E (TestClient/ASGITransport)
  và UI test với mock fetch.
- Chưa có highlight trong PDF (chỉ snippet/HTML + mở đúng trang); chưa có OCR.
- Chưa làm “xem thêm khoản khớp trong từng văn bản” (API chỉ trả tối đa 5 khoản/văn bản,
  không có tham số phân trang khoản).
- Chưa có test contrast/a11y tự động; chưa đo “Local Mode không request ra ngoài” bằng
  bắt gói.
- `pg_trgm` để ngỏ: nếu benchmark xác minh cần xác minh phrase nhanh hơn, thêm sau với
  quyết định riêng (kèm escape LIKE).
- Quy ước `phrase_found`/`empty_reason` và cách ẩn T3 khi có T1 cần owner/reviewer xác nhận
  khi làm Gold.

### 4.3. Rủi ro đã biết

- Tổng số/ phân trang lấy từ câu count SQL trên cùng predicate; nếu verification T1 loại
  một ứng viên nhưng node đó không có trong T3, `totals.clauses` có thể cao hơn số hiển thị.
  Với dữ liệu hiện tại chưa gặp; cần test trên corpus lớn.
- ~~Candidate cap 5000 cho mỗi tier~~ — đã bỏ 01/11; thay bằng giới hạn đếm có cờ
  `totals.capped` (ADR-006).
- Rate limit trong bộ nhớ không dùng được khi chạy nhiều worker.
- ~~Legacy chat search không có timeout~~ — từ 05/11 chat dùng chung `statement_timeout`
  và tối đa 4 lượt DB đồng thời (ADR-006).
- `doc_type` khi upload nay chọn từ 4 mã (`decree/circular/decision/other`); dữ liệu
  free-text cũ vẫn cần chuẩn hóa trước khi lọc đầy đủ.

## 5. Phương án bị loại

- **B (dense + RRF + reranker)**: chưa có model chạy local + Gold; làm sau, cắm thêm kênh
  qua interface `SearchService` (dự kiến `LexicalChannel`, `DenseChannel`).
- **C (Elasticsearch/OpenSearch/Meilisearch/ParadeDB)**: loại theo kế hoạch mục 1; nhân đôi
  ACL, thêm vận hành, vướng “PostgreSQL là DB duy nhất”.

## 6. Việc cần owner/reviewer

1. Duyệt 3 văn bản `pending_review` (hoặc nạp corpus thật) và xác minh provenance/span;
   nếu không, Search đúng code nhưng luôn rỗng.
2. Duyệt bộ Gold search 30–50 truy vấn; khi đó mới được báo metric chất lượng.
3. Chốt quy ước `exact_phrase_precision` cho ca không có exact phrase, ngưỡng chấp nhận
   p95, và câu chữ `PAGE_TOO_DEEP`.
4. Quyết định OCR (ADR riêng) và chuẩn hóa `doc_type` khi nhập liệu.

## 7. Cập nhật 31/10/2026 — normalization, benchmark, phân trang khoản

### 7.1. Chuẩn hóa và backfill

- Migration `0007_normalization_revision.sql` thêm `document_nodes.normalization_revision`;
  dữ liệu cũ được gán `vietnamese-tone-v2`, dữ liệu mới ghi `vietnamese-tone-v3`.
- Backend kiểm tra lúc khởi động và `/api/v1/system/mode` trả trạng thái stale/current;
  `scripts/backfill_search_normalization.py` tính lại `text_normalized`/`text_folded`
  (không đổi `text_original`/`text_indexed`). Đã chạy backfill trên DB dev:
  648 node v2 → 0 stale; log `docs/evidence/2026-10-31-search-v1/normalization-backfill.log`.
- Test PG tạo một node giả lập v2 (`định kì`, text_folded `dinh ki`), xác nhận trước backfill
  không khớp cụm `định kì`; sau backfill khớp `phrase_folded` (không gắn `exact_phrase`).

### 7.2. Benchmark và planner

- Script `scripts/benchmark_search.py` (dữ liệu sinh **HƯ CẤU**, 1.000 văn bản × 100 node =
  100.000 node, mỗi văn bản 1 node chứa cụm; có page/span/provenance/category ACL giả).
- **Không** đặt `enable_seqscan=off`; planner dùng mặc định (`enable_seqscan=on`,
  `random_page_cost=4`, `work_mem=4MB`, JIT on). EXPLAIN ANALYZE thật cho phrase query:
  execution 66–423 ms tùy lần đo; plan có **`document_nodes_search_word_gin`**; plan/config
  đầy đủ ở `docs/evidence/2026-10-31-search-v1/benchmark/benchmark.md` và `benchmark.json`.
- Kết quả lần chạy cuối (10 vòng, máy dev Windows): phrase p50/p95 **243,62 / 324,31 ms**;
  keyword **255,57 / 268,95 ms**; không kết quả **62,61 ms**. Mục tiêu tạm p95 300 ms:
  phrase **vượt** 24,31 ms, keyword đạt; mục tiêu chỉ chốt sau khi đo máy đích.
- API default (có approximate count) 338,66 ms nhờ cap: approximate hidden được tính có trần
  500 và bị bỏ khi có tầng cụm từ hoặc số khoản chính >200; `/search/approximate` vẫn trả
  kết quả thật khi mở rộng. Nếu mở rộng luôn tính approximate, caller phải chấp nhận chi phí
  cao hơn (trước đó 42 s ở 100k node).
- ACL được tối ưu bằng `_ALLOWED_DOCUMENTS_SQL` (đọc category_acl/document_acl, không scan
  100k node mỗi request) và base lọc `n.review_status='approved'`; đây là thay đổi hiệu năng
  quan trọng, đã test ACL khác principal trả 0 kết quả.

### 7.3. Phân trang khoản và UI

- API thêm `clause_page`/`clause_page_size` (max 50) và mỗi document trả
  `clause_page`, `clause_page_size`, `has_more_clauses`; `matched_clause_count` vẫn là tổng.
- UI hiển thị “Hiển thị X/Y khoản” và nút “Xem thêm khoản khớp”; client cộng dồn theo
  `node_id` vì API trả offset window (nếu API đổi sang cumulative, dedupe vẫn an toàn).
- Kích thước trang khoản cố định 5 ở UI; URL giữ `clause_page` nhưng reload chỉ tải trang
  khoản hiện tại, không dựng lại buffer các trang trước (đã ghi là hạn chế).

### 7.4. Kiểm thử bổ sung

- Backend: 187 passed với PostgreSQL; 171 passed + 16 skipped khi không DSN.
- Frontend: 65 test/14 file; thêm a11y (role/aria-live/aria-expanded), contrast WCAG đọc
  token (thấp nhất 5,21:1; `<mark>` 14,26:1), Local Mode (mọi fetch `/api/v1`, `dist` không
  tài nguyên ngoài), browser E2E Chrome headless qua CDP với fixture API cùng origin
  (12 request, 0 external http(s) origin) — chưa phải backend thật/approved data.
- CI: workflow đặt `EVIDENCE_TEST_DATABASE_URL` từ secret và `CI=true`; `verify.ps1` +
  `backend/tests/conftest.py` dừng nếu CI thiếu DSN, để test PG không bị skip.

### 7.5. Mặc định chờ owner chốt

- `PAGE_TOO_DEEP`: “Bạn đã xem tới giới hạn kết quả. Hãy thu hẹp bằng bộ lọc hoặc dùng từ
  khóa cụ thể hơn.” (đã áp dụng backend + frontend).
- `doc_type`: danh mục có kiểm soát do curator quản lý; UI tạm dùng
  `decree/circular/decision/other`; dữ liệu free-text cũ cần chuẩn hóa.
- `exact_phrase_precision`: tử số/tổng số khoản gắn exact_phrase tự xác minh; ca âm = 0;
  mẫu số 0 ở case dương = null (đã sửa harness + self-test 27 test).
- p95 tạm 300 ms trên 100k node sinh; chốt lại sau máy đích.
- Rate limit hiện chỉ đúng **một process**; đa worker phải chuyển sang store chia sẻ.

### 7.6. Việc còn nợ

- Gold thật + duyệt văn bản/provenance; chưa đo chất lượng.
- PDF bbox highlight, OCR, browser E2E với backend thật/approved data, CI browser runner.
- Reload `clause_page>1` chưa dựng lại buffer; “xem thêm” chỉ ở clause window hiện tại.