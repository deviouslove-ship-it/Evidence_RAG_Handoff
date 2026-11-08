# Báo cáo triển khai Search v1 — 31/10/2026

Kế hoạch nguồn: `KE_HOACH_TRIEN_KHAI_TIM_KIEM_V1_Evidence_RAG.md`
(bản owner chốt; các điểm chỉnh so với phương án trước ở mục 2 của kế hoạch).

## 1. Tóm tắt trung thực

- Đã triển khai **module Search v1** trên PostgreSQL: migration index, `SearchService`,
  API `GET /api/v1/search` + `/api/v1/search/approximate`, trang Tìm kiếm trong User Portal,
  bộ test backend/frontend, harness đánh giá (fixture HƯ CẤU).
- **Chưa nghiệm thu chất lượng**: 0 văn bản approved trong DB dev, 0 case Gold được người
  nắm nghiệp vụ duyệt, chưa đo recall/precision/p95 trên dữ liệu thật. Mọi kết quả test
  dưới đây là **test kỹ thuật trên fixture HƯ CẤU**, không phải số liệu chất lượng.
- Chat giữ nguyên hành vi cũ: golden test xanh (12 căn cứ, 8 claims, 3 suggestions,
  `answer_generated=false`, chuỗi 6 SSE event).

## 2. Trạng thái work package

| WP | Trạng thái | Bằng chứng / ghi chú |
|---|---|---|
| SR-0 | Xong | Đối chiếu hiện trạng; ADR-005 mục 2; golden test chat 5 test xanh |
| SR-1 | Xong | `0006_search_index.sql` + `.down.sql`; up trên DB dev; up/down trong test PG; `EXPLAIN` trong test xác nhận `document_nodes_search_word_gin` được dùng |
| SR-2 | Xong | `storage/search.py`: parse an toàn, T1–T4, xác minh phrase trên nội dung, ACL bằng allowed doc ids, version theo `as_of_date`, hiệu lực từng khoản, gộp văn bản, phân trang; chat delegate legacy khi không quote |
| SR-3 | Xong (thiếu HTTP server thật) | Route + schema + OpenAPI + mã lỗi + rate limit + timeout + audit hash-only; E2E API chạy qua ASGI (`httpx.ASGITransport`), chưa chạy uvicorn/browser |
| SR-4 | Xong một phần | `SearchPage.tsx` + nav + nút từ chat; 52 test frontend xanh; build/lint xanh. Chưa browser E2E, chưa test contrast/snapshot ảnh, chưa có “xem thêm khoản khớp” |
| SR-5 | Xong một phần | Backend trả `amendment_state` từng khoản + `effectivity_snapshot_status`; test PG có `modified` + `unknown`, stale trước khi có snapshot. UI nhãn hiệu lực chỉ test bằng mock; chưa có snapshot builder thật |
| SR-6 | Xong một phần | `evaluation/search_eval/` + `evaluation/scripts/evaluate_search.py`; 12 case HƯ CẤU; self-test 22 test + 47 value check + 4 latency check. **Chưa có Gold thật**, `official_metrics=null`, `quality_status=not_evaluated` |
| SR-7 | Xong một phần | Test ACL (khác principal ⇒ 0 kết quả), input ký tự đặc biệt, giới hạn độ dài/số từ/page/rate, map timeout; **chưa đo p95/tải**, chưa bắt gói Local Mode |
| SR-8 | Xong một phần | ADR-005, runbook, báo cáo này, mục SRS §26, cập nhật implementation-status; chưa có changelog file riêng (dự án không có CHANGELOG) |

## 3. Kiểm chứng kỹ thuật (số liệu thật, 31/10/2026)

Môi trường: Windows, Python 3.11.15 (venv `E:\Programs\EvidenceRAG\backend-venv`),
PostgreSQL 18.6 local (port 55432), Node bó sẵn của repo, vitest 2.1.3.

### Full verification (12/12)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1 `
  -ProgramsRoot E:\Programs `
  -OutputDirectory .\docs\evidence\2026-10-31-search-v1\verification
```

Kết quả: **12/12 check exit 0** (dependency-check, backend-lint, backend-typing,
backend-tests, source-policy, migration-pairs, openapi, polarity-fixtures,
temporal-fixtures, frontend-lint, frontend-tests, frontend-build). Log và
`summary.json` nằm trong `docs/evidence/2026-10-31-search-v1/verification/`.
Backend không có DSN: **171 passed, 16 skipped** (các test PG bị skip); có DSN:
**187 passed**.

