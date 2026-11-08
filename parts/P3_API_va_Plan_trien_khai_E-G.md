---

## E. Hợp đồng API bổ sung

SRS §11 giữ nguyên các API gốc (`/query/analyze`, `/query/requery`, `/query/evidence`, `/citations/*`, `/feedback`, `/admin/*`). Endpoint `/query/evidence` đảm nhiệm trả về căn cứ, nhóm căn cứ, nhận định và gợi ý tham khảo; `/query/answer` và `/analysis/situation` ảo trước đây đã được loại bỏ; luồng streaming hai pha hoàn chỉnh chạy qua `/agent/sessions/{id}/turns`. Dưới đây là **API bổ sung bắt buộc ở mức hành vi**; agent chốt schema OpenAPI đầu Sprint 1 và đối soát với SRS v1.3. Mọi endpoint kiểm ACL phía server; **không có endpoint nào cho phép Agent ghi dữ liệu nghiệp vụ**.

| Nhóm | Endpoint đề xuất | Mục đích |
|---|---|---|
| Phiên Chat Agent | `POST /api/v1/agent/sessions` (có cờ `incognito`) · `GET /api/v1/agent/sessions/{id}` · `DELETE /api/v1/agent/sessions/{id}` | Tạo, đọc trạng thái (facts, phạm vi, revision), xóa phiên |
| Lượt hội thoại | `POST /api/v1/agent/sessions/{id}/turns` (SSE) | Gửi lượt; dùng chung hợp đồng SSE hai pha |
| Điều khiển lượt | `POST /api/v1/agent/sessions/{id}/turns/{turn_id}/cancel` · `…/retry` · `GET …/{turn_id}/events?run_id=…` | Dừng, thử lại có chủ ý, nối lại event stream theo run |
| Bộ nhớ | `GET /api/v1/memory` · `DELETE /api/v1/memory/{item_id}` · `DELETE /api/v1/memory` · `GET/PUT /api/v1/memory/preferences` | Xem, xóa từng mục/toàn bộ, đọc và lưu sở thích tra cứu danh mục mặc định (opt-in) |
| Phân tích & Gợi ý | Tích hợp trong `POST /api/v1/query/evidence` và SSE `/turns` · `POST /api/v1/query/followups` (A2) | Phân tích tình huống có cấu trúc (A1); gợi ý câu hỏi tiếp theo (đã dry-run và khử trùng lặp với claims). Đã loại bỏ endpoint mock `/analysis/situation`. |
| Nguồn và so sánh | `GET /api/v1/nodes/{id}/notes` (A4) · `GET /api/v1/nodes/{id}/diff?as_of=…` (A5) · `GET /api/v1/nodes/{id}/related` (A6) | Điểm cần lưu ý, so sánh phiên bản, văn bản liên quan |
| Đề xuất AI cho curator | `GET /api/v1/admin/ai-suggestions` · `POST /api/v1/admin/ai-suggestions/{id}/accept` · `…/reject` · `…/edit` | Hàng đợi đề xuất; chấp nhận là hành động của curator, có audit |
| Domain nguồn | `GET/POST /api/v1/admin/source-domains` · `PATCH /api/v1/admin/source-domains/{id}` | Quản lý allowlist |
| Bộ kiểm thử | `GET /api/v1/admin/evaluation/cases` · `POST /api/v1/admin/evaluation/cases/{id}/review` · `GET /api/v1/admin/evaluation/splits` | Duyệt Gold/trap set; xem tách calibration/held-out |
| Theo dõi (P1) | `POST /api/v1/watches` · `GET /api/v1/notifications` | A9 |

**Sự kiện SSE bổ sung:** `retrieval_started`, `evidence_verified`, `evidence_complete`, `analysis_ready`, `answer_complete`, `explanation_unavailable`, `understood_as`, `clarify_needed`, `analysis_item`, `followup_suggestions`, `memory_state_changed`, `turn_cancelled` và `turn_error` (kèm mã lỗi: `SESSION_EXPIRED`, `MEMORY_CAPACITY_EXCEEDED`, `QUERY_FAILED`). Bổ sung vào danh sách event gốc ở SRS §11.4; frontend không tự đoán tiến trình.

**Hợp đồng chung phải đưa vào OpenAPI đầu Sprint 1**

- Scope: `scope_mode=SELECTED|ALL_AUTHORIZED`; SELECTED cần category IDs được cấp; ALL_AUTHORIZED do server giải lại theo quyền hiện tại mỗi run. Quyền tra cứu là quyền riêng, không suy từ vai trò SYS_ADMIN.
- Session thuộc một principal; tạo phiên mặc định `incognito=true`. Chỉ cho `incognito=false` khi có retention policy được duyệt và opt-in; nếu chưa đủ trả `RETENTION_NOT_APPROVED`, không âm thầm ghi. Response nêu `persistence_state=ephemeral|retained`, `expires_at` và các revision; không chứa secret. Incognito dùng RAM như C.4; cache HTTP nhạy cảm đặt no-store, không lưu câu hỏi/token vào local storage.
- POST turn/retry nhận idempotency key; server cấp `turn_id`/`query_id`/`run_id`. Retry giữ một message user, tạo run mới và ngân sách mới có rate limit; response/event ghi rõ run đang có hiệu lực. Cancel chỉ dừng lượt do chính user sở hữu, không gọi tool nghiệp vụ.
- Mỗi event có `query_id`, `run_id`, `facts_revision`, `snapshot_revision`, `event_sequence`. Snapshot có thể null trước khi pin; từ khi có evidence phải dùng cùng snapshot trong run. SSE ID là tổ hợp query/run/sequence; Last-Event-ID nối lại đúng run, không tự tạo generation mới. Client chỉ nhận run hiện hành, bỏ event trùng/cũ, không ghép claims hai run. Reconnect phải xác thực lại và kiểm ACL/policy trước khi phát lại; incognito chỉ replay phần còn trong RAM, hết TTL/restart trả `SESSION_EXPIRED`.
- DELETE memory/session xóa dữ liệu vận hành và vô hiệu dẫn xuất/cache/job theo C.4; audit/sổ yêu cầu xóa chỉ metadata cần thiết. Không trả nội dung/tên phiên của người khác. Xóa không làm mất nguồn PDF đã duyệt hoặc audit nghiệp vụ có chính sách giữ riêng.
- Checklist dùng enum `passed/failed/unknown` và tên chuẩn D.7; schema nhận định phân biệt conditional/needs_review/blocked. Không stream raw claim chưa validate; không coi pass kiểm số/phủ định là chứng minh ngữ nghĩa.
- **Bảo mật CORS:** Header định danh phát triển `X-Principal-Id` và `X-Roles` bị loại bỏ hoàn toàn khỏi cấu hình CORS khi chạy tiêu chuẩn hoặc production; chỉ mở khi bật cờ POC `DEV_ALLOW_IN_MEMORY_STORE=true` để ngăn chặn client giả mạo quyền hạn.
- **Model Registry & Runtime:** `is_safe_endpoint` cho phép loopback/localhost (`127.0.0.1`, `localhost`, `::1`) khi `EVIDENCE_ALLOW_LOCAL_AI=true` cho Ollama/vLLM; lọc danh sách đen biến môi trường nhạy cảm (`_SECRET_DENIED`) đối với `secret_ref`; bóc tách tự động thẻ suy luận (`<think>...</think>`) và markdown fences cho reasoning models; giới hạn timeout AI selection ở mức 70% query timeout và graceful degradation về fixed pipeline khi model phản hồi chậm.

