# KẾ HOẠCH TRIỂN KHAI — Tìm kiếm văn bản (Search v1)

> **[Không triển khai – xem ADR-010]** Mọi nội dung về bộ câu hỏi Gold, trap set, calibration và held-out trong tài liệu này không được triển khai theo [ADR-010](architecture-decisions/ADR-010-khong-trien-khai-bo-cau-hoi-gold.md). Phần còn lại giữ nguyên.

Hệ thống: Vietnamese Evidence RAG Agent · Phiên bản tài liệu 1.0 · ngày 31/10/2026
Người nhận: AI triển khai (đã có mã nguồn và `SRS_v1.3.md` trong repo)
Trạng thái: **owner đã chốt hướng** (mục 1). Tài liệu này thay thế bản phương án trước; mọi điểm khác biệt đã được ghi ở mục 2.

---

## 0. Cách dùng tài liệu này

1. Đây là bản **đã chỉnh** của phương án A (Search v1 trên PostgreSQL). Làm theo tài liệu này, không làm theo bản phương án cũ ở những điểm mục 2 nêu.
2. Tài liệu mô tả hiện trạng mã nguồn theo bản phương án trước (tên file, số dòng). **Việc đầu tiên (SR-0) là đối chiếu lại với mã nguồn thật**; chỗ nào không khớp thì báo và ghi ADR, không làm theo trí nhớ.
3. Quy tắc làm việc:
   - Làm tự chủ, ít hỏi lại. Điểm chưa chốt: dùng mặc định ở mục 11, ghi ADR, làm tiếp. Chỉ dừng chờ người ở bốn nhóm: **nghiệp vụ, quyền truy cập, bảo mật, độ đúng của căn cứ**.
   - **Tương thích ngược nghiêm ngặt:** không phá interface hiện có; tham số mới mặc định giữ nguyên hành vi cũ; chat giữ nguyên hành vi (12 căn cứ, claims, SSE).
   - Mỗi WP chỉ xong khi: code + migration + test xanh + tài liệu cập nhật + báo cáo theo mẫu ở mục 12. Báo trung thực phần chưa xong.
   - Không tuyên bố số liệu chưa đo ("p95 300 ms", "đúng/đủ"). Mọi con số ghi môi trường, phiên bản, dữ liệu.
   - Không bịa văn bản pháp luật. Fixture gắn nhãn "HƯ CẤU". Đánh giá chất lượng chỉ dùng văn bản thật đã duyệt.
   - Không tự duyệt tài liệu và không tự công nhận đáp án mẫu. Hai việc đó do người có thẩm quyền làm.

---

## 1. Quyết định đã chốt

| # | Chủ đề | Quyết định |
|---|---|---|
| 1 | Phương án | **A:** Search v1 trên PostgreSQL. Phương án B (ngữ nghĩa: tokenizer tiếng Việt + embedding + RRF + pre-gate + rerank) làm **sau**, khi đã có model chạy local và Gold [Không triển khai – xem ADR-010] đã duyệt. Phương án C (Elasticsearch/OpenSearch/Meilisearch/ParadeDB) **loại**: nhân đôi ACL, thêm vận hành, vướng quyết định "PostgreSQL là DB duy nhất" |
| 2 | Hình thức | **Tích hợp vào app hiện có dưới dạng module riêng**, không làm app độc lập. Tìm kiếm là trang riêng trong User Portal; Chat Agent có nút "Xem tất cả kết quả tìm kiếm". Chat giữ nguyên hành vi hiện tại |
| 3 | Chế độ cụm từ | Mặc định **tự nhận diện**: người dùng bọc nháy kép thì là cụm từ chính xác; có ô tích "Tìm chính xác cụm từ" cho người không quen nháy |
| 4 | Dùng chung | Chat và trang tìm kiếm dùng **một** `SearchService`; nâng cấp lên phương án B chỉ cắm thêm kênh, không đổi API và giao diện |
| 5 | Hệ điều hành và chế độ | Windows; chạy trọn ở **Local Mode** (không dịch vụ ngoài, không tải tài nguyên ngoài); không dùng mô hình AI trong Search v1 |
| 6 | Dữ liệu | Số văn bản đã duyệt hiện có và mốc thời gian mong muốn: **owner sẽ cung cấp** (mục 10). Việc duyệt văn bản do reviewer/người nắm nghiệp vụ làm, AI không được tự duyệt |

**Vì sao tích hợp, không tách app:** dùng chung ACL, đăng nhập, nhật ký kiểm toán, trình xem PDF, API trích dẫn và snapshot hiệu lực; một bộ cài, một dịch vụ, một cơ sở dữ liệu, một lần sao lưu trên Windows; hệ thống chạy trong mạng nội bộ nên chưa cần scale riêng. Chỉ cân nhắc tách khi tìm kiếm phục vụ nhóm người dùng/vùng mạng khác, cần phát hành độc lập, hoặc sau này chuyển sang search engine ngoài. Để tách được không đau: giữ module sạch (`SearchService`, tiền tố `/api/v1/search`, trang riêng, không trộn vào code chat).

---

## 2. Những điểm đã chỉnh so với phương án trước