### Backend

```powershell
$env:EVIDENCE_TEST_DATABASE_URL = "postgresql://...:55432/postgres"
python -m pytest backend/tests -q
```

Kết quả: **187 passed, 0 failed, 1 warning** (chạy 25,38 s), bao gồm test PG integration.
Test mới: **26** (`test_search_parser.py`, `test_search_api.py`, `test_search_postgres.py`,
`test_chat_characterization.py`).

Các kiểm tra đáng chú ý trong `test_search_postgres.py` (schema tạm, fixture HƯ CẤU):

1. Cụm từ trong **2 văn bản** ⇒ trả đủ 2 văn bản, mọi clause là `exact_phrase`;
   `phrase_found=true`.
2. Cụm từ không tồn tại ⇒ `phrase_found=false`, `empty_reason=PHRASE_NOT_FOUND`,
   không clause nào là `exact_phrase`.
3. Từ rời đủ mặt ⇒ chỉ `all_terms`, không gắn “đúng cụm từ”.
4. Gõ không dấu (`bao cao dinh ky va thuong xuyen`) ⇒ khớp kênh folded, nhãn
   `phrase_folded`, `phrase_found=false`; gõ `kì` thay `kỳ` vẫn trả `exact_phrase` cho bản
   có dấu (chuẩn hóa `kì→kỳ`, revision `vietnamese-tone-v3`).
5. Cụm từ nối qua **biên breadcrumb/title và nội dung** (chỉ khớp trong `text_indexed`)
   ⇒ **không** được gắn `exact_phrase` (tài liệu boundary không nằm trong kết quả phrase).
6. Phân trang: `page_size=1`, `totals.documents=2`, trang 1 `has_more=true`,
   trang 2 `has_more=false`.
7. ACL: principal không có `category_acl` ⇒ 0 kết quả,
   `empty_reason=NO_AUTHORIZED_DOCUMENTS`.
8. Hiệu lực: trước snapshot active ⇒ `effectivity_snapshot_status="stale"`; sau khi tạo
   snapshot active + interval cho một khoản ⇒ status `ok`, khoản đó `modified`, khoản
   không có interval `unknown`.
9. Highlight: `highlights` là offset tuyệt đối trên `quote_exact`; mọi range cắt ra
   chứa “báo cáo định kỳ”.
10. API E2E trong cùng event loop (`httpx.ASGITransport`): JSON trả đúng contract,
    `viewer_url` dạng `/api/v1/citations/ev_<uuid>/pdf?as_of_date=...`,
    `source_hash` có mặt.
11. Migration `0006` up/down trong schema tạm: index bị drop đúng.
12. `EXPLAIN` với `enable_seqscan=off` có `document_nodes_search_word_gin`.

### Frontend

```powershell
pnpm run test   # 14 files, 65 passed, 0 failed
pnpm run build  # tsc --noEmit + vite build OK; JS 252.12 kB (gzip 76.80), CSS 33.25 kB (gzip 6.25)
pnpm run lint   # eslint --max-warnings=0 OK
```

14 test mới: `SearchPage.test.tsx` (12), `App.search.test.tsx` (1),
`EvidenceChat.searchLink.test.tsx` (1). Test cũ vẫn xanh, gồm `PdfViewer` 3 test (chat
không đổi hành vi).

### OpenAPI

```powershell
python scripts/export_openapi.py
python scripts/export_openapi.py --check
```

Kết quả: export và check OK; `docs/openapi.json` có `/api/v1/search` và
`/api/v1/search/approximate`.

### Bộ đánh giá

```powershell
python evaluation/search_eval/self_test.py       # 22 test OK
python evaluation/scripts/evaluate_search.py --self-test
# {"self_test":"pass","label":"HU_CAU","cases_checked":6,"value_checks":47,"latency_checks":4,"failures":[]}
```

Chưa chạy được end-to-end với API HTTP thật vì (a) chưa có văn bản approved, (b) chưa có
token USER trong môi trường test. Harness đã sẵn `--base-url`/`--token-env` để chạy khi có
hai điều kiện đó.

### Dữ liệu dev hiện tại

Probe `SearchService` trên DB dev (`postgres`) với câu
`"báo cáo định kỳ và thường xuyên"`:

