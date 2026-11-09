# Đánh giá Search v1 — bộ case HƯ CẤU và harness đo chỉ số

> ⚠️ **HƯ CẤU** — Toàn bộ case trong thư mục này dùng **số hiệu/định danh văn bản, node và nội dung hư cấu** (`HU-CAU/2026/ND-CP`, `HC-ND-CP-N01`, …), **không phải văn bản pháp luật** và **không phải Gold**. Tất cả case đang có `approved_by = null`; vì vậy `evaluate_search.py` chỉ báo `hucau_metrics` và ghi `quality_status = "not_evaluated"`. Không được dùng số liệu trong report để tuyên bố chất lượng tìm kiếm.

## Mục đích

Chuẩn bị hạ tầng đo các chỉ số ở **mục 9-B** của [`docs/KE_HOACH_TRIEN_KHAI_TIM_KIEM_V1_Evidence_RAG.md`](../../docs/KE_HOACH_TRIEN_KHAI_TIM_KIEM_V1_Evidence_RAG.md) cho endpoint `GET /api/v1/search`:

- recall@k (mức văn bản), precision@k (mức khoản), `exact_phrase_precision`, `wrong_doc_rate`, `wrong_node_rate`, đúng-khi-không-có-kết-quả, p50/p95 độ trễ.
- Kiểm tra công thức/metric trên response giả lập để CI không phụ thuộc backend.
- Sẵn sàng nhận Gold thật: chỉ case `approved_by != null` mới được tính vào `official_metrics`.

Bối cảnh dữ liệu (mục 10 kế hoạch): hiện **0 văn bản approved**, 0 case Gold được người nắm nghiệp vụ duyệt. Vì vậy bộ này **chưa** đo chất lượng thật; nó chỉ chứng minh harness/metric chạy đúng.

## Thành phần

| File | Vai trò |
|---|---|
| `queries_hucau.json` | 12 case HƯ CẤU: cụm từ chính xác có/không, từ khóa đủ từ, gõ không dấu, biến thể kì/kỳ, hòa/hoà, số hiệu văn bản, ca âm (`expected_no_result`), nhiều văn bản, bộ lọc. |
| `schema.json` | JSON Schema (draft 2020-12) cho file queries. |
| `fixtures/sample_responses.json` | Response giả lập + giá trị metric kỳ vọng cho `--self-test` và `self_test.py`. Không phải response API thật. |
| `self_test.py` | 21 test stdlib `unittest`: công thức metric, schema/queries, percentile, URL, mock HTTP server end-to-end, exit code. |
| `reports/` | Nơi ghi `report.json` + `report.md` mặc định của `evaluate_search.py` (file sinh ra, có thể xoá/tạo lại). |
| `../scripts/evaluate_search.py` | Harness gọi API, đo latency, tính metric, xuất report. |

## Schema case

File queries là JSON object: `schema_version = 1`, `label = "HU_CAU"`, `description`, `corpus = "HU_CAU"`, `cases[]`. Mỗi case:

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `id` | string, duy nhất | Mã case, dùng trong report. |
| `query` | string | Truy vấn gửi API. |
| `mode` | `auto` \| `phrase` \| `keywords` | Tham số `mode`. |
| `filters` | object | `category_id` (mảng string), `doc_type`, `issuing_body`, `as_of_date` (YYYY-MM-DD), `only_active` (bool), `group_by` (`document`). Bỏ trống nếu không lọc. |
| `expected_documents` | string[] | Số hiệu văn bản kỳ vọng (khớp `document_number` API trả về). Rỗng ⇔ `expected_no_result = true`. |
| `expected_nodes` | string[] | Node kỳ vọng; chấp nhận **`node_id` hoặc nhãn** (`label`) vì Gold thật có thể chưa có UUID. |
| `expected_no_result` | bool | `true` khi kỳ vọng API không trả kết quả. |
| `notes` | string | Ghi chú của case. |
| `approved_by` | string \| null | `null` = chưa được người nắm nghiệp vụ duyệt → **chỉ** vào `hucau_metrics`. |
| `corpus` | string | `"HU_CAU"` cho fixture hư cấu. |