| # | Điểm chỉnh | Lý do và yêu cầu |
|---|---|---|
| 1 | **Hiệu lực tính theo từng khoản** | `amendment_state` đặt ở **từng khoản**, không ở cấp văn bản; khoản chưa rõ hiện "Hiệu lực chưa xác minh"; snapshot hiệu lực stale thì có cảnh báo |
| 2 | **Trang rỗng không lộ sự tồn tại** | `KHO_CHUA_CO_VAN_BAN_DUYET` tính trên **tập tài liệu người dùng được phép xem**, và thông điệp là "Chưa tìm thấy tài liệu được phép truy cập" |
| 3 | **Chuẩn hóa dấu tiếng Việt** | Kênh có dấu chạy trên văn bản đã chuẩn hóa NFC + dấu thanh (hòa/hoà) cả lúc index lẫn lúc truy vấn, **cùng một hàm**. Kênh không dấu chỉ để tăng recall, có `match_type` riêng, **không bao giờ** gắn `exact_phrase` |
| 4 | **Tách kết quả "một phần"** | Kết quả `any_term` gom vào mục "Kết quả gần đúng" thu gọn, không trộn với kết quả khớp cụm từ hoặc đủ từ |
| 5 | **`pg_trgm` chỉ giữ khi đo cần** | `phraseto_tsquery` đã giữ vị trí từ. Chỉ thêm index trigram nếu benchmark cho thấy cần; kiểm bản PostgreSQL Windows đóng gói offline có sẵn module contrib; LIKE phải escape `%` và `_` |
| 6 | **OCR là ngoại lệ, không bật mặc định** | Cần ADR (engine, giấy phép, dung lượng trong trần 10 GB, chạy offline). Văn bản từ OCR chỉ thành căn cứ sau khi reviewer duyệt và gắn `extraction_method=ocr` |
| 7 | **Truy vấn an toàn** | Không ghép chuỗi tsquery bằng tay từ input người dùng; dùng `plainto_tsquery`/`phraseto_tsquery` có tham số; giới hạn độ dài, số từ, thời gian chạy và tần suất |
| 8 | **Xác minh cụm từ trên nội dung, không trên `text_indexed`** | `text_indexed` chứa cả breadcrumb + tiêu đề + số hiệu; cụm từ có thể "khớp" xuyên ranh giới giữa breadcrumb và nội dung. Bước xác minh phải chạy trên trường nội dung của node |
| 9 | **Bản ghi trích dẫn tạo lười** | Không tạo `evidence_id` cho mọi kết quả mỗi lần tìm (phình dữ liệu). Kết quả mang `node_id` + span; bản ghi trích dẫn tạo khi người dùng mở PDF, và lúc mở phải kiểm lại ACL và hash |
| 10 | **Nhật ký không lưu nội dung truy vấn thô** | Audit ghi băm câu truy vấn, độ dài, bộ lọc, số kết quả; nội dung thô chỉ lưu nếu owner chốt chính sách riêng tư |
| 11 | **Mục tiêu hiệu năng là mục tiêu đo** | p95 ≤ 300 ms là mục tiêu phải đo trên máy Windows đích, chưa phải cam kết; ước lượng ngày công cũng chỉ là thô |

---

## 3. Phạm vi

**Trong phạm vi Search v1 (P0)**

- Tìm từ khóa và cụm từ trên kho văn bản đã duyệt; lọc theo danh mục, loại văn bản, cơ quan ban hành, ngày áp dụng.
- Kết quả gộp theo văn bản; mỗi văn bản hiện các khoản khớp kèm trích dẫn nguyên văn, snippet đánh dấu, trang PDF, trạng thái hiệu lực **của khoản**.
- Phân trang đầy đủ, tổng số chính xác; trạng thái rỗng phân biệt rõ.
- Nhận diện truy vấn là số hiệu văn bản (ví dụ `385/2026/NĐ-CP`) để đưa văn bản đó lên đầu, dùng lại Legal Reference Router nếu đã có trong mã nguồn.
- Mở PDF nguồn đúng trang qua trình xem và API trích dẫn hiện có (không đổi).
- Dùng chung `SearchService` với chat mà không đổi hành vi chat.

**Ngoài phạm vi (làm riêng, không gộp)**

- Tô sáng vị trí trong PDF (PDF.js text layer + bbox/quads) — WP riêng.
- Tìm theo ngữ nghĩa/diễn đạt khác (phương án B).
- Gợi ý khi gõ (typeahead), lưu truy vấn, lịch sử tìm kiếm, xuất kết quả (P1).
- Ghi truy vấn tìm kiếm vào bộ nhớ AI của Chat Agent.

---

## 4. Hiện trạng (theo mô tả trước — phải đối chiếu lại ở SR-0)

- Chỉ có một kênh lexical `to_tsvector('simple')`; câu hỏi tách thành túi từ khóa, AND toàn bộ rồi fallback OR từng từ; không có phrase/adjacency (`authorized_search.py`, khoảng dòng 193–231).
- `tsvector` tính lại từng dòng trong truy vấn, không dùng index; bảng `lexical_search_index` + GIN đã có trong migration nhưng không đoạn code nào dùng (`0001_core.sql`).
- Trần 12 node mỗi lượt, không phân trang, không gộp theo văn bản (`fixed_pipeline.py`, khoảng dòng 127–135).
- Chỉ tìm node `approved` + provenance `verified`. Theo mô tả, DB hiện **0 node approved** nên mọi truy vấn trả rỗng.
- Chưa có API search; chưa có Gold [Không triển khai – xem ADR-010]/metric đo recall/precision ([`history/eval-gold-protocol.md`](history/eval-gold-protocol.md)).
- `text_indexed` đã chứa breadcrumb + tiêu đề + số hiệu + nhãn + nội dung (`draft.py`); `text_folded` và `text_normalized` sinh lúc ingest.
- `official_url` đã lưu trong `document_versions` nhưng chưa được expose ở API/UI nào.
- SRS v1.3 định baseline 3 kênh `L1_WORD` + `L2_SYLLABLE` + `DENSE`, RRF, pre-gate, rerank top-12 (`SRS_v1.3.md`, khoảng dòng 279–303); mã nguồn mới làm được phần rất thô của kênh lexical.

---

## 5. Thiết kế kỹ thuật

### 5.1 Chuẩn hóa và index (migration `0006_search_index.sql` + `.down.sql`)

**Chuẩn hóa (một hàm duy nhất, dùng chung index và truy vấn)**