```json
{ "phrase_found": false, "totals": {"documents": 0, "clauses": 0,
  "approximate_matches_hidden": 0}, "effectivity_snapshot_status": "stale",
  "results": [], "empty_reason": "NO_AUTHORIZED_DOCUMENTS" }
```

Đây là hành vi đúng theo thiết kế với 0 node approved/0 provenance verified, **không phải**
bằng chứng search chạy đúng trên dữ liệu thật.

## 4. Đối chiếu tiêu chí nghiệm thu (kế hoạch mục 9-A)

| # | Tiêu chí | Trạng thái | Ghi chú |
|---|---|---|---|
| 1 | Cụm từ trong 3 văn bản approved ⇒ trả đủ 3 | Một phần | Test fixture dùng 2 văn bản exact + 1 boundary; chưa có 3 văn bản thật approved để chứng minh |
| 2 | Cụm từ không có ⇒ `phrase_found=false`, không nhãn exact, thông báo đúng | Đạt (fixture) | Test PG |
| 3 | Chỉ khớp từ rời ⇒ không nhãn “Đúng cụm từ” | Đạt (fixture) | Test PG + UI mock |
| 4 | Không dấu / kì–kỳ / hòa–hoà tìm được bản có dấu; nhãn `phrase_folded` | Đạt một phần | Không dấu + kì/kỳ: test PG; hòa/hoà: unit test chuẩn hóa; chưa có test PG cho hòa/hoà |
| 5 | Cụm từ vắt qua breadcrumb/title và nội dung không được tính exact | Đạt (fixture) | Test PG `boundary` |
| 6 | Tổng số/phân trang chính xác, giới hạn độ sâu | Đạt (fixture) | Test PG; API service test PAGE_TOO_DEEP |
| 7 | ACL: thu hồi quyền ⇒ 0 kết quả, không lộ qua tổng số/rỗng/lỗi | Đạt một phần | Test PG khác principal + API rate; chưa test thu hồi giữa chừng và rò rỉ qua lỗi/timing |
| 8 | Hiệu lực từng khoản đúng nhãn; stale có cảnh báo; unknown hiện “chưa xác minh” | Đạt một phần | Backend test `modified`/`unknown`/stale; UI nhãn chỉ test mock |
| 9 | Highlight đúng offset trên `text_original`; không chắc thì không tô | Đạt (fixture) | Unit + PG; frontend test clamp/không tô |
| 10 | Mở PDF đúng trang, kiểm ACL/hash, trích dẫn lười | Đạt một phần | `viewer_url` đúng contract + citation test cũ; chưa mở PDF thật từ search vì fixture không có file PDF trong document store |
| 11 | Input ký tự đặc biệt không lỗi/không đổi nghĩa | Đạt (fixture) | Parser + PG `báo "cáo - | & :* <-> ' % _` |
| 12 | Quá dài/nhiều từ/vượt tần suất/quá thời gian ⇒ mã lỗi đúng | Đạt một phần | Độ dài/từ/page/rate: test thật; timeout: map lỗi bằng fake, chưa tạo timeout DB thật |
| 13 | Không hồi quy chat | Đạt | Golden test 5 test + toàn bộ test cũ |
| 14 | Local Mode không request ra ngoài | Chưa kiểm bằng bằng chứng | Chỉ rà code; chưa bắt gói |
| 15 | Audit không lưu nội dung truy vấn thô | Đạt theo code | Metadata chỉ có SHA-256/độ dài/bộ lọc/số kết quả; chưa có test tự động |

## 5. Chỉ số đo (kế hoạch mục 9-B)

**Chưa có.** Không báo recall@k, precision@k, `exact_phrase_precision`,
`wrong_doc_rate`, `wrong_node_rate`, no-result, p50/p95 vì chưa có Gold thật và chưa có
văn bản approved. Eval harness đã sẵn sàng; khi có Gold, chạy:

```powershell
python evaluation/scripts/evaluate_search.py `
  --base-url http://127.0.0.1:8000 `
  --token-env EVIDENCE_ACCESS_TOKEN `
  --queries evaluation/search_eval/queries_gold.json `
  --output evaluation/search_eval/reports