`validate_queries()` trong harness kiểm tra tối thiểu: trường bắt buộc, `mode`, khóa `filters`, định dạng ngày, `expected_no_result` nhất quán với `expected_documents`, `id` không trùng, `approved_by` null/không rỗng, `corpus = HU_CAU`. `self_test.py` còn đối chiếu danh sách trường bắt buộc giữa `schema.json` và code.

## Công thức chỉ số

Với `k` = `--k` (mặc định 10) văn bản đầu trong `results`:

- **recall@k (document)** = `|expected_documents ∩ returned_documents[:k]| / |expected_documents|`. Case âm (không có văn bản kỳ vọng) không có recall → `null`, bị loại khỏi trung bình.
- **precision@k (clause)** = số clause thuộc `expected_documents` **hoặc** `expected_nodes` / tổng clause trả về trong `results[:k]`. Không có clause nào → `null`.
- **exact_phrase_precision** (định nghĩa owner chốt — tự xác minh, không tin nhãn):
  - Tử số = số clause được backend gắn `match_type = "exact_phrase"` mà `quote_exact` **thực sự chứa cụm từ** sau khi chuẩn hóa NFC + lowercase + coi mọi ký tự không phải chữ/số là phân tách + so khớp các từ liền nhau.
  - Mẫu số = tổng số clause được gắn `exact_phrase` trong `results[:k]` (khớp phạm vi các chỉ số clause khác).
  - Cụm từ dùng để đối chiếu = `query.phrase` trong response nếu có, ngược lại là `case.query`.
  - Ca âm (`expected_no_result = true`) luôn cho **0.0**, kể cả khi quote có chứa cụm từ và mẫu số > 0 (không được coi là 1.0).
  - Mẫu số = 0: case dương → **`null`** (loại khỏi trung bình, không coi là 1.0); ca âm → **0.0**.
  - `expected_documents`/`expected_nodes` **không** tham gia vào `exact_phrase_precision`; chỉ dùng cho recall/precision/wrong rate.
  - Report ghi kèm `exact_phrase_returned` (mẫu số), `exact_phrase_verified` (tử số thô), `exact_phrase_phrase`; aggregate có `exact_phrase_cases_scored`, `exact_phrase_cases_null`, `exact_phrase_negative_cases`, `exact_phrase_total_labeled`, `exact_phrase_total_verified`.
- **wrong_doc_rate** = văn bản trả về không nằm trong `expected_documents` / tổng văn bản trả về (trong `results[:k]`).
- **wrong_node_rate** = clause không khớp cả `expected_documents` lẫn `expected_nodes` / tổng clause trả về (bù của precision@k).
- **no-result correctness** = với case `expected_no_result`, đúng khi `results` rỗng **và** `empty_reason ∈ {NO_AUTHORIZED_DOCUMENTS, NO_RESULTS, PHRASE_NOT_FOUND}`.
- **p50/p95** = trung vị và nearest-rank trên latency của các request **thành công** (HTTP 200, JSON hợp lệ), đơn vị ms.
- Trung bình của các chỉ số (trừ p50/p95) là trung bình theo **từng case** đã chạy được; case lỗi HTTP/timeout bị loại khỏi tử số/mẫu số và được đếm riêng ở `cases_error`.
- Chia case: `approved_by != null` → `official_metrics`; `approved_by = null` → `hucau_metrics`. Không có case approved ⇒ `official_metrics = null`, `quality_status = "not_evaluated"`. Khi có case approved, `quality_status = "measured_on_approved_cases"` (số liệu vẫn phải báo kèm môi trường/quy mô, không tự kết luận "đạt").

## Cách chạy

Dùng Python backend venv (stdlib, không cài thêm gì):

```powershell
$py = 'E:\Programs\EvidenceRAG\backend-venv\Scripts\python.exe'

# 1) Test công thức/schema/mock HTTP (không cần API, không cần token)
& $py E:\Source\Evidence_RAG_Handoff\evaluation\search_eval\self_test.py

# 2) Tự kiểm tra công thức ngay trong harness (cùng fixture)
& $py E:\Source\Evidence_RAG_Handoff\evaluation\scripts\evaluate_search.py --self-test

# 3) Xem trợ giúp
& $py E:\Source\Evidence_RAG_Handoff\evaluation\scripts\evaluate_search.py --help

# 4) Chạy với API (khi backend đã có GET /api/v1/search và có token USER)
$env:EVIDENCE_ACCESS_TOKEN = '<token>'
& $py E:\Source\Evidence_RAG_Handoff\evaluation\scripts\evaluate_search.py `
    --base-url http://127.0.0.1:8000 `
    --queries E:\Source\Evidence_RAG_Handoff\evaluation\search_eval\queries_hucau.json `
    --output E:\Source\Evidence_RAG_Handoff\evaluation\search_eval\reports
```