| Thao tác | Quyền/chủ thể bắt buộc | Hệ quả được phép |
|---|---|---|
| Query, session, history, memory, cancel/retry | USER/quyền rag.query + owner của phiên + scope ACL | Ghi trạng thái kỹ thuật khi có chính sách; không ghi nghiệp vụ |
| Upload/import, sửa node, accept/edit/reject đề xuất AI | CURATOR + scope tài liệu | Chỉ tạo/sửa draft; accept không publish |
| Approve tài liệu/version/amendment/hiệu lực | REVIEWER + scope + If-Match | Ghi approved revision rồi build/publish snapshot nguyên tử |
| Cấu hình account/role/provider/route/domain | SYS_ADMIN + quyền cấu hình tương ứng | Audit; không cấp quyền đọc nội dung theo mặc định |
| Duyệt Gold/trap | REVIEWER/chuyên gia được chỉ định | Chỉ xác nhận case đã đọc nguồn; không cấp quyền tune held-out |
| Đọc audit | AUDITOR + audit scope | Đọc metadata/bằng chứng trong quyền, không sửa |

Role không tự suy ra từ tiền tố `/admin`. Với CURATOR-only, gọi approve phải bị từ chối và snapshot không đổi; tài khoản nhiều role chỉ có quyền đã được cấp tường minh. Các service ghi session/audit không trở thành tool cho LLM tự gọi.

---

## F. Plan triển khai chi tiết

### F.1 Cách đọc plan

- Mỗi sprint có **work package (WP)**: việc · đầu ra · nghiệm thu; kết thúc bằng một **gate**. Chỉ công nhận gate sau khi tiền đề đã đạt; có thể làm trước việc độc lập nhưng phải báo gate còn thiếu, không đổi mock hoặc trạng thái suy giảm thành nghiệm thu đầy đủ.
- Plan **không ước lượng thời gian**: SRS không cam kết và tốc độ phụ thuộc kết quả POC. Owner đặt lịch sau Sprint 0.
- Mã tính năng (Q, V, G, M, A, C, K, R, Z) tham chiếu mục C; mã màn hình (S1–S14) tham chiếu mục D.
- Mặc định kỹ thuật ở B.6; bất biến ở B.3.

### F.2 Tóm tắt sprint và gate

| Sprint | Mục tiêu | Gate |
|---|---|---|
| 0 | POC trên Windows thật: pgvector, PDF anchor, model, Local Mode offline, ADR-000/001/002 | ADR chốt; SRS v1.3; footprint đo thật; pgvector, backup/restore, dịch vụ Windows chạy được trên máy đích |
| 1 | Kho tài liệu, hiệu lực node, ERD (kể cả bộ nhớ), frontend nền, Gold v0 | Import → parse → review → approve → snapshot chạy trên PDF thật; resolver qua đủ ca; Gold v0 (150–200 câu) được người nắm nghiệp vụ duyệt; tokens + contrast test xanh |
| 2 | Retrieval, evidence-first, chống truy xuất sai, A4–A6, baseline hiệu năng | BFS 2-hop vs full-chain; pre-gate 3 trạng thái; stale snapshot; B0–B7 có số đo thật; `wrong_doc_rate`/`wrong_node_rate`; baseline hiệu năng; C1 tầng quy tắc |
| 3 | Model Router, Local/API Mode, claims, UI hai pha, Chat Agent, bộ nhớ, phân tích và gợi ý P0 | Hai chế độ API/Local chạy được (Local kiểm trên máy ngắt Internet thật); regression polarity/numeric/temporal xanh; widget, bộ nhớ, trap set đạt ngưỡng owner chốt; A1–A3 |
| 4 | Hardening, hiệu năng, đóng gói Windows, P1 owner chọn | Red-team (bộ nhớ, prompt injection, rò rỉ ACL); hồi quy hiệu năng; restore thành công trên máy sạch; footprint trong trần demo |

### F.3 Quyết định mặc định

Dùng bảng B.6. Agent không dừng chờ các điểm đó; ghi ADR khi chọn khác.

### F.4 Luồng làm việc và phụ thuộc

Bảy luồng: **A** DB/ACL/hiệu lực · **B** Ingestion/Parsing · **C** Retrieval/Eval · **D** Validator/Workflow · **E** Model Router · **F** Frontend · **G** Nền tảng/CI.

- Sprint 0 kiểm khả thi trên Windows và các cấu hình đại diện; POC chọn thư viện/runtime tương thích, không cố định provider/model. Profile B chỉ chứng minh lõi offline; các gate AI/local model còn thiếu phải được báo riêng.
- A (schema) chặn B, C, D. B (nodes + span) chặn C và hiển thị viewer. Resolver hiệu lực (A) chặn validator hiệu lực (D).
- Gold v0 (C) chạy song song từ đầu Sprint 1 nhưng cần PDF thật từ Sprint 0 và người duyệt.
- F bắt đầu design tokens, viewer, split-view khi OpenAPI/schema ổn định (cuối Sprint 1); trước đó dùng mock server.
- E (router) độc lập retrieval; chỉ cần schema `providers/model_profiles/stage_routes`.
- Widget và desktop USER (WP 3.9) cần SSE contract có run_id (WP 3.4), EvidenceCards (WP 2.9), auth/ACL và POC shell ở WP 0.5. Frontend/native không tạo workflow/backend riêng.
- Một chủ trì chịu trách nhiệm cho mỗi WP: backend/dữ liệu chủ trì 4.8 (red-team, phối hợp retrieval và frontend); retrieval/eval chủ trì 4.9 (P1 owner chọn, phối hợp backend/frontend). Phần UI của WP backend do frontend đóng góp; không coi giao diện là người sở hữu thứ hai thay cho chủ trì.

### F.5 Sprint 0 — POC trên Windows thật