1. Unicode NFC.
2. Chuẩn hóa dấu thanh theo bảng mapping có version (`hòa/hoà`, `thúy/thuý`…), kiểm hai chiều, ghi `normalization_revision`.
3. Hạ chữ thường; gom khoảng trắng; dấu câu coi là ký tự phân tách.
4. Kênh không dấu: thêm bước bỏ dấu (`đ → d` xử lý riêng).
5. Bản gốc `text_original` **không bao giờ bị sửa**. Hàm chuẩn hóa trả thêm **offset map** từ văn bản chuẩn hóa về `text_original` để tính highlight.

Nếu mapping đổi (đổi `normalization_revision`) thì index cũ không còn khớp: phải có job reindex hoặc kiểm tra revision lúc khởi động và báo rõ. Không giả định "không bao giờ cần reindex".

**Index đề xuất** (xác nhận bằng `EXPLAIN` ở SR-1; có thể thay biểu thức index bằng cột `tsvector` sinh sẵn nếu planner không dùng index hoặc để tránh tính lại; ghi ADR):

```sql
-- kênh có dấu (chính xác)
CREATE INDEX document_nodes_search_word_gin
  ON document_nodes
  USING GIN (to_tsvector('simple'::regconfig, text_indexed));

-- kênh không dấu (recall bổ sung, trọng số thấp)
CREATE INDEX document_nodes_search_folded_gin
  ON document_nodes
  USING GIN (to_tsvector('simple'::regconfig, text_folded));
```

- Phải dùng `'simple'::regconfig` tường minh (immutable) và dùng **đúng cùng biểu thức** trong truy vấn thì index mới được dùng.
- **Index trigram (`pg_trgm`) chỉ thêm khi benchmark chứng minh cần** (ví dụ xác minh cụm từ chậm). Nếu thêm: kiểm module contrib có trong bản PostgreSQL Windows đóng gói offline; ghi dung lượng index và chi phí ghi; escape `%`, `_` và `\` khi dùng LIKE.
- Migration có `.down.sql` và test up/down; không đổi cấu trúc bảng hiện có.

### 5.2 Truy vấn

**Phân tích truy vấn (ứng dụng, không phải SQL):**

- Giới hạn độ dài (mặc định 500 ký tự) và số từ (mặc định 20); vượt thì lỗi có thông điệp rõ.
- Nhận diện nháy kép "…" ⇒ cụm từ; có thể có nhiều cụm kèm từ khóa rời (P1: nếu phức tạp, chỉ hỗ trợ một cụm + từ khóa).
- Nhận diện số hiệu văn bản bằng quy tắc; khớp duy nhất + approved + ACL thì đưa văn bản lên đầu.
- Không diễn giải toán tử (`-`, `|`, `&`, `:*`, `<->`, dấu nháy đơn…) từ input người dùng; coi chúng là ký tự phân tách.

**Tầng khớp (xếp từ cao xuống thấp, không trộn):**

| Tầng | `match_type` | Điều kiện |
|---|---|---|
| T1 | `exact_phrase` | Cụm từ **có dấu** (đã chuẩn hóa) có trong nội dung node; đã xác minh trên trường nội dung |
| T2 | `phrase_folded` | Cụm từ khớp ở kênh không dấu, nhưng không khớp có dấu |
| T3 | `all_terms` | Có đủ mọi từ của truy vấn, không nhất thiết liền nhau |
| T4 | `any_term` | Chỉ có một phần các từ — **chỉ hiện ở mục "Kết quả gần đúng" thu gọn** |

- Dùng `phraseto_tsquery('simple'::regconfig, $1)` cho cụm từ, `plainto_tsquery(...)` cho đủ từ, và nối bằng toán tử tsquery `||` (OR) khi cần tầng `any_term`. Không ghép chuỗi tsquery từ input.
- `phraseto_tsquery` chỉ bảo đảm các từ gốc liền kề; **bắt buộc có bước xác minh** nguyên văn trước khi gắn `exact_phrase`: so khớp chuỗi đã chuẩn hóa (gom khoảng trắng, dấu câu thành khoảng trắng) trên **trường nội dung của node**, không phải `text_indexed`. Chỉ khi xác minh qua mới gắn nhãn T1/T2.
- Không bao giờ gắn nhãn "khớp cụm từ" cho kết quả túi từ.

**Phạm vi và quyền (SQL, trước tìm kiếm):**

- Lấy tập node được phép từ `authorized_nodes` (đặt `app.user_id` bằng `SET LOCAL` trong transaction) rồi lọc bằng semi-join (`n.id IN (SELECT id FROM authorized_nodes)`) để GIN vẫn được dùng. View có `UNION DISTINCT` dễ làm planner bỏ index: **phải kiểm `EXPLAIN`**. Nếu không đạt, thử các cách thay: tính trước tập `document_id` được phép (nhỏ) rồi lọc; CTE `MATERIALIZED`; ghi ADR kèm số đo.
- Điều kiện luôn có: node `approved` + provenance `verified` + span/trang khớp (giữ đúng điều kiện citation hiện tại).
- Bộ lọc: `category_ids` (ACL + phạm vi), `doc_type`, `issuing_body`, `as_of_date`.
- Chọn **version** theo `as_of_date` (version đã duyệt có hiệu lực tại ngày đó; không có `as_of_date` thì version đã duyệt mới nhất) để không trùng nhiều version.

**Xếp hạng:** trong từng tầng, `ts_rank_cd` + tăng điểm khi trùng số hiệu/tiêu đề. Hai kênh (có dấu, không dấu) hợp nhất bằng RRF đơn giản hoặc cộng điểm trọng số thấp cho kênh không dấu; **không** dùng điểm RRF/ts_rank làm ngưỡng tuyệt đối để quyết định "có kết quả hay không". Kênh không dấu không được nâng một kết quả lên tầng T1.

**Gộp theo văn bản và phân trang:**

- Gộp theo `document_id` (sau khi chọn version); mỗi văn bản trả tối đa N khoản khớp (mặc định 5, cấu hình được), có nút xem thêm.
- Phân trang theo **văn bản**; `total_documents` và `total_clauses` chính xác (đếm sau khi gộp, không đếm trước). `page_size` tối đa 50; giới hạn độ sâu (`page × page_size` ≤ giới hạn cấu hình, mặc định 1000) và trả thông báo khi vượt.
- Trần 12 cho chat giữ nguyên; trang tìm kiếm không dùng trần 12.

**Hiệu lực của khoản:** với mỗi khoản trả `amendment_state` theo `as_of_date` lấy từ snapshot hiệu lực (`active`, `modified`, `repealed`, `suspended`, `not_yet_effective`, `unknown`), kèm `effectivity_snapshot_status` (`ok` hoặc `stale`). Mặc định **hiện cả khoản đã sửa đổi/bãi bỏ kèm nhãn** (người dùng có thể đang tìm chính quy định đó); có công tắc lọc "Chỉ hiện quy định đang áp dụng" (mặc định tắt). Snapshot stale thì trả cảnh báo; không dùng snapshot cũ để khẳng định hiệu lực.

**An toàn và hiệu năng truy vấn:**

- Tham số hóa mọi truy vấn; `statement_timeout` riêng cho search; giới hạn tần suất theo người dùng; không có đường nào để input người dùng thành SQL hay toán tử tsquery.
- Chuỗi LIKE (nếu dùng) phải escape.
- Không lộ thông tin ngoài quyền qua: tổng số, phân trang, trạng thái rỗng, thông báo lỗi, thời gian phản hồi bất thường, gợi ý "bạn muốn tìm…".

### 5.3 Trích dẫn và highlight

- Mỗi khoản khớp trả: `node_id`, `document_version_id`, `label`, `page`, `quote_exact` (nguyên văn từ `text_original`), `snippet`, `highlights` (offset trên `text_original`), `match_type`, `amendment_state`.
- **Highlight:** tính trên `text_original` nhờ offset map. Nếu không chắc offset (chuẩn hóa không đảo ngược được) thì **không tô** và hiện snippet không đánh dấu. Không bao giờ tô lệch.
- **Bản ghi trích dẫn tạo lười:** khi người dùng bấm "Mở trang PDF nguồn", gọi API trích dẫn hiện có để tạo/lấy `evidence_id` và `viewer_url`; lúc đó kiểm ACL + hash như hiện nay. Nếu mã nguồn bắt buộc phải có `evidence_id` ngay trong kết quả, ghi ADR về cách tránh phình bảng (ví dụ ID xác định theo node + version, không ghi bản ghi mới).
- Trả thêm `official_url` (nếu curator đã xác minh) cho từng văn bản.

### 5.4 Dùng chung với chat

Refactor `PostgresAuthorizedNodeSearch` thành `SearchService` có hai phương thức:

- `search_clauses(...)` — `limit=12`, dùng cho pipeline chat; **giữ nguyên hành vi hiện tại**; chỉ thêm chế độ phrase khi người dùng bọc nháy kép.
- `search_documents(...)` — `page`/`page_size`, gộp theo văn bản, dùng cho trang tìm kiếm.

**Bắt buộc:** trước khi refactor, viết **characterization test** (golden test) cho kết quả chat hiện tại (cùng đầu vào ⇒ cùng 12 căn cứ, claims, SSE). Refactor chỉ được xong khi các test này vẫn xanh.

Thiết kế để phương án B là "cắm thêm kênh": giao diện kênh (`LexicalChannel`, sau này `DenseChannel`), hàm hợp nhất kết quả đặt riêng, không đổi API/UI khi thêm kênh.

---

## 6. API

```http
GET /api/v1/search?q=báo+cáo+định+kỳ+và+thường+xuyên
    &mode=auto|phrase|keywords
    &category_id=...&doc_type=decree&issuing_body=...&as_of_date=2026-10-31
    &only_active=false&group_by=document&page=1&page_size=20