Tham số chính: `--base-url` (mặc định `http://127.0.0.1:8000`), `--token` hoặc `--token-env` (mặc định `EVIDENCE_ACCESS_TOKEN`), `--queries`, `--k` (10), `--page-size` (50, tối đa theo contract), `--output` (thư mục), `--timeout` (giây), `--self-test`, `--fixtures`.

Report sinh ra:

- `report.json`: môi trường (OS, Python, base_url, thời gian), `queries_sha256`, quy mô bộ case, `quality_status`, `official_metrics`, `hucau_metrics`, chi tiết từng case (metric, latency, response summary/lỗi), ghi chú HƯ CẤU.
- `report.md`: bảng chỉ số + bảng từng case + cảnh báo HƯ CẤU/`not_evaluated`.

Exit code:

| Mã | Khi nào |
|---|---|
| `0` | Chạy xong và đã ghi report (kể cả metric xấu); `--self-test` pass. |
| `1` | `--self-test` fail (sai công thức/fixtures). |
| `2` | Lỗi cấu hình/token (thiếu token, token bị 401/403, `--k`/`--page-size`/`--timeout` sai, queries không hợp lệ) hoặc API không chạy/không trả response hợp lệ nào; **không ghi report**. |

## Quy trình khi có Gold thật

1. Người nắm nghiệp vụ duyệt từng case và **chỉ khi đó** điền `approved_by` (tên/ID người duyệt) — AI không được tự điền.
2. Case Gold thật phải dùng corpus/văn bản đã approved, **không** trộn với file `queries_hucau.json`. Tạo file queries riêng (ví dụ `queries_gold_v1.json`) có `label`/`corpus` tương ứng; nếu cần chạy corpus khác, cập nhật hằng số `CORPUS_LABEL`/`LABEL` trong harness theo ADR/quyết định của owner (hiện chỉ hỗ trợ nhãn `HU_CAU`).
3. Khoá `split_revision` trước khi tune, không tune trên held-out rồi báo lại là đánh giá độc lập ([`docs/history/eval-gold-protocol.md`](../../docs/history/eval-gold-protocol.md)).
4. Chạy harness trên file Gold; báo `official_metrics` kèm môi trường, phiên bản, quy mô dữ liệu và số case duyệt. Không tuyên bố "đúng/đủ" khi chưa có Gold duyệt.

## Giới hạn / chưa làm

- **Chưa chạy end-to-end với API thật**: backend chưa có route `GET /api/v1/search` tại thời điểm viết; chưa có token USER để gọi. Toàn bộ test hiện dùng response giả lập.
- **Chưa có Gold thật**: 0 case `approved_by != null`; mọi report sẽ là `quality_status = "not_evaluated"`, `official_metrics = null`.
- Chưa kiểm tra các "kiểm tra cứng" mục 9-A (ACL, nhãn hiệu lực, highlight offset, giới hạn phân trang, ký tự đặc biệt, lỗi chuẩn) — các mục này cần test backend/API riêng.
- Chưa đo tải/p95 trên máy Windows đích với ~100k node; p95 hiện chỉ là latency của request trong lần chạy thực tế.
- Metric `exact_phrase_precision` dùng định nghĩa owner (tự xác minh quote, ca âm = 0, case dương mẫu số 0 = null); khi có Gold người duyệt xác nhận lại quy ước này. Hiện chưa có Gold thật nên chưa có số liệu official.
- Tự xác minh `exact_phrase` chỉ kiểm tra quote có chứa cụm từ; chưa kiểm tra cụm từ vắt qua ranh giới breadcrumb/tiêu đề (mục 9-A #5) — cần test backend/API riêng.
- Fixture hư cấu không kiểm chứng nội dung pháp lý, không dùng làm bằng chứng trích dẫn.