| WP | Việc | Đầu ra | Nghiệm thu |
|---|---|---|---|
| 0.0 | Đưa hồ sơ 1.1, SRS v1.3 và ADR-000 đã có vào các đường dẫn repo quy định; giữ v1.2.1 làm lịch sử; rà ma trận B.7 | Bộ tài liệu hiện hành liên kết đúng | Không viết lại đặc tả hoặc chọn lại các quyết định đã chốt; không coi việc có tài liệu là đã hoàn thành các WP kỹ thuật |
| 0.1 | Khung repo theo §17 SRS; CI (ưu tiên runner Windows): lint, typing, unit, migration check, secret scan, SBOM; `dependency-manifest` (license, version, SHA-256, footprint); khai báo deployment profile installation.programs_root / EVIDENCE_PROGRAMS_ROOT và dependency-manifest theo B.8 | Repo + CI | CI xanh trên repo rỗng; source/script không hardcode PATH/LLM; root cài được đọc từ cấu hình, inventory ghi relative/real path |
| 0.2 | PostgreSQL + pgvector **trên Windows**: cài bằng bản được duyệt, cấu hình, chạy như dịch vụ Windows; đo hiệu năng truy vấn exact; backup và restore; API và worker chạy như dịch vụ Windows; cài PostgreSQL/pgvector và service wrapper dưới root cài công cụ theo B.8 | ADR-001 (cách cài và vận hành trên Windows) + script cài | `CREATE EXTENSION vector` và truy vấn `<=>` exact chạy trên máy Windows đích; cài sạch tái lập được; backup rồi restore ra máy sạch thành công; dịch vụ tự khởi động lại sau lỗi. Nếu pgvector lỗi: ADR đề xuất cách khắc phục trên Windows (bản build, cách biên dịch), chưa đổi kiến trúc; binary/helper resolve qua manifest dưới root; không dùng PostgreSQL global ngoài manifest, không hardcode executable path |
| 0.3 | POC PDF native trên 10–20 PDF thật: nhiều cấp điều khoản, file đời cũ/TCVN3, scan, xoay ngang, CropBox. So pypdfium2/pdfplumber | `pdf-anchor-coordinate-contract.md` + báo cáo | Highlight đúng với nhiều dòng, rotation, CropBox; mapping không chắc ⇒ fallback trang + quote; ghi tỷ lệ đúng trên từng file |
| 0.4 | POC NLP/model cấu hình được: Underthesea; embedding/reranker ONNX không PyTorch nếu tương thích; LLM API hoặc runtime local theo Registry, không hardcode model/provider/endpoint; kiểm license, prefix, hash và trust_remote_code policy; cài runtime/tool và model/package cache dưới root đã cấu hình theo B.8 | ADR-002 + footprint-report + cấu hình thử đã che secret | Kiểm từng capability/định dạng/runtime; GGUF hoặc định dạng LLM local đã kiểm chứng được phép. Thiếu model/key ghi MODEL_NOT_CONFIGURED hoặc capability chưa kiểm; không giả lập AI và không yêu cầu một model cố định; POC không dùng tool/model store ngoài manifest hoặc PATH global; model/provider vẫn đổi bằng cấu hình |
| 0.5 | E2E mỏng: auth, SQL ACL, upload một PDF + SHA-256, viewer byte gốc, FakeAdapter; POC shell desktop USER login → Orb → panel → thu/mở, tray, DPI và vùng hit-test; verify-egress; shell/helper/runtime chỉ dùng thành phần đã cài dưới root B.8 | Skeleton chung backend + báo cáo shell | User không quyền không thấy tài liệu; không nền vuông/bóng dư/vùng kéo đè chữ; không console. FakeAdapter chỉ test hợp đồng, không tính là AI thật; khởi động từ shortcut/service không nhờ PATH global hoặc tool trong thư mục source |
| 0.6 | POC parser tham chiếu pháp lý (`Điều X khoản Y điểm Z`, số hiệu) + chuỗi A→B→C trên PDF thật | Báo cáo + test mẫu | Parse đúng tập mẫu; ca mơ hồ trả "không chắc", không đoán |
| 0.7 | POC Local Mode khi ngắt Internet thật: đăng nhập, PDF, lexical/extractive; thêm embedding/rerank/LLM theo từng capability local được cấu hình; egress guard + rule firewall mẫu; kiểm inventory runtime/tool/model store local dưới root B.8 | verify-egress + ma trận capability đã kiểm/chưa kiểm và cấu hình không secret | Không DNS/HTTP ra Internet; endpoint LAN nội bộ chỉ theo allowlist. Profile B được nghiệm thu khả thi lõi offline với giới hạn công khai; thiếu dense/rerank/generation không được ghi đã kiểm những stage đó, không thay gate AI S3; thiếu root/dependency báo lỗi, không fallback sang vị trí khác hoặc tự tải/cài online |

**Gate S0:** ADR-000/001/002, SRS v1.3, footprint và pgvector/backup/restore/dịch vụ Windows có bằng chứng trên máy đích; POC shell USER có báo cáo; PDF và hash trong `evaluation/corpus_public_real`. Có thể đạt phần khả thi lõi theo profile B khi model chưa sẵn sàng, nhưng báo riêng các capability AI chưa kiểm và không công nhận chúng đã đạt. Lỗi nền tảng ⇒ ghi ADR phương án phù hợp Windows; không đổi yêu cầu hoặc hạ gate AI S3.

### F.6 Sprint 1 — Kho tài liệu, hiệu lực node, Gold v0

**Luồng A/B (nền dữ liệu)**