```

Ví dụ phản hồi:

```json
{
  "query": {"original": "…", "phrase": "báo cáo định kỳ và thường xuyên", "mode": "phrase", "normalization_revision": "…"},
  "phrase_found": true,
  "totals": {"documents": 3, "clauses": 5, "approximate_matches_hidden": 7},
  "page": 1, "page_size": 20, "has_more": false,
  "effectivity_snapshot_status": "ok",
  "results": [{
    "document_id": "…", "document_version_id": "…",
    "document_number": "385/2026/NĐ-CP", "title": "…", "doc_type": "decree",
    "issuing_body": "…", "official_url": "https://…",
    "matched_clause_count": 2,
    "clauses": [{
      "node_id": "…", "label": "Khoản 1 Điều 5", "page": 12,
      "match_type": "exact_phrase",
      "amendment_state": "active", "amendment_as_of": "2026-10-31",
      "quote_exact": "…", "snippet": "…",
      "highlights": [{"start": 10, "end": 44}]
    }]
  }],
  "approximate": {"collapsed": true, "total_clauses": 7},
  "empty_reason": null
}
```

- `empty_reason`: `NO_AUTHORIZED_DOCUMENTS` · `NO_RESULTS` · `PHRASE_NOT_FOUND` (có thể kèm kết quả `all_terms`).
- Kết quả "gần đúng" (`any_term`) lấy bằng tham số riêng hoặc endpoint con (`/search/approximate`) để tải theo yêu cầu, không trộn vào trang kết quả chính.
- Lỗi chuẩn: `QUERY_TOO_LONG`, `TOO_MANY_TERMS`, `PAGE_TOO_DEEP`, `RATE_LIMITED`, `SEARCH_TIMEOUT`. Thông báo không lộ thông tin ngoài quyền.
- Khoản có `amendment_state` khác `active` luôn trả kèm nhãn; không bỏ khoản khỏi kết quả chỉ vì hiệu lực (trừ khi `only_active=true`).
- Mở PDF: dùng nguyên API trích dẫn và `viewer_url` hiện có.
- Code: schema mới trong `schemas.py`; route mới trong `user.py` (theo mẫu `require_user`/`get_pipeline`); service mới `backend/app/storage/search.py`; chạy lại `export_openapi.py` để cập nhật `openapi.json`.

---

## 7. Thiết kế UX/UI trang Tìm kiếm

Tuân thủ design system hiện có (Modern Enterprise / Evidence-First; Light; Navy + Blue + White + Slate; màu qua CSS variables, cấm HEX cứng; màu không là tín hiệu duy nhất).

### 7.1 Vị trí và điều hướng

- Mục **"Tìm kiếm văn bản"** trên thanh điều hướng User Portal, cạnh Hỏi đáp; đường dẫn riêng; trạng thái truy vấn nằm trong query string của URL để quay lại/làm mới không mất kết quả.
- Chat Agent: sau mỗi câu trả lời có nút **"Xem tất cả kết quả tìm kiếm"** mở trang này với truy vấn tương ứng; không đổi hành vi chat.

### 7.2 Bố cục

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ [Hỏi đáp] [Tìm kiếm văn bản]  …            [Danh mục ▼]  [API/Local Mode]  │ Navy
├────────────────────────────────────────────────────────────────────────────┤
│ Tìm kiếm văn bản                                                           │
│ ┌ Tìm theo từ khóa, cụm từ hoặc số hiệu văn bản… ───────────┐ [Tìm kiếm]   │
│ └────────────────────────────────────────────────────────────┘             │
│ [✓] Tìm chính xác cụm từ                                                   │
│ Lọc: [Danh mục ▼] [Loại văn bản ▼] [Cơ quan ▼] [Ngày áp dụng ▼]            │
│      [ ] Chỉ hiện quy định đang áp dụng                                    │
│ ────────────────────────────────────────────────────────────────────────── │
│ Có 5 khoản chứa đúng cụm từ “…” trong 3 văn bản.                           │
│                                                                            │
│ ▾ Nghị định 385/2026/NĐ-CP — Tên văn bản · Nghị định · Cơ quan             │
│   Liên kết trang công bố chính thức                    2 khoản khớp        │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │ Khoản 1 Điều 5 · Trang 12        [Đúng cụm từ] [Đang áp dụng]       │   │
│   │ “…các bộ, ngành thực hiện ▓báo cáo định kỳ và thường xuyên▓ …”     │   │
│   │ [Mở trang PDF nguồn]                                                │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│   ┌ Khoản 3 Điều 9 · Trang 20  [Đúng cụm từ] [Đã sửa đổi từ 01/07/2026] ┐   │
│   └─────────────────────────────────────────────────────────────────────┘  │
│ ▸ Thông tư …                                                               │
│                                                                            │
│ ‹ Trước   Trang 1 / 1   Sau ›                                              │
│ ▸ Kết quả gần đúng (7 khoản khớp một phần các từ)  — đang thu gọn          │
└────────────────────────────────────────────────────────────────────────────┘
```