```

## 6. File thay đổi chính

Backend:
- `backend/app/storage/search.py` (mới)
- `backend/app/schemas.py` (thêm schema Search)
- `backend/app/api/v1/user.py` (2 route)
- `backend/app/api/v1/errors.py` (mã lỗi)
- `backend/app/main.py` (wiring service/rate)
- `backend/app/config.py` (3 cấu hình search)
- `backend/app/migrations/0006_search_index.sql` + `.down.sql` (mới)
- `backend/tests/test_search_parser.py`, `test_search_api.py`, `test_search_postgres.py`,
  `test_chat_characterization.py` (mới); `test_auth_and_admin_portal.py` (cập nhật danh sách migration)

Frontend:
- `frontend/src/pages/SearchPage.tsx` + test (mới)
- `frontend/src/App.tsx`, `types.ts`, `api/client.ts`, `components/PdfViewer.tsx`,
  `pages/EvidenceChat.tsx`, `styles.css`, `App.search.test.tsx`,
  `pages/EvidenceChat.searchLink.test.tsx`

Evaluation:
- `evaluation/search_eval/` (README, schema, 12 case HƯ CẤU, fixture, self-test)
- `evaluation/scripts/evaluate_search.py`

Tài liệu:
- `docs/architecture-decisions/ADR-005-search-v1.md` (mới)
- `docs/search-v1-runbook.md` (mới)
- `docs/evidence/2026-10-31-search-v1/REPORT.md` (file này)
- `docs/SRS_v1.3.md` (§26), `docs/implementation-status.md`, `docs/openapi.json`

## 7. Việc còn lại / bị chặn

1. **Dữ liệu**: reviewer duyệt 3 văn bản `pending_review` (hoặc nạp corpus thật) + xác minh
   provenance/span. Không có bước này, Search luôn trả `NO_AUTHORIZED_DOCUMENTS`.
2. **Gold search**: người nắm nghiệp vụ duyệt 30–50 case; sau đó mới chạy metric chính thức.
3. **Đo p50/p95** trên máy Windows đích/quy mô ~100k node; hiện chỉ có test chức năng.
4. **PDF highlight (bbox/quads)** và OCR: WP riêng, chưa làm.
5. **“Xem thêm khoản khớp”** trong từng văn bản: cần bổ sung tham số API nếu muốn.
6. **Browser E2E + contrast/a11y tự động + bắt gói Local Mode**: chưa có dependency/phương
   tiện trong môi trường hiện tại.
7. **Quyết định owner**: quy ước exact_phrase_precision cho ca không có exact phrase,
   ngưỡng p95, câu chữ PAGE_TOO_DEEP, chuẩn hóa `doc_type`, OCR ADR.

## 8. Cập nhật đợt 2 — 31/10/2026 (theo góp ý owner)

### 8.1. Reindex/normalization (SR-0/SR-1 bổ sung)

- Migration `0007_normalization_revision.sql`: thêm `document_nodes.normalization_revision`;
  dữ liệu cũ gán `vietnamese-tone-v2`, dữ liệu mới ghi `vietnamese-tone-v3` (có cặp `kì→kỳ`).
- Backend kiểm tra lúc khởi động; `/api/v1/system/mode` trả
  `search_normalization_status` (`current|stale|unavailable`), revision và số node stale.
- `scripts/backfill_search_normalization.py` (dry-run + batch) tính lại
  `text_normalized`/`text_folded`, không đổi `text_original`/`text_indexed`.
  Đã chạy trên DB dev: **648 node v2 → 0 stale** (log `normalization-backfill.log`).
- Test PG mới: node giả lập v2 (`định kì`, folded `dinh ki`) không khớp trước backfill;
  sau backfill khớp `phrase_folded` (không gắn `exact_phrase`). Nếu đổi revision mà không
  backfill, status stale được báo thay vì im lặng.

### 8.2. Benchmark dữ liệu sinh 100.000 node

Script `scripts/benchmark_search.py` (HƯ CẤU; 1.000 văn bản × 100 node; có page/span/
provenance/category ACL giả; không đặt `enable_seqscan=off`). Planner mặc định:
`enable_seqscan=on`, `random_page_cost=4`, `work_mem=4MB`, JIT on. EXPLAIN ANALYZE:
plan có `document_nodes_search_word_gin`; execution 66–423 ms tùy lần.

| Truy vấn | p50 | p95 |
|---|---:|---:|
| Phrase `"báo cáo định kỳ và thường xuyên"` | 243,62 ms | **324,31 ms** |
| Keyword `báo cáo định kỳ` | 255,57 ms | 268,95 ms |
| Không kết quả | 62,61 ms | 62,61 ms |
| API default (có approximate cap) | — | 338,66 ms (một lần) |

Mục tiêu tạm p95 300 ms: phrase **vượt 24,31 ms**, keyword đạt; chỉ chốt sau khi đo trên
máy Windows đích. Chi tiết plan/config: `benchmark/benchmark.json`, `benchmark/benchmark.md`.
Tối ưu kèm theo: đọc ACL theo document (không scan 100k node mỗi request); bỏ count all-terms
khi phrase tier đã có; giới hạn approximate count 500 và chỉ tính khi cần (trước đó API
default mất 42 s ở 100k node, nay ~0,34 s).

### 8.3. Phân trang khoản khớp

- API thêm `clause_page`, `clause_page_size` (max 50) và field
  `clause_page`/`clause_page_size`/`has_more_clauses` mỗi document.
- UI hiển thị “Hiển thị X/Y khoản” và nút “Xem thêm khoản khớp”; client cộng dồn theo
  `node_id` vì API trả offset window. Giới hạn: reload URL `clause_page>1` chỉ tải đúng
  trang khoản hiện tại, không dựng lại buffer các trang trước.

### 8.4. A11y/contrast/Local Mode/browser E2E/CI

- Frontend: **65 test/14 file**, build + lint xanh. Thêm:
  - a11y: role/label, `aria-live="polite"` vùng kết quả, `aria-expanded`/`aria-controls`,
    heading theo văn bản.
  - contrast: đọc token thật từ `tokens.css`/`styles.css`, tính WCAG; thấp nhất **5,21:1**
    (`<mark>` 14,26:1), tất cả ≥ 4,5:1.
  - Local Mode: mọi fetch là `/api/v1/...`, không host ngoài; `dist/index.html` không tài
    nguyên ngoài.
  - Browser E2E: Chrome 156 headless qua CDP + fixture API cùng origin (không dependency mới);
    đăng nhập → search phrase → badge/mark/stale → clause_page=2 → approximate lazy → PDF
    iframe; **10–12 request, 0 external http(s) origin**. Harness nằm trong repo tại
    `frontend/e2e/search.e2e.mjs` (+ README), chạy `pnpm run e2e:search` với `CHROME_PATH`.
    Đây **chưa** phải backend thật +
    dữ liệu approved.
- CI: workflow đặt `EVIDENCE_TEST_DATABASE_URL` từ secret và `CI=true`; `verify.ps1` +
  `backend/tests/conftest.py` dừng nếu thiếu DSN, không để test PG bị skip. Browser E2E
  chưa vào CI vì cần Chrome runner ổn định.

### 8.5. Mặc định chờ owner (đã áp dụng tạm)

- `PAGE_TOO_DEEP`: “Bạn đã xem tới giới hạn kết quả. Hãy thu hẹp bằng bộ lọc hoặc dùng từ
  khóa cụ thể hơn.” (backend + frontend).
- `doc_type`: danh mục có kiểm soát do curator quản lý; UI tạm dùng
  `decree/circular/decision/other`; dữ liệu free-text cũ cần chuẩn hóa.
- `exact_phrase_precision`: tử số là khoản gắn exact_phrase thực sự chứa cụm từ / tổng số
  khoản gắn exact_phrase; ca âm = 0; mẫu số 0 ở case dương = null; harness self-test 27 test.
- p95 tạm 300 ms trên 100k node sinh; chốt sau máy đích.
- Rate limit hiện chỉ đúng một process; đa worker cần store chia sẻ.

### 8.6. Kiểm chứng lại

- Backend: **187 passed** với PostgreSQL (sau migration 0007 và các thay đổi); 171 passed
  + 16 skipped khi không DSN.
- Frontend: 65 passed; build/lint xanh.
- Eval: self-test 27 test, `--self-test` 8 case/75 value check/4 latency check; vẫn
  `quality_status=not_evaluated` (0 Gold, 0 approved).
- `scripts/verify.ps1`: **12/12 check exit 0** (log mới trong
  `docs/evidence/2026-10-31-search-v1/verification/`).

### 8.7. Chưa xong

- Gold thật + duyệt văn bản/provenance; chưa đo recall/precision/p95 chất lượng.
- PDF bbox highlight, OCR; browser E2E backend thật; CI browser runner.
- Reload `clause_page>1` chưa dựng lại buffer; chưa có test reset clause_page khi đổi filter.
- `doc_type` free-text chưa được chuẩn hóa; rate limit đa worker chưa làm.