| WP | Việc | Nghiệm thu |
|---|---|---|
| 1.1 | AI tự thiết kế toàn bộ ERD (bảng, quan hệ, khóa ngoại, ràng buộc, lịch sử phiên bản) và tạo migration + test DB theo §10 SRS; tự kiểm tra nhất quán, toàn vẹn, phân quyền. Gồm principal/ACL, categories, documents/versions, `source_provenance`, pages/spans, nodes, references, amendments, reviews, snapshots, jobs, audit. **Bổ sung** FK, RLS hoặc security view, exclusion/check cho interval, `unresolved_targets`, audit append-only. Sửa DDL minh họa: `evidence_groups.query_id` và `citation_id` phải có FK thật | Migration up/down có test; test ACL không lọt; không copy DDL minh họa làm production; test riêng cho quan hệ hiệu lực, sửa đổi, bổ sung, bãi bỏ đến từng Điều/Khoản/Điểm và lịch sử phiên bản; ERD kèm báo cáo tự kiểm tra, chỉ trình owner các nguyên tắc nghiệp vụ quan trọng |
| 1.2 | Auth RBAC+ABAC; Category CRUD: tạo/sửa/ẩn/xóa mềm/khôi phục, cây độ sâu cấu hình, chống vòng, N–N, import/export JSON/CSV có kiểm tra | SYS_ADMIN không đọc nội dung mặc định; xóa mềm không xóa file gốc; không lộ tài liệu mất quyền |
| 1.3 | Ingestion nguồn (mặc định chặn URL tùy ý; bảng `domain_allowlist` do admin thêm/sửa/vô hiệu trong giao diện sau khi xác minh, mọi thay đổi có audit; upload PDF từ máy hỗ trợ đơn lẻ hoặc chọn nhiều tệp theo lô tuần tự kèm metadata độc lập và xử lý trùng lặp 2 tầng byte SHA-256 + content fingerprint NFC; chỉ tài liệu `approved` vào kho; domain hợp lệ không đồng nghĩa còn hiệu lực): `import-url` (DNS pin/recheck, chặn private/local, giới hạn redirect/size), `upload` (magic bytes, quota, SHA-256), bản bất biến, provenance | Test SSRF, redirect ra mạng nội bộ, file giả MIME; hash đổi tại cùng URL ⇒ version mới chờ duyệt; URL ngoài allowlist bị chặn; domain bị vô hiệu thì import dừng; trùng byte chặn 409, trùng nội dung cảnh báo draft; file lỗi cấu trúc/hash/metadata không thể thành approved |
| 1.4 | Job queue: `SKIP LOCKED`, lease, heartbeat, retry cap, cancel, idempotency key, backpressure | Hai worker không parse trùng một version; cancel dừng đúng; lỗi được redact |
| 1.5 | Parse native từng trang; chẩn đoán (ký tự `�`, tỷ lệ âm tiết hợp lệ, độ phủ text, thứ tự đọc); nhận diện TCVN3/VNI + chuyển mã có hồi kiểm; trạng thái `needs_ocr` + interface OCR plugin (không cài runtime); `extraction_method` từng trang | Trang lỗi **không bao giờ** thành quote verified; trang scan đi `needs_ocr` |
| 1.6 | Tree parser: Chương/Mục/Điều/Khoản/Điểm/Phụ lục; văn bản không cấu trúc theo heading/trang (không bịa Điều/Khoản); `text_indexed` có breadcrumb; applicability header; `node_references` giải khi ingest, unresolved được flag; `parse_confidence`; hàng đợi review ưu tiên rủi ro | Test trên PDF thật: nhảy khoản, tham chiếu "khoản 1 Điều này", văn bản công văn không có Điều |
| 1.7 | **Hiệu lực:** `node_amendments` (CURATOR lập nháp, REVIEWER duyệt), amendment-chain resolver chạy đến fixed point (phát hiện cycle/đứt/chồng chéo/xung đột, resource guard fail-closed, không rò văn bản ngoài ACL), snapshot staged → atomic publish theo `snapshot_revision`, `source_review_revision`, stale fail-closed, hook invalidate cache, audit | Test: A→B→C→D vượt 2 hops vẫn đúng; cycle/thiếu cạnh/xung đột ⇒ `temporal_unknown`; worker lỗi ⇒ `SNAPSHOT_STALE`; rollback khi cutover lỗi |
| 1.10 | ERD bộ nhớ: phiên, trạng thái, tóm tắt, bộ nhớ người dùng, retrieval hints, bản đồ văn bản; ràng buộc xóa thật và retention | Test ACL, xóa, hết hạn; không có đường nào biến bộ nhớ thành citation |

**Luồng F (frontend nền)**

| WP | Việc | Nghiệm thu |
|---|---|---|
| 1.8 | Module design tokens theo D.2 (kể cả token bổ sung); contrast test tự động WCAG 2.2 AA; lint cấm HEX cứng; `PdfViewer` (byte gốc, anchor, fallback trung thực); `AmendmentBanner` hai vị trí (toolbar + sát highlight); `CuratorSplitView` (autosave draft ≠ Approve, `If-Match`, phím tắt không duyệt khi đang nhập, xác nhận khi sửa hiệu lực/hàng loạt); `CategoryAdmin`; `CuratorQueue`; màn hình Domain cho phép (S8); mock server từ OpenAPI | Snapshot ảnh cho `active/modified/repealed/suspended/not_yet_effective/unknown`; bàn phím + screen reader; banner có nhãn chữ + icon, không chỉ màu |

**Luồng C (đánh giá)**

| WP | Việc | Nghiệm thu |
|---|---|---|
| 1.9 | **Gold v0 150–200 câu** (thay chỉ tiêu 50–100) từ PDF văn bản chính thức thật. Agent tự đọc PDF, soạn câu hỏi, đáp án tham chiếu và căn cứ; mỗi câu có số hiệu văn bản, điều/khoản/điểm, đoạn trích, phiên bản, thời điểm áp dụng khi liên quan, source URL/hash. Phủ: hỏi trực tiếp, tình huống nhiều điều kiện, ngoại lệ, văn bản sửa đổi (kể cả chuỗi A→B→C→D), chuyển tiếp, văn bản bãi bỏ, không đủ căn cứ, ngoài ACL, lời thường, không dấu, số hiệu viết tắt, PDF font lỗi. Agent tự kiểm cấu trúc, trích dẫn (quote khớp `text_original`) và phát hiện trùng lặp. Tách calibration và held-out theo scenario_group_id; các câu diễn đạt lại/cùng tình huống không chia sang hai tập; tỷ lệ đề xuất khoảng 30/70 là theo số case nhưng không phá nhóm. Regression vận hành tách khỏi held-out; manifest/corpus/split revision được khóa trước tuning. Màn hình duyệt S11 | Mỗi case có trạng thái draft → reviewed bởi người nắm nghiệp vụ; **chỉ case đã duyệt được dùng làm chuẩn**; AI không tự công nhận đáp án; báo cáo trùng lặp và kiểm trích dẫn đạt trên mọi case; script kiểm case ID, scenario_group_id, paraphrase/tình huống gần trùng giữa calibration và held-out; freeze split_revision trước tuning; corpus tách khỏi kho nghiệp vụ; fixture UI ở `synthetic_ui_fixtures` |

**Gate S1:** import → parse → review → approve → snapshot chạy thông trên PDF thật; resolver qua đủ ca ở WP 1.7; Gold v0 (150–200 câu) đã được người nắm nghiệp vụ duyệt; tokens + contrast test xanh.

### F.7 Sprint 2 — Retrieval và Evidence-first