- Kết quả **nhóm theo văn bản**; mỗi nhóm hiện số hiệu, tiêu đề, loại, cơ quan, link trang công bố chính thức (nếu đã xác minh) và số khoản khớp; mở rộng để xem các khoản (mặc định mở nhóm đầu).
- Mỗi khoản hiện nhãn khớp (`Đúng cụm từ`, `Cụm từ (không dấu)`, `Đủ các từ`) và **nhãn hiệu lực của chính khoản** (icon + chữ + ngày). `Đã sửa đổi`/`Đã bãi bỏ`/`Hiệu lực chưa xác minh` luôn hiện, không chỉ đổi màu.
- Snippet dùng `<mark>` với màu từ token highlight; chỉ tô khi backend trả `highlights`.
- Khi snapshot hiệu lực stale: dải cảnh báo đầu trang kết quả "Dữ liệu hiệu lực đang được cập nhật. Chưa thể khẳng định hiệu lực của các khoản bên dưới."
- Điện thoại: bộ lọc vào ngăn kéo; kết quả một cột; nút chạm ≥ 44×44px.

### 7.3 Trạng thái và nội dung giao diện

| Trạng thái | Nội dung |
|---|---|
| Placeholder | "Tìm theo từ khóa, cụm từ hoặc số hiệu văn bản…" |
| Nút | "Tìm kiếm"; ô tích "Tìm chính xác cụm từ" |
| Chưa nhập | Gợi ý cách tìm (ba ví dụ: từ khóa, cụm từ trong nháy kép, số hiệu); không dữ liệu giả |
| Đang tìm | Skeleton trung tính + "Đang tìm trong văn bản đã duyệt…" |
| Có kết quả cụm từ | "Có [N] khoản chứa đúng cụm từ “…” trong [M] văn bản." |
| Có kết quả từ khóa | "Tìm thấy [N] khoản trong [M] văn bản." |
| `PHRASE_NOT_FOUND` có kết quả đủ từ | "Không tìm thấy đúng cụm từ “…”. Dưới đây là các khoản có đủ các từ của cụm từ này." |
| `NO_RESULTS` | "Không có kết quả phù hợp. Thử bớt từ khóa hoặc bỏ tùy chọn tìm chính xác cụm từ." |
| `NO_AUTHORIZED_DOCUMENTS` | "Chưa tìm thấy tài liệu được phép truy cập." (đúng một thông điệp, không tiết lộ kho có hay không có văn bản) |
| Lỗi quá dài/nhiều từ | "Câu tìm kiếm quá dài. Rút gọn dưới [N] ký tự." / "Câu tìm kiếm có quá nhiều từ. Giữ tối đa [N] từ." |
| Tần suất | "Bạn tìm kiếm quá nhanh. Thử lại sau vài giây." |
| Quá hạn | "Tìm kiếm mất quá nhiều thời gian. Thu hẹp bộ lọc rồi thử lại." |
| Mất kết nối | "Mất kết nối tới máy chủ. Nội dung bạn nhập vẫn được giữ." + "Thử lại" |
| Nhãn khớp | "Đúng cụm từ" · "Cụm từ (không dấu)" · "Đủ các từ" · "Một phần" |
| Mở nguồn | "Mở trang PDF nguồn" |
| Mục gần đúng | "Kết quả gần đúng ([N] khoản khớp một phần các từ)" — thu gọn mặc định |