| WP | Việc | Nghiệm thu |
|---|---|---|
| 2.1 | `vietnamese_nlp`: NFC + bảng mapping dấu thanh (`hòa/hoà`, `thúy/thuý`) kiểm 2 chiều và versioned, `đ→d` riêng, offset map về original, canonical hóa số hiệu (giữ giá trị gốc + khóa chuẩn), alias dictionary do curator quản lý | Test 2 chiều; `text_original` không bao giờ bị sửa |
| 2.2 | Lexical: `L1_WORD` (Underthesea, fixed words), `L2_SYLLABLE` (uni/bigram), `text_folded` trọng số thấp; FTS `tsvector` + `setweight` A/B/C, GIN; ACL trong SQL; lưu tokenizer/index revision. **Không gọi `ts_rank` là BM25** | `EXPLAIN ANALYZE` có dùng index; test ACL không rò qua tokenizer |
| 2.3 | Deterministic Legal Reference Router (B0): chỉ bypass Analyze khi match **duy nhất + approved + ACL + as_of_date** | Test đúng/sai/trùng/mơ hồ số hiệu và Điều/Khoản/Điểm; mơ hồ ⇒ quay về Analyze |
| 2.4 | Dense: `EmbeddingAdapter`, `embedding_indices` + `node_embeddings` có revision riêng, exact `<=>` trên `authorized_nodes`; đổi model ⇒ index mới song song rồi cutover; contextual prefix sau flag OFF | Không trộn vector khác model; test model switch; HNSW chỉ POC ACL-filtered recall, mặc định tắt |
| 2.5 | Fusion: RRF; Grouped RRF theo aspect (`required` thiếu ⇒ `uncovered`); pre-gate 3 nhánh calibrate theo model/category/query type trên tập calibration (không đụng held-out); conditional rerank top-12 với window giữ phủ định/ngoại lệ/chuyển tiếp | Test false refusal, no-answer, cosine thấp nhưng nguồn đúng không bị loại sớm; không dùng RRF làm ngưỡng |
| 2.6 | Mở rộng ngữ cảnh: auto-merge khi ≥2 khoản cùng Điều; bounded BFS `max_hops=2` (visited, `max_expanded_nodes/tokens`, deadline, ACL + time filter **mỗi bước**, `partial_graph`); mở ngoài danh mục chỉ khi policy cho phép và hiển thị rõ | Test cycle, depth, token cap, cross-scope; hết budget ⇒ `coverage.partial_graph=true` |
| 2.7 | Evidence: `citation_records`, quote hydrator, citation validator (ACL ở retrieval/generate/mở citation; span đúng version/node/trang/hash), numeric/date/period validator, Polarity & Modality validator (cho phép tương đương đã test, `không quá ≈ tối đa`), claim schema §6.2, allowlist `evidence_ids` | Test `15→30 ngày`, `không quá↔ít nhất`, `có thể↔phải`, bỏ `trừ trường hợp`; đo false positive; không tuyên bố validator bảo đảm đúng tuyệt đối |
| 2.8 | Benchmark B0–B7 + ablation trên calibration/regression; pin corpus, split, model/tokenizer/prompt/config revision, giao thức và candidate trước đánh giá chốt | Báo khoảng tin cậy, missed-exception, false abstention, over-expansion và ACL leakage; held-out chỉ chạy đợt chốt theo protocol, không tune sau khi nhìn kết quả rồi báo cùng tập là độc lập |
| 2.9 | API `/query/evidence`, `/citations/*`; `EvidenceCards`, `NodeToc`, click mở đúng PDF/version/anchor, feedback 4 loại vào hàng chờ curator | Click đúng trang; banner đúng node/`as_of_date`; link tới văn bản sửa đổi đã duyệt |
| 2.10 | Dịch vụ phiên + viết lại câu nối tiếp + hiển thị "Đang hiểu là" + hỏi lại một câu | Câu nối tiếp trỏ đúng đối tượng; thiếu điều kiện ⇒ hỏi lại, không đoán |
| 2.11 | Định tuyến văn bản, lọc metadata, khử trùng phiên bản, `retrieval_diagnostics` (L0–L2) | Đo `wrong_doc_rate`/`wrong_node_rate` trên Gold; có ablation |
| 2.12 | Retrieval hints do curator duyệt + alias expansion có audit | Gợi ý chưa duyệt không ảnh hưởng xếp hạng |
| 2.13 | Baseline hiệu năng, tính trước lúc index, connection pool | Báo cáo P50/P95 theo stage trên máy đích |
| 2.14 | Quy tắc điểm cần lưu ý (A4), diff xác định (A5), đồ thị liên quan (A6) | Test trên PDF thật; diff khớp text đã duyệt; A6 không lộ node ngoài ACL |
| 2.15 | Bộ phát hiện đề xuất cho curator tầng quy tắc: quan hệ sửa đổi, tham chiếu chưa giải, node bất thường (C1 a, b, d) | Precision/recall trên tập nhãn lấy từ PDF thật, curator duyệt tập nhãn |

**Gate S2 (release-gate, không phải P1):** BFS 2-hop vs full-chain resolver; pre-gate 3 trạng thái; snapshot stale + worker lỗi; Gold v0 chạy B0–B7 (chỉ case đã duyệt; đánh giá cuối trên held-out) có số đo thật; baseline hiệu năng; `wrong_doc_rate`/`wrong_node_rate`; A4–A6 và C1 tầng quy tắc.

### F.8 Sprint 3 — Model Router, Claims, Chat Agent, bộ nhớ, phân tích

| WP | Việc | Nghiệm thu |
|---|---|---|
| 3.1 | Model Registry theo capability, kiến trúc Hybrid Multi-LLM (mỗi stage chọn model qua Registry), hai chế độ vận hành API Mode / Local Mode: `OpenAICompatibleAdapter`, `AnthropicNativeAdapter`, `LocalInferenceAdapter` tự viết (timeout, backoff idempotent, circuit breaker, giới hạn redirect/endpoint); secret mã hóa, mask, không đọc lại; test endpoint chỉ bằng dữ liệu tổng hợp | Không dùng LiteLLM; test từng tính năng tương thích, không giả định rerank/JSON-schema |
| 3.2 | API Mode (có Internet; embedding/reranker local hoặc API; chỉ gửi dữ liệu chính sách cho phép; fallback trong phạm vi API được phép) và Local Mode (ngắt hoàn toàn Internet; LLM, embedding, reranker 100% local; fallback chỉ model nội bộ). Egress policy theo công thức §8.4 với điều kiện `mode == API`; fallback chỉ cùng privacy zone; audit mỗi quyết định route | Remote denied ⇒ `REMOTE_AI_DENIED`; Local Mode không DNS/HTTP ra Internet, chỉ endpoint nội bộ đã duyệt (egress guard + rule Windows Firewall), chạy trọn tìm kiếm/embedding/rerank/phân tích/xem PDF khi máy không có Internet, đăng nhập và khởi động không gọi dịch vụ ngoài, model và bản cập nhật nhập bằng media offline có kiểm hash; local lỗi không tự bật remote |
| 3.3 | Workflow Analyze/Generate cố định, tổng llm_attempt_budget=2 mỗi run, tính cả lỗi/timeout/retry/fallback; rules-first, extractive khi thiếu model/budget; evidence trong EVIDENCE_DATA | Test bộ đếm ở adapter: không quá hai request LLM; P0 summary bằng code, A2 không thêm call; lỗi hoặc hết budget vẫn trả evidence hợp lệ, không loop |
| 3.4 | OpenAPI/SSE theo E: query_id + run_id + facts_revision + snapshot_revision + event_sequence; idempotency, cancel, retry tường minh và reconnect; snapshot null trước pin, nhất quán sau evidence | Event/replay cũ không đè run mới; reconnect không gọi model lại; recheck ACL/policy khi phát event; incognito chỉ replay RAM; không stream raw claim chưa validate |
| 3.5 | Frontend S1: `FactChips` dirty-state, `DirtyFactBar`, `EvidenceGroupTabs`, `TwoPhaseSkeleton` (câu trung tính), `CoverageChecklist` tách `source_verified / effective_checked / applicability_checked / claim_supported`, nhãn trạng thái, nhãn `stale` | Sửa 3 chip chỉ 1 requery; copy/in giữ phạm vi + `as_of_date` + cảnh báo; UI không dùng "Đã xác minh X căn cứ" |
| 3.6 | Admin AI Configuration hoàn chỉnh theo S9: cấu hình API/Local, provider/adapter/endpoint/model/runtime/artifact/secret/stage routes, test tổng hợp và mask key; dashboard S12 | Thay model trong adapter được hỗ trợ qua cấu hình không sửa mã; không secret ra frontend/log; chưa có model/key có trạng thái thật, owner tự nhập sau; USER không có form cấu hình AI |
| 3.7 | Memory service M1–M5; P0 rolling summary bằng code; retention + opt-in, incognito RAM TTL, Memory Center, invalidation, xóa messages/summary/facts/cache và cancel job dẫn xuất | Test không persist nội dung incognito, hết TTL mất phiên, cross-user ACL, xóa không bị job cũ ghi lại; claim không trỏ bộ nhớ; dữ liệu xóa không quay lại sau restore áp sổ xóa |
| 3.8 | Long-context manager: ngân sách token, evidence packing, xử lý theo aspect, `partial` | Câu hỏi nhiều văn bản vẫn trích đúng; vượt ngân sách báo `partial` |
| 3.9 | User Portal tách Admin Portal; AgentLauncher/Panel + viewer/workspace chung phiên; shell desktop USER Tauri 2 theo W1–W8/S14: login trong app, Orb toggle, drag/resize, tray, logout/exit, state backend chung | E2E native/web và quyền server; không nền vuông/bóng dư/login trong suốt/console/vùng kéo đè chữ; thu/mở/PDF/workspace không mất phiên; USER không có menu quản trị; Local không tải tài nguyên ngoài |
| 3.10 | L3–L5: mâu thuẫn/ngoại lệ, kiểm claim tầng 1, POC tầng 2 | `unsupported_claim_rate` giảm so baseline mà false rejection không tăng |
| 3.11 | Trap set người nắm nghiệp vụ duyệt, nhóm paraphrase/tình huống tách đúng split; dashboard chỉ số; freeze candidate/config trước đợt đánh giá chốt | Regression dùng trong phát triển; trap hold-out chỉ đánh giá chốt, không lộ đáp án cho người tune; tập đã dùng để sửa được đánh dấu và thay tập chưa xem cho tuyên bố độc lập sau đó |
| 3.12 | Phân tích tình huống (A1) và thông tin còn thiếu (A3) trên FactChips | Mỗi dòng có `evidence_id`; thiếu điều kiện không kết luận; trap set không bị phá |
| 3.13 | Gợi ý câu hỏi tiếp theo (A2) có dry-run retrieval | Mọi gợi ý hiển thị đều có evidence trong ACL (kiểm bằng test); đo tỷ lệ bấm |
| 3.14 | Giao diện: tab Phân tích/Liên quan trong Chat Agent, tab Đề xuất của AI cho curator (S6) | E2E; chấp nhận/từ chối ghi audit; AI không có API ghi nghiệp vụ |

**Gate S3:** API Mode / Local Mode được kiểm với provider/model thực được cấu hình; Local kiểm khi ngắt Internet, cho phép endpoint LAN nội bộ đã duyệt; regression polarity/numeric/temporal, UI hai pha, bộ nhớ, trap set và A1–A3 đạt. Desktop USER qua luồng login → Orb → chat → viewer/workspace → thu/mở → logout. Chưa có key/model thật thì ghi gate AI chưa đạt; có thể hoàn thiện việc độc lập bằng mock nhưng không ghi đã chạy AI thực.

### F.9 Sprint 4 — Hardening và đóng gói Windows

| WP | Việc | Nghiệm thu |
|---|---|---|
| 4.1 | Bộ test bảo mật/hồi quy: ACL qua cache và `as_of_date`, cross-scope, prompt injection, XSS từ PDF, CSP, KV cache isolation (nếu có local LLM), PDF mojibake, curator thiếu approval, zero-answer | Mọi bug từ feedback có gold test tái hiện |
| 4.2 | Tải và backpressure: concurrency gate cho CPU LLM, job position, cancel; test 30–60 session; đo `evidence_ready_ms` P50/P95 tách khỏi `final_answer_ms`; so parallel vs serial vs CTE dưới tải | Số đo ghi kèm môi trường; evidence-first vẫn hiện khi inference kẹt |
| 4.3 | Đóng gói cho Windows (installer, dịch vụ Windows): Core Pack, Model Pack manifest (id, sha256, license, revision, dimension, RAM/disk), Data Pack; demo cài sạch **< 10 GB** kiểm trong CI; báo dung lượng Core/Model/PostgreSQL/data riêng; installer đặt mọi công cụ/tool/runtime cần cài dưới `E:\Programs` bằng cấu hình triển khai, gồm cache/store do dự án quản lý | `measure-footprint` chạy trong CI; không PyTorch/full ML extras mặc định; preflight root/quyền/dung lượng; inventory real path đúng root; không PATH/LLM hardcode, không cài global/AppData/Program Files hoặc âm thầm đổi ổ |
| 4.4 | Backup mã hóa + restore máy sạch; retention audit/bộ nhớ/backup, sổ yêu cầu xóa mới nhất, SBOM/license/runbook offline/API và client desktop; runbook ghi root cài, dependency-manifest và cách nạp cấu hình; dữ liệu/backup theo cấu hình riêng | Restore có dữ liệu mẫu đã xóa: áp sổ xóa trước mở dịch vụ, không phục hồi nội dung vào history/cache; thiếu đối soát thì chưa mở truy cập. Cấu hình endpoint/path qua môi trường triển khai; secret do người vận hành nhập/khôi phục theo chính sách, không chép secret từ máy cũ; restore/reinstall giữ đúng root cài công cụ; không chép đường dẫn máy cũ vào source hoặc tự di chuyển dữ liệu |
| 4.5 | Gold mở rộng vượt v0 (150–200 câu) **khi có reviewer**; P1 (PyVi, BM25 re-score, ParadeDB, HNSW, ONNX INT8, KV prefix) chỉ mở nếu benchmark/ADR chứng minh | Không bật mặc định khi chưa qua non-regression |
| 4.6 | Tối ưu và cache riêng embedding/analysis/retrieval theo C.7; analysis/retrieval OFF cho đến khi đủ fingerprint và invalidation; đo hồi quy | Test cùng câu hỏi khác user/phiên/facts/memory/scope/as_of_date/ACL/policy/index/model; incognito không cache bền; không thoái lui độ chính xác, số đo kèm môi trường |
| 4.7 | Kiểm widget và desktop W1–W8/S14: auth, Orb toggle, login/panel nền đục, vùng kéo, resize, tray, workspace/viewer, stop/retry, logout; responsive 320/768/1024/1280px, DPI 100/125/150/200%, nhiều màn hình, keyboard/contrast/reduced-motion; kiểm native sau cài tại root B.8 với tool ngoài manifest không hiện diện trong PATH của tiến trình thử | Có ảnh/log trên Windows đích; không overlap hai vùng tương tác, không nền vuông/bóng mờ dư/console, không mất nội dung khi thu/mở; đo tải trang trước/sau; unit/build không thay nghiệm thu native thực tế; Orb/chat/viewer vẫn chạy bằng dependency đã khai báo; lỗi root/tool thiếu hiển thị rõ, không fallback đường dẫn |
| 4.8 | Backend/dữ liệu chủ trì red-team: prompt injection, memory poisoning, cross-user leak, cache ngữ cảnh, incognito persistence, xóa/restore và job cũ; retrieval/frontend phối hợp | Không rò rỉ; nội dung đã xóa không hồi sinh; phản hồi chưa duyệt không đổi xếp hạng. Báo cáo có chủ trì, ca test, dữ liệu và phần chưa kiểm |
| 4.9 | Retrieval/eval chủ trì danh sách P1 owner chọn: A7–A10, D1, C1(c,e); backend/frontend phối hợp, ghi rõ mục không chọn | Mỗi tính năng được chọn có test/chỉ số và owner chốt; không tăng unsupported_claim_rate; không tự bật P1 hoặc dùng held-out đã xem để tune |