Cấm dùng: phần trăm "độ chính xác", "chắc chắn", "đã xác minh" cho kết quả tìm kiếm; "khớp cụm từ" cho kết quả túi từ.

### 7.4 Trợ năng và hiệu năng giao diện

- Ô tìm có nhãn; Enter gửi; không phím tắt toàn cục mới.
- Vùng kết quả có `aria-live="polite"` thông báo tổng số khi có kết quả mới; mỗi văn bản là một tiêu đề; nút mở rộng có `aria-expanded`; mục "Kết quả gần đúng" là vùng thu gọn có nhãn đếm.
- `prefers-reduced-motion` tắt hiệu ứng mở/đóng.
- Danh sách kết quả phân trang (không cuộn vô hạn); trang tìm kiếm tải lười; không tải tài nguyên ngoài ở Local Mode.
- Contrast test tự động cho nhãn khớp, nhãn hiệu lực và `<mark>`.

---

## 8. Kế hoạch work package

Thứ tự: SR-0 → (SR-1 ∥ SR-2) → SR-3 → (SR-4 ∥ SR-5) → (SR-6 ∥ SR-7) → SR-8. Ước lượng thô của bản phương án trước (khoảng 11–12 ngày công/1 dev; backend và frontend song song còn khoảng 8–9 ngày) **chưa được kiểm chứng**; chốt lịch sau SR-0.

| WP | Việc | Nghiệm thu |
|---|---|---|
| SR-0 | Đối chiếu hiện trạng với mã nguồn (mục 4): `authorized_search.py`, `0001_core.sql`, `fixed_pipeline.py`, `draft.py`, `citation-contract.md`; kiểm `text_indexed`/`text_folded`/`text_normalized` đã chuẩn hóa dấu thanh chưa; kiểm có Legal Reference Router trong mã không; kiểm module contrib trên PostgreSQL Windows đóng gói. Viết **characterization test cho chat** | Báo cáo hiện trạng (khớp/không khớp); ADR cho điểm khác; golden test chat xanh làm nền |
| SR-1 | Migration `0006` (index có dấu/không dấu), `.down.sql`, test up/down; `EXPLAIN` chứng minh index được dùng cùng semi-join ACL; quyết định `pg_trgm` bằng số đo; đánh dấu `normalization_revision` | Index được dùng trong `EXPLAIN` với ACL; migration up/down xanh; ADR về trigram và cách chống lệch revision |
| SR-2 | `SearchService`: phân tích truy vấn an toàn, chuẩn hóa dùng chung, T1–T4 với xác minh nguyên văn trên trường nội dung, offset map, xếp hạng, ACL, chọn version theo `as_of_date`, hiệu lực từng khoản, gộp văn bản, phân trang; refactor chat gọi `search_clauses` | Test từng tầng; golden test chat vẫn xanh; không còn đường ghép tsquery từ input |
| SR-3 | `GET /api/v1/search` (+ endpoint kết quả gần đúng), schema, OpenAPI, mã lỗi chuẩn, rate limit, timeout, audit không lưu truy vấn thô | OpenAPI cập nhật; test mã lỗi; audit đúng quy định mục 2 điểm 10 |
| SR-4 | Trang Tìm kiếm (mục 7): ô tìm, tích cụm từ, bộ lọc, nhóm văn bản, khoản khớp, snippet `<mark>`, nhãn hiệu lực, mục gần đúng, phân trang, trạng thái rỗng/lỗi, nút từ Chat Agent, mở PDF qua API trích dẫn | Test UI + a11y như các trang hiện có; snapshot ảnh nhãn khớp và nhãn hiệu lực; trạng thái rỗng đúng 3 trường hợp |
| SR-5 | Tích hợp hiệu lực: nhãn từng khoản từ snapshot, cảnh báo stale, công tắc "Chỉ đang áp dụng" | Test: khoản `modified/repealed/unknown` hiện nhãn đúng; snapshot stale ⇒ cảnh báo, không khẳng định hiệu lực |
| SR-6 | Bộ đánh giá: 30–50 truy vấn có đáp án kỳ vọng (văn bản + node) từ **văn bản thật đã duyệt**, gồm ca dương/âm/biến thể dấu/số hiệu; script tính metric; **người nắm nghiệp vụ duyệt đáp án kỳ vọng** | Báo cáo recall@k, precision@k, `exact_phrase_precision`, `wrong_doc_rate`, `wrong_node_rate`, đúng-khi-không-có-kết-quả, p50/p95; chỉ case đã duyệt tính vào chuẩn |
| SR-7 | Kiểm thử bảo mật và hiệu năng: rò rỉ ACL (kể cả tổng số, phân trang, trạng thái rỗng, lỗi), thu hồi quyền giữa chừng, input toán tử tsquery/SQL, escape LIKE, giới hạn độ dài/tần suất/timeout, benchmark p95 | Mọi test bảo mật xanh; số đo p95 ghi môi trường và quy mô dữ liệu |
| SR-8 | Tài liệu: ADR, runbook, thêm mục "Tìm kiếm văn bản" vào SRS v1.3, changelog; checklist tiền điều kiện dữ liệu (mục 10) | Tài liệu cập nhật; không còn điểm lệch giữa SRS và mã nguồn |