**Gate S4:** red-team/cache/bộ nhớ, restore không hồi sinh nội dung đã xóa, hồi quy hiệu năng và nghiệm thu desktop thực qua; footprint trong trần demo; P1 owner chọn qua nghiệm thu. Không dùng test/build cũ của project đã mất làm bằng chứng hiện tại.

### F.10 Mẫu báo cáo cuối mỗi WP (bắt buộc)

```text
WP: <id> — <tên>
Trạng thái: Xong / Xong một phần / Bị chặn
Đã làm: <danh sách ngắn>
Test: <tên test + kết quả thật, số pass/fail>
Số đo: <nếu có; ghi môi trường, phiên bản, corpus hash>
Quyết định/ADR mới: <id>
CHƯA XONG / bị hoãn: <liệt kê rõ, kèm lý do>
Rủi ro / cần người quyết: <nếu có>
```

Phần "CHƯA XONG" không được để trống bằng cách lược bỏ; không đổi tiêu chí nghiệm thu để test xanh.

### F.11 Việc cần con người (agent không tự thay được)

- **Nghiệp vụ:** duyệt các nguyên tắc nghiệp vụ quan trọng trong ERD (quan hệ hiệu lực, sửa đổi, bổ sung, bãi bỏ đến Điều/Khoản/Điểm; trạng thái node) và sequence `ingest → review → retrieve → evidence → claims → citation-click`, đầu Sprint 1. Không cần duyệt từng chi tiết kỹ thuật.
- **Độ đúng của căn cứ:** người nắm nghiệp vụ duyệt đáp án mẫu Gold v0 (150–200 câu) và trap set trước khi dùng làm chuẩn; CURATOR xử lý nháp/hints; REVIEWER phê duyệt tài liệu, metadata hiệu lực và quan hệ sửa đổi có tác động đến căn cứ.
- **Quyền truy cập:** phê duyệt chính sách remote AI theo từng category (API Mode); ai được thấy Chat Agent theo role; ánh xạ quyền với app quản lý cán bộ nếu tích hợp.
- **Bảo mật và riêng tư:** admin xác minh và duyệt từng domain đưa vào allowlist; xác nhận cấu hình Local Mode và việc ngắt Internet ở hạ tầng mạng; chốt thời hạn lưu mặc định của bộ nhớ hội thoại và loại dữ liệu được phép lưu.
- **Ngưỡng chấp nhận:** owner chốt ngưỡng cho các chỉ số chống ảo giác và mục tiêu độ trễ sau khi có baseline; chọn tính năng P1 nào làm trước (C.5); curator quyết định chấp nhận hoặc từ chối từng đề xuất của AI.
- **Xác nhận giả định ở B.6**, đặc biệt: người dùng có được tự chọn chế độ hay không, tỷ lệ chia Gold, kích thước trap set.
- **Cung cấp (không phải phê duyệt):** máy Windows đích để đo footprint, latency, backup/restore.

### F.12 Rủi ro chính

| Rủi ro | Cách xử lý trong plan |
|---|---|
| pgvector gặp vấn đề trên Windows | WP 0.2; ADR đề xuất cách khắc phục trên Windows (bản build, cách biên dịch) trước khi bàn đổi kiến trúc |
| Chặn kết nối ở ứng dụng không thay được ngắt mạng thật | WP 0.7, 3.2; agent cung cấp egress guard và rule firewall mẫu; việc ngắt Internet ở hạ tầng do người vận hành bảo đảm |
| Model embedding/reranker Việt không chạy ONNX hoặc vướng license | WP 0.4; profile B không cần LLM/dense |
| PDF cũ lỗi font, bbox lệch khi xoay/CropBox | WP 0.3, 1.5; fallback trang + quote, không tô sai |
| Chuỗi sửa đổi thiếu văn bản trong kho | Resolver báo `temporal_unknown`, không khẳng định "không sót sửa đổi" |
| Gold 150–200 câu cần nhiều thời gian duyệt của người nắm nghiệp vụ | Agent soạn đủ trích dẫn và tự kiểm trước; duyệt theo lô; case chưa duyệt không tính vào chuẩn; báo rõ số case đã duyệt |
| Dùng lẫn Gold với chỉnh ngưỡng gây đánh giá thiên lệch | Tách calibration và held-out, script kiểm không giao nhau |
| CPU local LLM nghẽn khi 30–60 session | Evidence tách khỏi generate; queue + backpressure; template extractive |
| Phình dependency và dung lượng | Manifest + CI đo footprint, trần demo < 10 GB |
| Bộ nhớ cũ sau khi snapshot đổi | Gắn revision + nhãn "cần kiểm lại" |
| Đầu độc bộ nhớ/hints | Chỉ curator duyệt mới có hiệu lực; phản hồi người dùng không tự đổi xếp hạng |
| Lớp kiểm mới gây từ chối quá tay hoặc làm chậm | Theo dõi false rejection và `evidence_ready_ms` sau mỗi lớp; mỗi lớp sau cờ |
| Phân tích bị đọc như tư vấn pháp lý | Ba nhãn Căn cứ/Phân tích/Gợi ý; không kết luận khi thiếu điều kiện; lưu ý cuối kết quả |
| Curator quá tải vì đề xuất của AI | Xếp theo rủi ro, giới hạn số đề xuất mỗi lượt, đo `suggestion_acceptance_rate` |

### F.13 Ca bắt buộc trong release gate (tóm tắt; danh sách P0 đầy đủ ở SRS §16)

- Rò rỉ ACL: qua lexical, vector, rerank, cache, tokenizer, citation, viewer, bộ nhớ, gợi ý và đồ thị liên quan.
- SSRF/redirect/MIME giả; URL ngoài allowlist; prompt injection và XSS từ PDF.
- Hiệu lực: chuỗi A→B→C→D; cycle; thiếu cạnh; xung đột; snapshot stale; rollback cutover; `as_of_date` trước ngày sửa đổi.
- Retrieval: pre-gate 3 nhánh; no-answer; cosine thấp nhưng nguồn đúng; nhầm hàng xóm (Điều 15/150); tiền đề sai.
- Claims: numeric/date, polarity/modality, quote do backend hydrate, claim trỏ vào bộ nhớ bị từ chối.
- Local Mode: không kết nối Internet; endpoint nội bộ chỉ theo allowlist; chạy trọn khi ngắt Internet; không tự chuyển sang API khi Local LLM lỗi.
- Viewer: highlight đúng (nhiều dòng, xoay, CropBox); fallback trung thực; PDF không đổi byte.
- Vận hành: backup/restore máy sạch có đối soát sổ xóa; dịch vụ Windows tự khởi động lại; footprint < 10 GB.
- LLM cấu hình API/Local, không provider/model/endpoint/key/path cố định; thử thay hai cấu hình đại diện trong adapter được hỗ trợ; đếm cả retry/fallback trong budget.
- PATH/cài đặt: mọi tool/runtime dự án cài và cache/store tương ứng ở `E:\Programs` qua cấu hình, kiểm real path trong root; không hardcode PATH/LLM hoặc dựa vào tool global; missing-root/dependency không fallback đường dẫn.
- Desktop: tách User/Admin, Orb tròn toggle, login/panel không trong suốt, không console/bóng dư, drag/resize không đè nội dung, thu/mở/PDF/workspace giữ phiên, tray/logout/exit đúng.
- Gold: kiểm split theo nhóm tình huống, nội dung held-out không được dùng để tune; ghi candidate/config/corpus/split revision.

---

## G. Prompt khởi động và phụ lục

### G.1 Prompt giao cho AI triển khai

> Bạn là coding agent triển khai Vietnamese Evidence RAG Agent trên Windows. Đọc `docs/SRS_v1.3.md`, `docs/HOSO_BAN_GIAO.md` và `docs/architecture-decisions/ADR-000.md`; nếu đang ở gói bàn giao, dùng ánh xạ trong README. SRS v1.3 và ADR-000 đã có: WP 0.0 tích hợp/đối soát, không viết lại đặc tả hoặc chọn lại quyết định owner.
> 
> Triển khai tuần tự các WP mục F, gồm bộ nhớ, chống ảo giác, phân tích/gợi ý và desktop USER. USER mở shortcut, đăng nhập trong app Windows, dùng Orb tròn góc phải desktop, click mở/thu chat, mở PDF/workspace cùng phiên; có drag/resize/tray/stop/retry/logout/exit theo S14. Admin Portal tách User Portal, dùng chung auth/backend/PostgreSQL/kho tài liệu/RAG; không tạo chatbot hoặc DB mỗi máy USER. Giữ theme/tokens và chữ dễ đọc; Orb không nền vuông/bóng dư, login/panel nền đục, vùng kéo không đè chữ, không hiện console.
> 
> LLM cấu hình API hoặc Local qua Registry/Router từng stage: adapter/provider, endpoint/runtime được duyệt, model ID/artifact, params, revision, secret reference và fallback. Không hardcode quyền/provider/model/endpoint/key/host/port/path; dùng cấu hình, manifest và platform API. API Mode có Internet và egress được phép; Local Mode ngắt Internet, chỉ runtime/endpoint nội bộ được duyệt, không tự chuyển API. Model POC không là model bắt buộc. Owner tự nhập key sau; chưa có model/key thì hoàn thiện tính năng và test hợp đồng, trả evidence/extractive thật, không giả lập AI hoặc công nhận gate provider đã đạt.
> 
> Không hardcode PATH hoặc LLM. Toàn bộ công cụ/tool/runtime dự án cài để build/cài/vận hành app phải dưới root `E:\Programs` do owner chốt; root chỉ là giá trị deployment profile `installation.programs_root` / `EVIDENCE_PROGRAMS_ROOT`, không nhúng trong code/script. Resolve executable/model/artifact và cache công cụ từ manifest dưới root, không dùng fallback PATH/global/AppData/Program Files. Thiếu root/dependency thì báo lỗi, không tự đổi ổ. Mỗi máy chỉ cài thành phần theo role; dữ liệu nghiệp vụ/backup có đường dẫn cấu hình riêng, không tự di chuyển. Tuân thủ B.8 và SRS §25.9.
> 
> Tuân thủ B.3/B.7/B.8 và SRS §25: CURATOR nháp, REVIEWER duyệt; cache analysis/retrieval OFF đến khi đủ fingerprint và test; incognito chỉ RAM, retention + opt-in mới lưu; xóa dẫn xuất/cache/job, restore áp sổ xóa; Gold 150–200 case người nắm nghiệp vụ duyệt, split theo nhóm tình huống, regression tách held-out; llm_attempt_budget=2 tính cả timeout/retry/fallback, summary P0 bằng code. Scope là SELECTED hoặc ALL_AUTHORIZED, server luôn kiểm ACL; SSE dùng query_id/run_id/revisions/sequence, retry tường minh không trộn lượt.
> 
> AI tự dựng ERD/migration/test DB và làm tối đa phần kỹ thuật kiểm chứng được; chỉ cần người quyết các nguyên tắc nghiệp vụ, quyền truy cập, bảo mật và độ đúng căn cứ. Không tự công nhận Gold, không bịa văn bản pháp lý, không thêm dependency bị cấm, không dùng kết quả cũ làm bằng chứng hiện tại. Thiếu key/model/reviewer/thiết bị thì báo đúng gate còn thiếu và làm tiếp việc độc lập. Kết thúc mỗi WP báo cáo F.10, có số đo/môi trường và mục CHƯA XONG.

### G.2 Danh sách file bàn giao

| File | Vai trò |
|---|---|
| `01_HOSO_BAN_GIAO_Vietnamese_Evidence_RAG_Agent.md` | Hồ sơ này: tính năng, UX/UI, API, plan, prompt |
| `02_Vietnamese_Evidence_RAG_Agent_SRS_v1_3.md` | SRS kỹ thuật hiện hành, gồm §25 |
| `03_ADR_000_QUYET_DINH_BAN_GIAO.md` | Ghi nhận quyết định, mặc định và ranh giới nghiệm thu |
| `02_Vietnamese_Evidence_RAG_Agent_SRS_v1_2_1.md` | Bản lịch sử giữ nguyên, không dùng làm yêu cầu hiện hành |

### G.3 Từ điển ngắn

**as_of_date:** ngày áp dụng của tra cứu. **Evidence:** đoạn nguồn đã kiểm chứng kèm vị trí. **Node:** một đơn vị của văn bản (Chương/Mục/Điều/Khoản/Điểm). **Snapshot hiệu lực:** kết quả đã tính của chuỗi sửa đổi, publish nguyên tử theo revision. **Fail-closed:** khi không chắc thì chặn/từ chối thay vì cho qua. **Held-out:** tập đánh giá không dùng để chỉnh ngưỡng. **Dry-run retrieval:** chạy thử truy xuất để kiểm một gợi ý có căn cứ trong quyền người dùng hay không.