---

## 9. Tiêu chí nghiệm thu

**A. Kiểm tra cứng (phải đạt, không phải thống kê)**

| # | Kiểm tra |
|---|---|
| 1 | Cụm từ có trong 3 văn bản đã duyệt ⇒ trả đủ 3 văn bản ở trang 1 (khi không lọc) |
| 2 | Cụm từ không có trong kho ⇒ `phrase_found=false`, **không** kết quả nào gắn `exact_phrase`, có thông báo đúng |
| 3 | Kết quả chỉ khớp các từ rời ⇒ **không bao giờ** có nhãn "Đúng cụm từ" |
| 4 | Gõ không dấu / "kì–kỳ" / "hòa–hoà" vẫn tìm được bản có dấu; kết quả chỉ khớp ở kênh không dấu có nhãn `phrase_folded`, không phải `exact_phrase` |
| 5 | Cụm từ vắt qua ranh giới breadcrumb/tiêu đề và nội dung **không** được tính là `exact_phrase` |
| 6 | Tổng số văn bản/khoản và phân trang chính xác (`totals`, `has_more`); không vượt giới hạn độ sâu |
| 7 | ACL: thu hồi quyền ⇒ 0 kết quả, không lộ tên/nội dung, không lộ qua tổng số/phân trang/trạng thái rỗng/lỗi; chạy test PG integration (không được skip trong CI: `EVIDENCE_TEST_DATABASE_URL` phải được đặt) |
| 8 | Hiệu lực từng khoản đúng nhãn; snapshot stale ⇒ có cảnh báo; khoản hiệu lực chưa rõ ⇒ "Hiệu lực chưa xác minh" |
| 9 | Highlight đúng offset trên `text_original`; khi không chắc offset thì không tô |
| 10 | Mở PDF nguồn: đúng trang; kiểm ACL và hash như hiện nay; bản ghi trích dẫn tạo lười đúng cách |
| 11 | Input chứa toán tử/ký tự đặc biệt (`"` `-` `|` `&` `:*` `<->` `'` `%` `_`) không gây lỗi SQL/tsquery, không đổi nghĩa truy vấn ngoài ý muốn |
| 12 | Truy vấn quá dài/nhiều từ, vượt tần suất, quá thời gian ⇒ mã lỗi đúng, không treo |
| 13 | Không hồi quy chat: cùng đầu vào cho cùng 12 căn cứ, claims, SSE (golden test) |
| 14 | Local Mode: trang tìm kiếm không phát sinh request ra ngoài, không tải tài nguyên ngoài |
| 15 | Nhật ký kiểm toán không chứa nội dung truy vấn thô (trừ khi owner chốt chính sách khác) |

**B. Chỉ số đo (báo cáo, không tuyên bố đạt/đủ khi chưa có số)**

recall@k, precision@k, `exact_phrase_precision`, `wrong_doc_rate`, `wrong_node_rate`, đúng-khi-không-có-kết-quả, p50/p95 độ trễ. Mục tiêu độ trễ (ví dụ p95 ≤ 300 ms với khoảng 100k node trên máy dev) là **mục tiêu phải đo** trên máy Windows đích; nếu chưa có dữ liệu thật ở quy mô đó thì dùng dữ liệu sinh để thử tải và ghi rõ là dữ liệu tổng hợp. Bộ đánh giá phải độc lập với dữ liệu dùng chỉnh ngưỡng của chat/RAG.

---

## 10. Điều kiện tiên quyết về dữ liệu (rất quan trọng)

Theo mô tả hiện trạng: 0 văn bản approved, 0 provenance verified, 9/12 PDF thử nghiệm là bản scan cho 0 node nếu không OCR (`database-summary.json`, `implementation-status.md`). Nếu không giải quyết, trang tìm kiếm đúng code nhưng luôn rỗng.

| Việc | Ai làm | Ghi chú |
|---|---|---|
| Duyệt 3 văn bản đang `pending_review` hoặc nạp bộ văn bản thật | **Reviewer / người nắm nghiệp vụ** | AI không được tự duyệt |
| Xác minh provenance/span để citation mở được | Reviewer/curator | |
| OCR cho PDF scan | AI soạn **ADR** (engine, giấy phép, dung lượng trong trần 10 GB, chạy offline, không cài runtime mặc định) → owner duyệt → triển khai như plugin ngoại lệ | Văn bản từ OCR chỉ thành căn cứ sau khi reviewer duyệt; gắn `extraction_method=ocr`; kiểm `text_quality` |
| Cung cấp số văn bản đã duyệt hiện có và mốc thời gian mong muốn | **Owner** | Chốt lịch sau SR-0 |

Trong lúc chờ dữ liệu thật, AI được phép phát triển và chạy test bằng fixture **gắn nhãn "HƯ CẤU"**, tách khỏi corpus đánh giá; số đo chất lượng chỉ tính trên văn bản thật đã duyệt.

---

## 11. Mặc định agent dùng nếu chưa có chỉ đạo (owner đổi được)

| Vấn đề | Mặc định |
|---|---|
| Độ dài truy vấn tối đa / số từ tối đa | 500 ký tự / 20 từ |
| `page_size` mặc định / tối đa | 20 / 50 |
| Số khoản khớp hiển thị mỗi văn bản | 5 (có nút xem thêm) |
| Giới hạn độ sâu phân trang | 1000 kết quả |
| `statement_timeout` cho search | cấu hình được; đề xuất vài giây, chốt bằng số đo |
| Tần suất tối đa mỗi người dùng | cấu hình được; đề xuất giới hạn theo phút |
| Khoản đã sửa đổi/bãi bỏ | Hiện kèm nhãn; công tắc "Chỉ hiện quy định đang áp dụng" mặc định tắt |
| Index trigram | Không thêm cho tới khi đo chứng minh cần |
| Lưu nội dung truy vấn thô | Không; chỉ băm + độ dài + bộ lọc + số kết quả |
| Nhiều cụm từ trong một truy vấn | P1; Search v1 hỗ trợ một cụm trong nháy kép + từ khóa rời |
| Kích thước bộ đánh giá | 30–50 truy vấn |

---

## 12. Mẫu báo cáo cuối mỗi WP (bắt buộc)

```text
WP: <id> — <tên>
Trạng thái: Xong / Xong một phần / Bị chặn
Đã làm: <danh sách ngắn>
Test: <tên test + kết quả thật, số pass/fail>
Số đo: <nếu có; ghi môi trường, phiên bản, quy mô dữ liệu>
Quyết định/ADR mới: <id>
CHƯA XONG / bị hoãn: <liệt kê rõ, kèm lý do>
Rủi ro / cần người quyết: <nếu có>
```

Phần "CHƯA XONG" không được để trống bằng cách lược bỏ; không đổi tiêu chí nghiệm thu để test xanh.

---

## 13. Rủi ro chính

| Rủi ro | Cách xử lý |
|---|---|
| Planner bỏ index GIN khi kết hợp view ACL | SR-1 kiểm `EXPLAIN`; phương án thay: tính trước tập `document_id` được phép, CTE `MATERIALIZED`; ghi số đo |
| Lệch chuẩn hóa giữa index và truy vấn ⇒ không tìm thấy dù có | Một hàm chuẩn hóa dùng chung; test hòa/hoà, NFC/NFD; `normalization_revision` + kiểm lúc khởi động |
| Gắn nhầm nhãn "đúng cụm từ" cho kết quả không liền kề hoặc vắt qua breadcrumb | Bước xác minh nguyên văn trên trường nội dung; kiểm tra cứng #3 và #5 |
| Lộ sự tồn tại tài liệu qua tổng số/rỗng/lỗi | Tính trên tập được phép; một thông điệp rỗng; test rò rỉ có cả đếm và phân trang |
| Refactor làm hỏng chat | Golden test trước khi refactor (SR-0); tham số mới mặc định giữ hành vi cũ |
| Dữ liệu rỗng làm mọi demo thất bại | Mục 10; fixture "HƯ CẤU" để dev, văn bản thật đã duyệt để đo |
| OCR kéo dependency/dung lượng nặng | ADR riêng, plugin ngoại lệ, duyệt trước khi bật |
| Chỉ số "đúng/đủ" bị tuyên bố sớm | Chỉ báo khi có Gold [Không triển khai – xem ADR-010] tìm kiếm đã duyệt; mọi số ghi môi trường |
| Truy vấn nặng làm chậm hệ thống | Timeout, giới hạn tần suất, giới hạn độ sâu, đo p95 |

---

## 14. Mở rộng sau (phương án B) — không làm trong Search v1

Khi đã có model chạy local và Gold [Không triển khai – xem ADR-010] đã duyệt: thêm `lexical_search_index` có revision, tokenizer tiếng Việt (Underthesea/PyVi theo SRS v1.3), embedding qua Model Registry (mở rộng registry cho model loại embedding), RRF + pre-gate + rerank, định tuyến văn bản trước node. Mọi bước sau cờ tính năng, chỉ bật khi benchmark không thoái lui; giao diện kênh và hàm hợp nhất ở mục 5.4 đã chừa chỗ để không đổi API và giao diện trang tìm kiếm.

---

## 15. Prompt giao cho AI triển khai

> Bạn là coding agent triển khai **Search v1** cho Vietnamese Evidence RAG Agent, tích hợp vào app hiện có dưới dạng module riêng (trang Tìm kiếm trong User Portal, `SearchService` dùng chung với chat). Đọc kỹ file kế hoạch này và `SRS_v1.3.md`; kế hoạch này thắng bản phương án trước ở những điểm mục 2. Bắt đầu bằng SR-0: đối chiếu hiện trạng với mã nguồn thật và viết golden test cho chat trước khi refactor. Giữ tương thích ngược nghiêm ngặt: tham số mới mặc định giữ hành vi cũ, chat không đổi. Làm tự chủ; dùng mặc định ở mục 11 khi chưa có chỉ đạo và ghi ADR; chỉ dừng chờ người ở nghiệp vụ, quyền truy cập, bảo mật, độ đúng của căn cứ. Không ghép tsquery từ input người dùng; chỉ gắn nhãn "đúng cụm từ" sau khi xác minh nguyên văn trên trường nội dung; hiệu lực tính theo từng khoản; trạng thái rỗng không được lộ sự tồn tại tài liệu; không tự duyệt văn bản và không tự công nhận đáp án đánh giá; không tuyên bố số liệu chưa đo; fixture phải gắn nhãn "HƯ CẤU". Kết thúc mỗi WP báo cáo theo mẫu mục 12 và nêu rõ phần chưa xong.

---

## 16. Việc cần owner

1. Cung cấp **số văn bản đã duyệt hiện có và mốc thời gian mong muốn** (mục 10).
2. Chỉ định reviewer/người nắm nghiệp vụ duyệt 3 văn bản đang `pending_review` và duyệt đáp án kỳ vọng của bộ đánh giá SR-6.
3. Duyệt ADR OCR (engine, giấy phép, dung lượng) nếu muốn xử lý PDF scan.
4. Xác nhận các mặc định ở mục 11, đặc biệt: khoản đã sửa đổi/bãi bỏ hiện kèm nhãn hay mặc định ẩn; có lưu nội dung truy vấn thô hay không.
5. Cung cấp máy Windows đích để đo p95 và dung lượng index.
