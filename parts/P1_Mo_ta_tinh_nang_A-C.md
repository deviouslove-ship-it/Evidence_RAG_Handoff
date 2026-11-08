# HỒ SƠ BÀN GIAO TRIỂN KHAI — Vietnamese Evidence RAG Agent

Phiên bản hồ sơ 1.1 · cập nhật ngày 21/10/2026
Căn cứ: SRS v1.3 + quyết định của owner ngày 17/10 và 21/10/2026; đối chiếu lịch sử project “Agent tra cuu”, đặc biệt yêu cầu tách portal và ứng dụng USER trên Windows.

**Hồ sơ gồm:** A. Cách dùng · B. Tổng quan sản phẩm và quyết định đã chốt · C. Mô tả tính năng · D. Thiết kế UX/UI chi tiết · E. Hợp đồng API bổ sung · F. Plan triển khai chi tiết · G. Prompt khởi động và phụ lục.

---

## A. Cách dùng hồ sơ này

**File đi kèm bắt buộc:** `02_Vietnamese_Evidence_RAG_Agent_SRS_v1_3.md` — nguồn kỹ thuật hiện hành (DDL phác thảo, thuật toán retrieval, API, benchmark, cấu trúc repo). Bản `02_Vietnamese_Evidence_RAG_Agent_SRS_v1_2_1.md` giữ nguyên làm lịch sử, không dùng để lấy quyết định vận hành hiện tại.

**Thứ tự ưu tiên khi mâu thuẫn:** (1) chỉ đạo mới của owner → (2) B.4, B.7 và B.8 → (3) hồ sơ này → (4) SRS v1.3. ADR-000 đi kèm ghi lại các quyết định; khi đặt vào repo, dùng `docs/SRS_v1.3.md`, `docs/HOSO_BAN_GIAO.md` và `docs/architecture-decisions/ADR-000.md`. Không tạo thêm đặc tả cạnh tranh. Bản cập nhật này chỉ là tài liệu, chưa chứng minh WP hay release gate đã hoàn thành.

**Quy tắc làm việc cho AI triển khai**

1. Làm tự chủ, ít hỏi lại. Điểm chưa chốt: dùng mặc định ở B.6 hoặc F.3, ghi ADR trong `docs/architecture-decisions/`, làm tiếp. Chỉ dừng chờ người ở bốn nhóm: **nghiệp vụ, quyền truy cập, bảo mật, độ đúng của căn cứ** (F.11).
2. Mỗi work package (WP) chỉ được coi là xong khi: code + migration + test xanh + tài liệu cập nhật + báo cáo theo mẫu F.10.
3. Tự làm tối đa mọi việc kỹ thuật kiểm chứng được bằng code/test (thiết kế ERD, migration, test DB, parser, retrieval, UI, CI, benchmark).
4. Không thêm dependency nặng: PyTorch, full Docling, LiteLLM (SDK lẫn Gateway), Redis, Elasticsearch, Qdrant, Neo4j, RAGFlow, GraphRAG, LlamaIndex/Haystack bắt buộc. Mọi dependency pin version + hash, ghi license và footprint vào `dependency-manifest`.
5. Không bịa văn bản pháp luật. Fixture cho UI gắn nhãn "HƯ CẤU". Benchmark chỉ dùng văn bản công khai thật, tách corpus riêng.
6. Không tuyên bố số liệu chưa đo ("<2ms", "giảm 60–70%", "100% chính xác"). Mọi con số ghi môi trường, phiên bản, dữ liệu.
7. Báo trung thực phần chưa xong; không đổi tiêu chí nghiệm thu để test xanh.

**Cách chia cho nhiều AI** (tùy owner): bảy luồng A–G ở F.4 có thể giao cho các AI khác nhau. Để làm song song: (a) luồng backend xuất **OpenAPI** đầu Sprint 1; (b) luồng frontend dùng mock server sinh từ OpenAPI và module design tokens (D.2) cho tới khi backend sẵn sàng; (c) luồng đánh giá dùng chung `corpus_public_real`; (d) mọi luồng nộp ADR và báo cáo WP theo cùng một mẫu.

---

## B. Tổng quan sản phẩm và quyết định đã chốt

### B.1 Sản phẩm là gì

Một nền tảng **hỏi đáp tiếng Việt có trích dẫn** trên kho văn bản đã được duyệt (luật, nghị định, thông tư, quy chế, quy trình, văn bản nội bộ). Người dùng hỏi bằng ngôn ngữ tự nhiên; hệ thống tìm đúng văn bản và đúng Điều/Khoản/Điểm, hiển thị **căn cứ nguyên văn kèm trang PDF gốc trước**, rồi mới giải thích điều kiện áp dụng, ngoại lệ, hiệu lực và quy định chuyển tiếp. Khi chưa đủ căn cứ, hệ thống nói thẳng "chưa đủ căn cứ" thay vì suy đoán.

Hệ thống **chỉ tham mưu (read-only advisory)**: không phê duyệt, không ra quyết định, không ghi dữ liệu nghiệp vụ.

Triển khai nội bộ (LAN) trên **Windows**, có hai chế độ vận hành độc lập: **API Mode** và **Local Mode (offline hoàn toàn)**.

### B.2 Người dùng và vai trò

| Vai trò | Làm gì | Không làm |
|---|---|---|
| USER (người hỏi) | Đăng nhập trong app Windows, dùng Orb/chat/workspace, chọn danh mục hoặc toàn bộ trong quyền, xem nguồn và bộ nhớ của mình | Không thấy tài liệu ngoài quyền; không upload vào kho, quản lý tài khoản, cấu hình model hoặc sửa dữ liệu kho |
| CURATOR | Nạp tài liệu, gắn danh mục, kiểm tra trích xuất, lưu draft node, chấp nhận/sửa/từ chối đề xuất ở mức nháp | Không phê duyệt tài liệu, phiên bản, hiệu lực hoặc sửa đổi nếu không được cấp thêm quyền REVIEWER |
| REVIEWER | Phê duyệt tài liệu/phiên bản, quan hệ sửa đổi, hiệu lực node | Không đổi cấu hình hệ thống |
| SYS_ADMIN | Cấu hình, tài khoản, quyền, Model Registry, allowlist domain | **Không mặc nhiên đọc nội dung nghiệp vụ hoặc tài liệu mật** |
| AUDITOR | Xem nhật ký và bằng chứng trong phạm vi cho phép | Không sửa dữ liệu |

Quyền của module RAG là **riêng**, không suy ra từ role của ứng dụng khác (ví dụ app quản lý cán bộ); ánh xạ phải được cấp tường minh.

### B.3 Bất biến (vi phạm = lỗi chặn release)

- Agent chỉ tham mưu, READ-ONLY; không có tool ghi/duyệt/gửi. Chỉ gọi các service đọc đã allowlist: `search_authorized_nodes`, `get_node_history`, `get_precomputed_references`, `validate_evidence`, `read_original_span`, `get_viewer_anchor`.
- **LLM không viết quote, không tạo ID hay số điều khoản.** Backend hydrate `quote_exact` từ `text_original` đã duyệt.
- **ACL lọc trong SQL trước** lexical, vector, rerank, cache, citation, viewer. Không lộ sự tồn tại của tài liệu không có quyền.
- **Remote AI fail-closed** (`remote_processing_allowed` mặc định FALSE). Local Mode không kết nối Internet; chỉ endpoint loopback/LAN nội bộ đã duyệt, không tự chuyển sang API khi Local LLM lỗi.
- **Hiệu lực ở mức node**, mặc định `unknown`; CURATOR lập nháp, REVIEWER phê duyệt tài liệu/phiên bản và quan hệ sửa đổi/hiệu lực. Không suy "còn hiệu lực" từ ngày ban hành.
- Retrieval 2 hops ≠ resolver hiệu lực. Resolver duyệt cả chuỗi sửa đổi đã verified đến fixed point; vượt guard hoặc thiếu cạnh thì fail-closed.
- Snapshot hiệu lực: atomic publish, pin revision; stale/failed ⇒ `SNAPSHOT_STALE`, không dùng snapshot cũ để khẳng định hiệu lực.
- Pre-gate 3 nhánh (pass / uncertain → mở rộng hoặc rerank / insufficient → từ chối). Không dùng min-max hay RRF score làm ngưỡng tuyệt đối.
- Hai pha UI: "đã kiểm tra nguồn/quote" ≠ "claim đã xác minh". Không dùng câu "Đã xác minh X căn cứ" khi chưa chứng minh hiệu lực và độ phủ.
- PDF gốc bất biến (không đổi byte, không overlay chữ mới); hash khác ⇒ version mới.
- PostgreSQL là DB duy nhất; không semantic answer cache; không auto-crawl; không GraphRAG/ColBERT ở MVP.
- Màu qua design tokens, không hardcode HEX; màu không là tín hiệu duy nhất.
- **Bộ nhớ không bao giờ là căn cứ**; validator từ chối claim trỏ vào bộ nhớ.
- **AI không tự công nhận đáp án Gold**; chỉ case do người nắm nghiệp vụ duyệt mới làm chuẩn; tập held-out không dùng để chỉnh ngưỡng.
- Mặc định chặn URL tùy ý; chỉ tài liệu đã duyệt vào kho; domain hợp lệ không đồng nghĩa văn bản còn hiệu lực.
- Windows là OS chính thức; không thêm phụ thuộc bắt buộc vào Linux, WSL hoặc Docker.
- **Không hardcode quyền, provider, endpoint, model ID, API key, đường dẫn model hoặc đường dẫn máy.** LLM được cấu hình API hoặc Local qua Registry/Router; model POC chỉ là dữ liệu cấu hình thử nghiệm.
- **Không hardcode PATH hoặc LLM.** Toàn bộ tool/runtime dự án cài phải dưới `E:\Programs` qua cấu hình `EVIDENCE_PROGRAMS_ROOT`; không đặt literal root trong logic ứng dụng. Chính sách bắt buộc ở B.8.
- User Portal, Admin Portal và shell desktop dùng chung authentication, backend API, PostgreSQL, kho tài liệu và pipeline RAG. Không tạo chatbot, database hoặc pipeline riêng cho desktop.

### B.4 Quyết định đã chốt của owner (đã đồng bộ vào SRS v1.3)

| # | Chủ đề | Quyết định |
|---|---|---|
| 1 | ERD | AI tự thiết kế toàn bộ ERD, bảng, quan hệ, khóa ngoại, ràng buộc; tự tạo migration và test DB; tự kiểm tra nhất quán, toàn vẹn, phân quyền, lịch sử phiên bản; đặc biệt quan hệ hiệu lực, sửa đổi, bổ sung, bãi bỏ đến từng Điều/Khoản/Điểm. Chỉ trình owner các nguyên tắc nghiệp vụ quan trọng |
| 2 | Nguồn và domain | Mặc định chặn tải URL tùy ý. Admin thêm/sửa/vô hiệu domain trong giao diện quản trị sau khi xác minh. Cho upload PDF từ máy. Kiểm tra nguồn gốc, cấu trúc file, hash, metadata, nội dung trước khi duyệt; chỉ tài liệu được duyệt vào kho chính thức. Domain hợp lệ không đồng nghĩa còn hiệu lực |
| 3 | Gold v0 | 150–200 câu từ PDF văn bản chính thức thật. Agent soạn, người nắm nghiệp vụ duyệt; AI không tự công nhận. Calibration dùng chỉnh ngưỡng; held-out độc lập với chỉnh ngưỡng và dữ liệu huấn luyện; chia theo nhóm tình huống/câu diễn đạt lại, không chỉ theo case ID |
| 4 | Chế độ AI | Kiến trúc Hybrid Multi-LLM nhưng **chỉ hai chế độ vận hành**. **API Mode:** có Internet; LLM qua API; embedding/reranker local hoặc API; chỉ gửi dữ liệu chính sách cho phép; fallback trong phạm vi API được phép. **Local Mode:** ngắt hoàn toàn Internet; LLM, embedding, reranker 100% local; fallback chỉ model nội bộ; model và bản cập nhật vào bằng phương tiện offline |
| 5 | Hệ điều hành | Windows chính thức: PostgreSQL + pgvector, FastAPI, frontend, worker, local LLM chạy trên Windows; không bắt buộc Linux/WSL/Docker. Sprint 0 chỉ kiểm cài pgvector, hiệu năng, backup/restore, dịch vụ Windows. Nếu pgvector gặp vấn đề, đề xuất cách khắc phục trên Windows trước khi bàn đổi kiến trúc |
| 6 | Bộ nhớ AI | Bộ nhớ cho truy vấn và ngữ cảnh dài (C.4) |
| 7 | Chat Agent | USER dùng app Windows: mở shortcut, đăng nhập trong app, Orb tròn góc phải desktop, bấm mở/thu chat, mở workspace cùng phiên; không cần mở trình duyệt. User/Admin tách portal, dùng chung RAG (C.3, C.12, D.5 S14) |
| 8 | Chống ảo giác | Thêm 8 lớp L0–L7 và trap set (C.6) |
| 9 | Chính xác và tốc độ | Cải tiến có cờ + đo; cache có cổng (C.7) |
| 10 | Phân tích và gợi ý | 12 tính năng A1–A10, C1, D1; gói P0 trong MVP, gói P1 theo ưu tiên owner (C.5) |
| 11 | Cấu hình LLM | Admin cấu hình API hoặc Local: adapter, endpoint/runtime được duyệt, model ID hoặc artifact, tham số, secret reference, route từng stage và fallback. Không cố định hãng/model/endpoint; owner tự nhập API key sau, không đưa secret vào hồ sơ |
| 12 | Phạm vi và portal | USER chọn một/nhiều danh mục hoặc “Tất cả danh mục được phép”; mọi trường hợp đều lọc ACL tại SQL. SYS_ADMIN không tự có quyền tra cứu; tài khoản nhiều quyền chuyển portal có chủ ý |
| 13 | PATH/LLM và cài công cụ | Không hardcode PATH hoặc LLM. Toàn bộ công cụ/tool/runtime dự án cài phải dưới `E:\Programs`; root lấy từ deployment profile hoặc `EVIDENCE_PROGRAMS_ROOT`, không nhúng trong code/script; chi tiết B.8 |

Ranh giới tự động/phê duyệt: agent tự làm mọi việc kỹ thuật kiểm chứng được; con người chỉ phê duyệt ở nghiệp vụ, quyền truy cập, bảo mật, độ đúng của căn cứ.

**Các thay đổi đã đưa vào SRS v1.3** (bảng đối chiếu lịch sử, không phải việc chờ AI sửa lại)

| Mục SRS | Cũ | Mới |
|---|---|---|
| §0.1 D02, §8.1, §13.1 | Ba chế độ HYBRID / API_ONLY / LOCAL_ONLY, Hybrid mặc định | Hai chế độ API Mode / Local Mode; Hybrid là kiến trúc Registry/Router chọn model theo stage; profile A/B/C giữ làm profile triển khai; remote vẫn fail-closed theo chính sách |
| §8.4 | `mode != LOCAL_ONLY` | `mode == API`; điều kiện còn lại giữ nguyên |
| §9.1 (thanh trên) | Chọn `[Hybrid ▼]` | Hiển thị huy hiệu chế độ chỉ đọc (xem B.6) |
| §10, §13, §18 Sprint 0, §22 | Postgres Windows hoặc Linux, chọn OS ở Sprint 0 | Windows đã chốt; `deploy/windows` là baseline |
| §11.2, §12.3 | `import-url` theo allowlist cấu hình | Allowlist là bảng DB do admin quản lý trong giao diện, mặc định chặn |
| §15.1, §16, §18 Sprint 1 | Gold v0 50–100 câu | 150–200 câu, tách tập calibration và held-out |
| Mục mới | — | Thêm các mục: Bộ nhớ, Chat Agent, Lớp chống ảo giác, Phân tích và gợi ý |
| §9, §17–18, §25 | Widget trong trình duyệt là mô tả chính | Thêm shell desktop USER theo lịch sử đã được owner duyệt; giữ nguyên backend/RAG; đưa 8 góp ý thành hợp đồng và nghiệm thu |

### B.5 Phạm vi KHÔNG làm

Không auto-crawl; không semantic answer cache; không GraphRAG, ColBERT, Neo4j, Elasticsearch, Qdrant, Redis ở MVP; không LiteLLM; không SQLite làm DB chính; không xử lý nghiệp vụ (phê duyệt, kỷ luật, khen thưởng, chi trả) trong module này; không Dark Mode ở MVP (P1); OCR chỉ là plugin ngoại lệ, không cài runtime mặc định.

### B.6 Giả định agent dùng mặc định, owner có thể đổi

| Vấn đề | Mặc định | Đổi khi |
|---|---|---|
| Chế độ hiển thị trên giao diện | Huy hiệu chỉ đọc "API Mode"/"Local Mode"; chỉ admin đổi qua cấu hình, người dùng không tự chuyển | Owner cho phép người dùng chọn theo chính sách |
| Thư viện PDF | pypdfium2 | pdfplumber hơn rõ trên bbox/bảng ở POC |
| Highlight viewer | PDF.js + lớp overlay tự vẽ từ quads | react-pdf-highlighter-extended qua POC |
| Job queue | Procrastinate nếu overhead thấp | Không đạt: tự viết `SKIP LOCKED` |
| Chạy dịch vụ Windows | NSSM hoặc pywin32 service, chọn qua ADR | Cần cách khác |
| Embedding/reranker | Chọn qua POC từ ứng viên §14.3 SRS; Local Mode chỉ model chạy local | Không model nào qua: tắt dense bằng flag, chạy profile B (lexical + extractive) |
| Contextual dense prefix | OFF | POC chứng minh tăng chất lượng, không tăng missed-exception |
| Auth | Tài khoản cục bộ + role/ABAC của module RAG | Tích hợp app quản lý cán bộ sau, ánh xạ quyền tường minh |
| Tokenizer | Underthesea | P1 mới so PyVi |
| Số lượt hội thoại gần nhất gửi cho LLM | Cấu hình được, đề xuất 3 | Theo benchmark |
| Chia tập Gold | Đề xuất khoảng 30% calibration / 70% held-out, ghi ADR | Owner chốt |
| Trap set | Đề xuất 40–60 câu | Owner chốt |
| Thời hạn lưu bộ nhớ hội thoại | Owner chốt chính sách; trước khi có chính sách được duyệt, lưu hội thoại dài hạn OFF, phiên chỉ dùng RAM với TTL tạm | Bật lưu sau khi có retention và opt-in hợp lệ |
| Font | `Inter, system-ui, Arial, sans-serif`; chỉ đóng gói Inter sau khi kiểm license, Local Mode không tải font ngoài | — |
| Shell desktop USER | Tauri 2 theo phương án desktop đã được duyệt trong lịch sử; khóa phiên bản/runtime ở POC, không tạo backend riêng | Chỉ đổi công nghệ shell bằng ADR và quyết định owner |
| Phiên không lưu | RAM phía backend; TTL nhàn rỗi 30 phút, cấu hình được; không ghi nội dung vào PostgreSQL/log/cache bền | Owner có chính sách phiên khác; không âm thầm bật lưu |
| Cache analysis | OFF; chỉ bật sau test khóa theo toàn bộ ngữ cảnh và kiểm cô lập user | Bật bằng feature flag, có ADR và invalidation |
| Tóm tắt hội thoại P0 | Template/trích xuất bằng code; không gọi LLM riêng | LLM summary là P1 với job/quota riêng, không nằm trên đường trả evidence |
| Root cài công cụ | Đã chốt `E:\Programs` trong cấu hình `EVIDENCE_PROGRAMS_ROOT` / installation.programs_root; mọi tool/runtime dự án cài nằm dưới root (B.8) | Chỉ thay bằng chỉ đạo mới của owner; không tự chọn thư mục khác |

### B.7 Phương án thống nhất cho 8 góp ý

| # | Phương án đã chọn cho tài liệu | Vị trí và nghiệm thu |
|---|---|---|
| 1 | CURATOR tạo nháp; REVIEWER duyệt; accept đề xuất không tự publish | C.8, E, WP 1.7/3.14; test 403 và không đổi snapshot khi thiếu quyền |
| 2 | Tách embedding/analysis/retrieval cache; analysis OFF; khóa chứa mọi đầu vào ảnh hưởng kết quả | C.7, WP 4.6; cùng câu hỏi nhưng khác user/phiên/facts không dùng nhầm cache |
| 3 | Incognito chỉ RAM; xóa dữ liệu vận hành và áp lại sổ yêu cầu xóa khi restore | C.4, E, WP 3.7/4.4/4.8; không hồi sinh nội dung đã xóa |
| 4 | Profile B được nghiệm thu khả thi lõi offline với giới hạn công khai; không thay gate AI thật | C.9, WP 0.4/0.7/3.2; model và API do cấu hình, không hardcode |
| 5 | Chia Gold theo nhóm tình huống; regression dùng thường xuyên, held-out khóa đến đợt chốt | C.10, S11, WP 1.9/2.8/3.11 |
| 6 | Tối đa 2 lần thử gọi LLM trong một lượt, tính cả retry/fallback; P0 summary bằng code | C.3/C.4/C.9, WP 3.3; hết budget trả evidence/extractive |
| 7 | Gán một chủ trì cho mọi WP; backend chủ trì 4.8, retrieval/eval chủ trì 4.9 | F.4, prompt theo luồng; cộng tác không thay người chịu trách nhiệm |
| 8 | Panel và viewer chỉ cạnh nhau khi đủ chiều rộng; thiếu chỗ thì chuyển một khung | D.4/S3/S14, WP 4.7; kiểm 320/768/1024/1280px, DPI và nhiều màn hình |

**Căn cứ lịch sử đã đọc ngày 21/10/2026:** các chat “Thiết kế AI Agent tra cứu”, “Mô tả AI Widget”, “Tiếp tục triển khai dang dở” và “Khôi phục project RAG”. Giữ ý định sản phẩm: tách User/Admin, USER có app desktop, Orb toggle, giữ phiên khi thu/mở, stop/retry, phân tích có căn cứ, owner tự cấu hình API/Local, chữ dễ đọc và không lỗi cửa sổ. Các lỗi từng được nêu trở thành ca nghiệm thu; không kế thừa tài khoản test, secret, đường dẫn máy hoặc tuyên bố test cũ là kết quả hiện tại. Bảng màu Navy/Blue và ràng buộc chuyển động của hồ sơ hiện hành giữ làm chuẩn.

---

### B.8 Không hardcode PATH/LLM và vị trí cài công cụ bắt buộc

**Quyết định owner:** toàn bộ công cụ, tool và runtime mà dự án cần cài/đóng gói để app chạy phải nằm dưới `E:\Programs`. Đây là giá trị của cấu hình triển khai `installation.programs_root` / `EVIDENCE_PROGRAMS_ROOT`, **không phải hằng đường dẫn trong mã nguồn**. Không hardcode PATH, executable path, đường dẫn model, provider, endpoint, model ID hay API key.

- Installer/launcher/service đọc root từ deployment profile đã duyệt hoặc biến môi trường do cấu hình triển khai cung cấp; hai nguồn phải nhất quán. Mã nguồn, script cài/chạy, migration, UI và test không nhúng literal ổ đĩa hoặc đường dẫn máy. Đổi root chỉ khi có chỉ đạo mới của owner và cập nhật deployment profile, không sửa source để chuyển đường dẫn.
- Mỗi thành phần có thư mục con do manifest xác định dưới `<PROGRAMS_ROOT>/<product_id>/`: app, runtimes, database, tools, models và cache của công cụ. Dùng hàm nối đường dẫn/platform API; không nối chuỗi ổ đĩa bằng tay. Tên provider/model và artifact luôn lấy từ Registry/Model Pack manifest.
- Phạm vi gồm Python/môi trường backend, PostgreSQL + pgvector, runtime LLM/embedding/reranker, công cụ PDF/OCR khi bật, runtime desktop và service wrapper. Công cụ build/cài/vận hành bổ sung nếu cần cài cũng tuân thủ cùng root; chỉ cài thành phần thực sự cần theo vai trò máy và capability, không bắt máy USER cài database/backend riêng.
- Executable, DLL/plugin, package/model store và cache công cụ do dự án quản lý phải được resolve từ dependency-manifest dưới root đã cấu hình. Kiểm real path nằm trong root, version/hash/license; không âm thầm dùng bản trong PATH toàn cục, Program Files, AppData, Downloads hoặc thư mục source. Nếu tool cần PATH, tạo PATH cho tiến trình con từ manifest, không sửa PATH toàn hệ thống.
- Thiếu ổ/thư mục/quyền ghi hoặc dependency không hỗ trợ vị trí này thì báo lỗi/chặn thành phần đó và nêu phương án; không tự chuyển sang ổ C hoặc cài global. Quy định áp dụng phần dự án cài/đóng gói, không yêu cầu di chuyển thành phần Windows sẵn có.
- PDF nguồn, dữ liệu PostgreSQL, log nghiệp vụ và backup có cấu hình đường dẫn riêng, tách khỏi binary/tool; không tự di chuyển dữ liệu chỉ vì bổ sung quy định cài công cụ. Model/runtime cài local và cache công cụ vẫn thuộc root trên. Cấu hình/manifest không chứa API key plaintext.
- Mỗi máy Windows cài thành phần dự án theo cùng chính sách; client chỉ cài client/runtime cần thiết, server/inference node cài thành phần tương ứng. API provider từ xa là dịch vụ cấu hình, không biến thành yêu cầu cài model local.
- Model Registry & Runtime cục bộ: Nạp cấu hình từ DB kèm các tham số thế hệ (`params`: `temperature`, `max_tokens`, `json_mode`); hỗ trợ kiểm tra endpoint an toàn (`is_safe_endpoint`) cho phép loopback/localhost (`127.0.0.1`, `localhost`, `::1`) khi bật cờ `EVIDENCE_ALLOW_LOCAL_AI=true` cho Ollama/vLLM cục bộ; lọc danh sách đen biến môi trường nhạy cảm (`_SECRET_DENIED`) đối với `secret_ref`; bóc tách thẻ suy luận (`<think>`) của reasoning models; bọc timeout AI selection ở 70% query timeout và graceful degradation tránh treo ứng dụng.
- Nghiệm thu: dependency inventory ghi root và đường dẫn tương đối/real path của từng tool; cài sạch và khởi động không dựa vào PATH toàn cục; thiếu root/dependency báo đúng lỗi, không fallback đường dẫn; thay cấu hình model/API/Local không sửa source. Kiểm code/script không có PATH/LLM hardcode; literal `E:\Programs` chỉ nằm trong dữ liệu/chính sách cấu hình triển khai được duyệt, không nằm trong logic ứng dụng.

---

## C. Mô tả tính năng ứng dụng

Ký hiệu ưu tiên: **P0** = bắt buộc trong MVP/release gate; **P1** = sau MVP, có số đo. Mã tính năng dùng để tham chiếu trong plan (F) và thiết kế (D).

### C.1 Hỏi đáp có căn cứ (USER)

| Mã | Tính năng | Mô tả hành vi | Ràng buộc và an toàn | Ưu tiên |
|---|---|---|---|---|
| Q1 | Chọn phạm vi | Chọn một/nhiều danh mục hoặc “Tất cả danh mục được phép”; phải có phạm vi hợp lệ trước khi hỏi. Bộ lọc loại văn bản độc lập; `as_of_date` mặc định hôm nay theo timezone cấu hình | `scope_mode=SELECTED` cần `category_ids` hợp lệ; `ALL_AUTHORIZED` do server giải thành danh mục hiện được cấp, vẫn lọc ACL trong SQL, không có wildcard bỏ quyền | P0 |
| Q2 | Nhập câu hỏi và Analyze | Người dùng nhập văn bản tự nhiên; `analyze` sinh fact chips (đối tượng, hành vi/sự kiện, thời điểm, địa bàn, loại hồ sơ, điều kiện) và query rewrites; không kết luận | Rules-first; Tổng tối đa 2 lần thử gọi LLM mỗi run, tính cả retry/fallback | P0 |
| Q3 | Fact chips dirty-state và requery | Sửa/xóa/thêm chip không tự gọi lại; hiện "Đã chỉnh sửa dữ kiện — kết quả bên dưới dựa trên dữ kiện trước đó"; nút "Cập nhật dữ kiện & Tra cứu lại" gửi một request với `base_query_id`, `base_facts_revision`; kết quả cũ giữ nhãn `stale` đến khi có evidence mới | Dữ kiện AI suy ra không tự coi là xác thực: `user_confirmed` / `extracted_unconfirmed` / `inferred_uncertain` | P0 |
| Q4 | Hỏi thẳng Điều/Khoản/số hiệu | Legal Reference Router khớp duy nhất + approved + ACL + `as_of_date` thì bỏ qua Analyze | Mơ hồ thì quay về Analyze; không hứa 100% | P0 |
| Q5 | Evidence-first | Evidence cards validated hiện trước, giải thích hiện sau (SSE). Thẻ gộp theo vai trò: quy định chính / đối tượng / điều kiện / ngoại lệ / chuyển tiếp / thẩm quyền | Auto-merge chỉ là tổ chức UI, không biến các khoản độc lập thành căn cứ mới | P0 |
| Q6 | Nhãn trạng thái kết quả | **Đã xác định căn cứ / Có điều kiện / Thiếu căn cứ / Nguồn xung đột**; trường hợp không có tài liệu phù hợp: "Chưa tìm thấy tài liệu được phép truy cập" | Trạng thái tính từ quy tắc; không badge màu trang trí, không phần trăm tự đánh giá | P0 |
| Q7 | Checklist độ phủ căn cứ | Tách `source_verified`, `effective_checked`, `applicability_checked`, `claim_supported` (và chi tiết `transition_checked`, `required_facts_complete`, `scope_expansion`, `citation_verified`) | Không tuyên bố đã xác thực khi còn `temporal_unknown` hoặc mới chỉ có candidates | P0 |
| Q8 | Nhận định có dẫn chứng và đề xuất tham khảo | Claims + suggestions theo schema SRS §6.2, mỗi mục có `evidence_ids`; ba lớp nội dung phân biệt rõ: nguyên văn / nhận định có dẫn chứng / đề xuất tham khảo | Claim không có nguồn ⇒ hạ thành "chưa xác minh" hoặc chặn | P0 |
| Q9 | Từ chối đúng và hỏi lại | Thiếu căn cứ thì nói rõ không đủ căn cứ; thiếu dữ kiện thiết yếu thì hỏi tối đa 1–3 dữ kiện | Không chế ra điều khoản | P0 |
| Q10 | Mở rộng ngoài danh mục có kiểm soát | Khi điều khoản dẫn chiếu ra ngoài danh mục: (a) không mở rộng, báo thiếu; (b) mở từng văn bản liên quan đã được cấp quyền, có nhãn "Nguồn ngoài danh mục" | Không mở văn bản không có quyền | P0 |
| Q11 | Sao chép, in, xuất | Giữ nguyên phạm vi, `as_of_date`, ngày kho dữ liệu, số hiệu nguồn và cảnh báo sửa đổi | Refresh/print/copy không làm mất cảnh báo | P0 |
| Q12 | Phản hồi | Bốn loại: Căn cứ sai · Thiếu căn cứ · Văn bản hết hiệu lực · Trích dẫn sai đoạn; vào hàng chờ curator, liên kết evaluation case | Phản hồi chưa duyệt không đổi xếp hạng | P0 |
| Q13 | Lịch sử của tôi | Xem lại câu hỏi và kết quả của chính mình nếu chính sách cho phép; mở lại citation phải kiểm lại quyền và hiệu lực | Snapshot citation theo quyền kiểm toán | P0 |

### C.2 Xem nguồn và hiệu lực

| Mã | Tính năng | Mô tả hành vi | Ràng buộc và an toàn | Ưu tiên |
|---|---|---|---|---|
| V1 | PDF viewer nguyên bản | Mở đúng byte PDF bất biến, đúng version/trang, cuộn tới span; fallback mở đúng trang và hiện quote đối chiếu khi bbox không tin cậy, kèm cảnh báo "chưa tô chính xác" | Không overlay chữ mới, không phủ màu lên nội dung PDF | P0 |
| V2 | Cây điều khoản | Dựng từ DB: Chương > Mục > Điều > Khoản > Điểm; click node nhảy PDF | Không dựng từ PDF lúc xem | P0 |
| V3 | Sticky Amendment Banner | Trạng thái node **đúng `as_of_date`**: `active`, `modified`, `repealed`, `suspended`, `not_yet_effective`, `unknown`; cảnh báo cố định ở toolbar + huy hiệu ngay vùng highlight, có link mở đúng PDF/version/trang/node thay thế đã duyệt | Nhãn chữ + icon + mô tả theo ngày; không chỉ đổi màu; `modified` không đồng nghĩa mất hiệu lực toàn văn bản | P0 |
| V4 | Chuỗi sửa đổi | Chuỗi A ← B ← C hiển thị đúng các sửa đổi liên quan; nút "Xem nội dung áp dụng tại ngày tra cứu"; khi `as_of_date` trước ngày sửa đổi, diễn đạt "Quy định được thay đổi từ [ngày]" và luôn xét chuyển tiếp/đình chỉ | Thiếu metadata ⇒ "Hiệu lực chưa xác minh", không tự gắn hết hiệu lực | P0 |
| V5 | Nguồn chính thức và tải file | Link tới trang công bố chính thức nếu curator đã xác minh; tải PDF theo quyền | Không thay viewer nội bộ | P0 |

### C.3 Chat Agent cho người dùng (icon góc phải màn hình)

| Mã | Tính năng | Mô tả hành vi | Ràng buộc | Ưu tiên |
|---|---|---|---|---|
| G1 | Launcher | Orb tròn 56–64px mặc định góc phải dưới; bấm mở, bấm lại thu panel; tôn trọng safe-area/work area. Desktop chỉ vùng tròn hiển thị/nhận tương tác, không có nền vuông hoặc bóng dư | Trạng thái dựa trên backend; chuyển động nhẹ, reduced-motion; desktop theo C.12/S14 | P0 |
| G2 | Panel hội thoại | Ngăn trượt trên desktop, toàn màn hình trên điện thoại; đầu panel có chip phạm vi, `as_of_date`, FactChips; thẻ căn cứ gọn; tab Trả lời / Phân tích / Liên quan | Dùng cùng hợp đồng SSE hai pha như trang đầy đủ | P0 |
| G3 | Ngữ cảnh trang | Mở từ trang văn bản/danh mục thì gợi ý phạm vi theo trang, người dùng bỏ được; nhãn rõ khi truy vấn mở rộng ra ngoài phạm vi | Không tự mở rộng ngầm | P0 |
| G4 | Mở trang đầy đủ cùng phiên | Nút "Mở trang đầy đủ" giữ nguyên phiên, FactChips và kết quả | Trạng thái phiên ở server; trình duyệt chỉ giữ session id | P0 |
| G5 | Chip gợi ý | Hàng chip câu hỏi tiếp theo dưới câu trả lời (A2) | Mỗi gợi ý đã chạy thử retrieval | P0 |
| G6 | Viewer không mất hội thoại | Bấm citation mở PDF viewer đúng anchor mà không rời hội thoại; điện thoại: viewer toàn màn hình có nút quay lại | Kiểm lại ACL khi mở | P0 |
| G7 | Chỉ tham mưu | Không có nút thực hiện hay phê duyệt nghiệp vụ; workflow cố định, tối đa 2 lần thử gọi LLM cho mỗi lượt, tính cả lỗi/retry/fallback theo C.9 | Bất biến B.3; không agent loop tự chủ | P0 |
| G8 | Dừng và thử lại | Dừng lượt đang chạy; giữ evidence hợp lệ và nhãn kết quả chưa hoàn tất. Thử lại là thao tác tường minh, tạo `run_id` mới, không nhân đôi tin nhắn user | Idempotency theo lượt; không trộn events/claims hai lần chạy; recheck ACL/policy/revision | P0 |
| G9 | Nội dung hội thoại | Markdown/bảng/code block được render an toàn; copy kèm nguồn, history riêng và composer giữ nháp khi có lỗi | Không thực thi HTML/script trong model/PDF; đính kèm vào kho vẫn chỉ CURATOR có quyền | P0 |

### C.4 Bộ nhớ AI cho truy vấn và ngữ cảnh dài

Nguyên tắc: **bộ nhớ giúp hiểu câu hỏi, không giúp trả lời.** Câu trả lời pháp lý chỉ dựa trên evidence lấy lại từ kho tại thời điểm hỏi.

| Mã | Tầng | Lưu gì | Dùng để | Giới hạn an toàn |
|---|---|---|---|---|
| M1 | Trạng thái phiên | Facts có nhãn nguồn, phạm vi, `as_of_date`, tham chiếu đã giải ("điều đó" → node_id), câu hỏi còn mở | Viết lại câu nối tiếp, hiển thị FactChips | Gắn `facts_revision` và `snapshot_revision`; snapshot đổi ⇒ "cần kiểm lại", không dùng tự động |
| M2 | Tóm tắt hội thoại cuộn | P0: template/trích xuất bằng code; LLM summary chỉ P1, job riêng có quota/egress/audit, không chặn evidence | Giữ ngữ cảnh dài: LLM chỉ thấy trạng thái + tóm tắt + vài lượt gần nhất | Nhãn "không phải căn cứ"; validator từ chối claim trỏ vào nó; không chứa quote pháp lý |
| M3 | Sở thích người dùng (opt-in) | Danh mục mặc định, phạm vi hay dùng, kiểu hiển thị | Điền sẵn phạm vi | Không lưu nội dung pháp lý hay định danh nhạy cảm; xem và xóa được |
| M4 | Retrieval hints | Alias, từ đồng nghĩa pháp lý, cách gọi thông dụng → số hiệu/node chuẩn | Mở rộng truy vấn, định tuyến văn bản | Chỉ curator duyệt mới có hiệu lực; phản hồi người dùng không tự đổi xếp hạng |
| M5 | Bản đồ văn bản | Mục lục xác định từ cây node, danh sách văn bản liên quan | Định tuyến nhiều văn bản, giải thích phạm vi | Sinh bằng code; tóm tắt LLM của văn bản là P1 và gắn nhãn "không phải căn cứ" |

**Quy tắc chung của bộ nhớ**

- Mỗi lần dùng phải kiểm lại ACL, trạng thái approved và hiệu lực tại `as_of_date`; node không còn quyền thì bỏ khỏi trạng thái, không lộ sự tồn tại.
- Bộ nhớ riêng từng user; admin không đọc nội dung mặc định. Hội thoại dài hạn chỉ ghi khi có retention policy được duyệt và user opt-in; trước đó dùng phiên tạm RAM.
- `incognito=true`: nội dung phiên, facts, summary và events chỉ ở RAM backend, TTL nhàn rỗi mặc định 30 phút/có cấu hình; hết TTL/đăng xuất/thoát phiên thì hủy. Không ghi nội dung vào PostgreSQL, query/answer log, file tạm, cache bền hoặc SSE replay bền; audit chỉ metadata tối thiểu, không câu hỏi/quote/summary. Khởi động lại backend làm mất phiên tạm; UI nói rõ. Không tự tải hội thoại cũ vào phiên không lưu.
- Người dùng xem/sửa/xóa từng mục hoặc toàn bộ ở "Bộ nhớ của tôi"; xóa thật khỏi dữ liệu vận hành gồm messages, summary, facts, dẫn xuất và cache thuộc phiên/user. Hủy job đang dùng nội dung đó; tăng `memory_revision` để kết quả/job cũ không ghi lại dữ liệu đã xóa. Citation/audit cần giữ theo chính sách phải tách khỏi bộ nhớ và không giữ bản sao câu hỏi mật.
- **Kết nối giao diện & điều khiển luồng:** `EphemeralMemoryService` kết nối trực tiếp với giao diện `EvidenceChat` qua SSE streaming hai pha. Người dùng xem danh sách mục nhớ phiên trong ngăn kéo "Bộ nhớ phiên (RAM)", xóa từng mục (`DELETE /api/v1/memory/{item_id}`), xóa toàn bộ RAM (`DELETE /api/v1/memory`), bấm nút Dừng (`POST /turns/{id}/cancel`) hoặc Thử lại (`POST /turns/{id}/retry`). Bật công tắc "Lưu vào sở thích tra cứu" (`GET/PUT /api/v1/memory/preferences`) cho phép lưu và tự động áp dụng danh mục mặc định qua hàm `_with_preferences`.
- Backup có kỳ lưu hữu hạn và lịch hủy được công bố; không hứa xóa ngay nội dung khỏi mọi bản backup bất biến. Khi restore, áp lại sổ yêu cầu xóa tối thiểu mới nhất trước khi mở dịch vụ; thiếu sổ đối soát thì chưa mở truy cập. Không để nội dung đã xóa quay lại history, summary, cache hoặc gợi ý.
- Local Mode: bộ nhớ nằm trong PostgreSQL cục bộ. API Mode: tóm tắt cũng là dữ liệu, chỉ gửi ra ngoài khi chính sách cho phép.
- Không semantic answer cache; không tự học từ hội thoại vào xếp hạng.

**Ngữ cảnh dài**

- LLM không nhận toàn bộ lịch sử, chỉ nhận trạng thái phiên + tóm tắt + vài lượt gần nhất + evidence đã chọn.
- Câu nối tiếp được viết lại bảo thủ thành câu độc lập và **hiển thị "Đang hiểu là: …"** cho người dùng sửa; thiếu điều kiện then chốt thì hỏi lại tối đa một câu bằng lựa chọn dạng chip, không đoán.
- Evidence packing: ngân sách token theo stage; điều kiện chính và ngoại lệ đặt ở đầu và cuối; cắt theo node, không cắt giữa Khoản; không nén quote.
- Câu hỏi nhiều khía cạnh/nhiều văn bản: xử lý theo aspect rồi gộp, mỗi claim vẫn qua validator; vượt ngân sách ⇒ `partial` và nói rõ phần chưa đủ.

### C.5 Phân tích và gợi ý bằng AI

Ba nhãn phân biệt rõ trên giao diện: **Căn cứ** (trích nguyên văn) · **Phân tích** (suy ra từ căn cứ, kèm điều kiện chưa xác minh) · **Gợi ý** (việc nên hỏi hoặc kiểm tiếp, không phải khẳng định). Mỗi mục phân tích gắn ít nhất một `evidence_id` đã qua validator; mục không có căn cứ thì không hiển thị. Gợi ý tham khảo được lọc tự động loại trừ các căn cứ đã trích dẫn trong nhận định chính (claims) để bảo đảm không bị lặp lại. Tối ưu hóa truy vấn FTS PostgreSQL bằng cú pháp `LATERAL` trong `authorized_search.py` tính toán `to_tsvector` một lần cho mỗi hàng ứng viên kết hợp lọc hư từ nghi vấn tiếng Việt, ngăn chặn nghẽn truy vấn khi số lượng văn bản lớn. Chạy theo yêu cầu hoặc bất đồng bộ, **không làm chậm `evidence_ready_ms`**; quy tắc trước, LLM chỉ để diễn đạt; Local Mode luôn có bản quy tắc/extractive. Với curator, AI chỉ **đề xuất**; curator bấm chấp nhận, sửa hoặc từ chối.

| Mã | Tính năng | Cho ai | Cách làm | Chống sai | Gói |
|---|---|---|---|---|---|
| A1 | Phân tích tình huống có cấu trúc | USER | Trích facts từ mô tả (đối tượng, hành vi, thời điểm, số liệu) rồi xếp theo căn cứ: điều kiện đã thỏa / chưa xác minh, ngoại lệ, mốc thời gian, hệ quả nêu trong văn bản | Mỗi dòng có `evidence_id`; facts chưa xác nhận hiện thành chip để sửa; thiếu điều kiện thì không kết luận được/không được | P0 |
| A2 | Gợi ý câu hỏi tiếp theo | USER | Sinh từ khoảng trống đã biết: aspect `uncovered`, điều kiện chưa xác minh, ngoại lệ, văn bản sửa đổi liên quan; không sinh tự do | Chạy thử retrieval (dry-run): phải có evidence trong ACL, nếu không thì bỏ | P0 |
| A3 | Thông tin còn thiếu | USER | Liệt kê facts quyết định phạm vi áp dụng mà người dùng chưa cung cấp, dạng chip điền nhanh; điền xong chỉ requery một lần | Chỉ hỏi facts mà căn cứ thực sự dùng làm điều kiện | P0 |
| A4 | Điểm cần lưu ý trong căn cứ | USER | Quy tắc nhận diện thời hạn, con số, chủ thể, ngoại lệ ("trừ trường hợp"), điều kiện kèm theo; tô nổi trong thẻ căn cứ và PDF viewer | Chỉ đánh dấu đoạn có sẵn trong `text_original`, không diễn giải thêm | P0 |
| A5 | So sánh phiên bản một Điều | USER | Diff xác định giữa các version/amendment của cùng node theo `as_of_date`; AI chỉ diễn đạt ngắn phần thay đổi | Diff lấy từ text đã duyệt; thiếu bản trước thì nói không có | P0 |
| A6 | Văn bản và Điều liên quan | USER | Đồ thị từ `node_references` + `node_amendments`: văn bản hướng dẫn, sửa đổi, tham chiếu hai chiều, chuỗi sửa đổi | Hoàn toàn xác định, không LLM; chỉ hiện node trong ACL; quan hệ chưa duyệt có nhãn riêng | P0 |
| A7 | Diễn giải dễ hiểu | USER | Bật "giải thích đơn giản" cho từng claim, hiển thị cạnh quote | Là claim, qua validator như claim thường; cấm thêm ý | P1 |
| A8 | Tóm tắt Chương/Mục | USER | Extractive trước (tiêu đề + câu chủ chốt), LLM tùy chọn | Nhãn "không phải căn cứ", không dùng làm evidence | P1 |
| A9 | Theo dõi thay đổi | USER | Đăng ký theo dõi câu hỏi hoặc Điều; snapshot đổi ảnh hưởng node đó ⇒ thông báo trong ứng dụng, mở lại với `as_of_date` mới | Chỉ thông báo trong ứng dụng, không gửi nội dung ra ngoài | P1 |
| A10 | So sánh hai văn bản | USER | Căn theo cấu trúc chương/điều, diff, liệt kê khác biệt chính | Chỉ liệt kê khác biệt có cặp quote, không kết luận hơn kém | P1 |
| C1 | Đề xuất của AI cho curator | CURATOR | (a) quan hệ sửa đổi/bổ sung/bãi bỏ phát hiện từ mẫu câu ("sửa đổi, bổ sung khoản 2 Điều 5 của …"); (b) tham chiếu chưa giải; (c) văn bản trùng/tương tự; (d) trang/node parse bất thường; (e) retrieval hints rút từ phản hồi | Mỗi đề xuất kèm span nguồn và độ tin cậy, xếp theo rủi ro; từ chối được ghi nhận để đo precision; không tự áp dụng | P0 cho a, b, d; P1 cho c, e |
| D1 | Phân tích khoảng trống kho tri thức | ADMIN, CURATOR | Gom câu hỏi "không đủ căn cứ" theo chủ đề ⇒ gợi ý loại văn bản nên bổ sung; thống kê phản hồi sai theo văn bản | Dùng số liệu tổng hợp; nội dung câu hỏi hiện theo quyền; không tự tải văn bản | P1 |

### C.6 Lớp chống ảo giác và chống truy xuất sai

Thêm vào các validator có sẵn (ACL, span, hiệu lực node, allowlist ID, numeric/date, polarity/modality).

| Lớp | Việc | Đo bằng |
|---|---|---|
| L0. Tiền đề sai | Câu hỏi nhắc Điều/Khoản/văn bản không tồn tại hoặc sai số hiệu ⇒ trả lời "không có" kèm danh sách thực tế (ví dụ văn bản chỉ có Điều 1–N); không tìm gần đúng rồi trả bừa | `false_premise_detection_rate` |
| L1. Truy xuất đúng đối tượng | Ràng buộc rút từ câu hỏi (số hiệu, loại văn bản, năm, cơ quan, mốc thời gian, con số) phải khớp evidence; chống nhầm "hàng xóm" (Điều 15 và 150, Khoản 1 và 11) và nhầm phiên bản; sinh `retrieval_diagnostics`; lệch ⇒ mở rộng, hỏi lại hoặc từ chối | `wrong_doc_rate`, `wrong_node_rate` |
| L2. Định tuyến văn bản trước node | Chọn văn bản ứng viên bằng số hiệu, tiêu đề, loại, danh mục, bản đồ văn bản rồi mới tìm node; khử trùng lặp giữa các phiên bản, ưu tiên bản hiệu lực tại `as_of_date` | Ablation riêng |
| L3. Mâu thuẫn và ngoại lệ | Các node được chọn nói khác nhau về cùng đối tượng (số, thời hạn, chủ thể, "trừ trường hợp") ⇒ nêu cả hai, không chọn một | `missed_exception` |
| L4. Sinh có ràng buộc | Chỉ claims có `evidence_ids` trong allowlist; cấu hình xác định/nhiệt độ thấp nếu adapter hỗ trợ; cấm số, ngày, tên không có trong evidence; không dùng kiến thức ngoài | `validator_reject_rate` |
| L5. Claim có được căn cứ hỗ trợ | Tầng 1 xác định: trùng thực thể, số, ngày, phủ định, phương thức. Tầng 2 (P1): mô hình entailment cục bộ, chỉ bật khi qua POC và không làm tăng false rejection. Claim không qua ⇒ loại hoặc hiện "chưa xác minh" | `unsupported_claim_rate` |
| L6. Trung thực giao diện | Nhãn lấy từ trạng thái evidence và validator, không từ "độ tự tin" của LLM; không dùng "chắc chắn"/"đã xác minh" khi chưa đủ | Test UI |
| L7. Vòng phản hồi | "Sai/thiếu/lỗi hiệu lực" vào hàng đợi curator; case đã duyệt vào regression suite, không vào tập calibration hay held-out | Quy trình có test |

**Trap set** (đề xuất 40–60 câu, tách khỏi Gold v0): agent soạn từ PDF thật, người nắm nghiệp vụ duyệt. Gồm tiền đề sai, Điều không tồn tại, số hiệu gần giống, văn bản hết hiệu lực, hỏi vượt phạm vi, lệnh chèn trong PDF, yêu cầu bỏ qua nguồn, xin tư vấn vượt căn cứ. Ngưỡng chấp nhận do owner chốt sau baseline. Hồ sơ không tuyên bố loại bỏ hoàn toàn ảo giác; mục tiêu là đo được, giảm được và luôn nói rõ khi chưa đủ căn cứ.

### C.7 Chính xác và tốc độ

**Chính xác** (mỗi bước sau feature flag, chỉ bật khi benchmark không thoái lui): mở rộng truy vấn bằng retrieval hints đã duyệt; tách câu nhiều khía cạnh bằng quy tắc trước, LLM sau; lọc metadata rút từ câu hỏi (loại văn bản, cơ quan, năm, danh mục); định tuyến văn bản trước node (L2); rerank có điều kiện. Mỗi bước có ablation.

**Tốc độ** (không đổi bất biến an toàn):

- Tính trước lúc index: `text_folded`, `tsvector`, embedding, breadcrumb, applicability header, bản đồ văn bản; nạp model một lần khi khởi động và giữ session ONNX.
- Connection pool, prepared statements; lexical và dense chạy song song, so với tuần tự/CTE theo đúng benchmark SRS.
- Đường tắt: Legal Reference Router khớp duy nhất thì bỏ qua Analyze.
- Cache embedding: tách khỏi analysis; khóa gồm hash đúng input + model/tokenizer/prefix revision + phân vùng bảo mật; không gộp user mặc định. Phiên incognito không ghi cache bền; chỉ dùng cache RAM cùng phiên nếu cần.
- **Cache analysis mặc định OFF.** Chỉ bật khi khóa bao phủ principal/session, câu hỏi đã viết lại, `facts_revision`, `memory_revision`, phạm vi, `as_of_date`, ACL/policy revision, model/tokenizer/prompt-schema/hints revision và mọi đầu vào thực sự được đọc. Thiếu fingerprint nào ảnh hưởng output thì bỏ qua cache; recheck quyền khi đọc.
- **Cache retrieval mặc định OFF.** Nếu bật, khóa gồm ACL fingerprint + policy revision + `snapshot_revision`/source-review revision + `index_revision` + model/tokenizer/hints revision + phạm vi + `as_of_date` + truy vấn/facts. Quyền, dữ liệu, model, policy hoặc snapshot đổi phải invalidate. Không semantic answer cache; không dùng kết quả cache để vượt kiểm quyền.
- Evidence-first: hiện evidence ngay khi sẵn sàng, claim stream sau; giao diện prefetch trang PDF được trích khi hover.
- Đo `retrieval_ms`, `evidence_ready_ms`, `first_claim_ms`, `final_answer_ms` (P50/P95) trên máy Windows đích; baseline ở WP 2.13; mục tiêu số do owner chốt sau baseline; CI kiểm hồi quy hiệu năng với dung sai.

### C.8 Quản trị kho tài liệu (CURATOR, REVIEWER)

| Mã | Tính năng | Mô tả hành vi | Ràng buộc và an toàn | Ưu tiên |
|---|---|---|---|---|
| K1 | Danh mục | Tạo/sửa/ẩn/xóa mềm/khôi phục; cha–con độ sâu cấu hình (ví dụ 3); N–N với tài liệu; chuyển tài liệu giữa danh mục; import/export JSON/CSV có kiểm tra | Chống vòng lặp; xóa mềm không xóa file gốc/embedding đang dùng nơi khác; xóa cứng chỉ qua quy trình duyệt | P0 |
| K2 | Hồ sơ tài liệu | Metadata chuẩn (SRS §2.4): số hiệu, cơ quan, ngày ban hành/hiệu lực, trạng thái, nguồn, hash, phiên bản…; trạng thái hiệu lực mức Điều/Khoản | Không tự suy "còn hiệu lực" từ ngày ban hành; phân biệt `valid_time` và `recorded_time` | P0 |
| K3 | Upload PDF | Kéo thả/chọn file; kiểm magic bytes, quota, SHA-256; lưu bản bất biến; tiến độ ingest theo job | File lỗi cấu trúc/hash/metadata không thể thành `approved` | P0 |
| K4 | Import URL | Chỉ domain trong allowlist; DNS pin/recheck; chặn địa chỉ private/local; giới hạn redirect/size | URL ngoài allowlist bị chặn kèm lý do; hash đổi tại cùng URL ⇒ version mới chờ duyệt | P0 |
| K5 | Quản lý allowlist domain | Admin thêm/sửa/vô hiệu domain sau khi xác minh (kiểm DNS/HTTPS, người xác minh, ghi chú); mọi thay đổi audit | Domain bị vô hiệu thì import dừng | P0 |
| K6 | Pipeline ingestion | Parse native từng trang; chẩn đoán trang (ký tự `�`, tỷ lệ âm tiết hợp lệ, độ phủ text, thứ tự đọc); nhận diện TCVN3/VNI + chuyển mã có hồi kiểm; `needs_ocr` + interface OCR plugin | Trang lỗi không bao giờ thành quote verified | P0 |
| K7 | Parse cây node | Chương/Mục/Điều/Khoản/Điểm/Phụ lục; văn bản không cấu trúc theo heading/trang; `text_indexed` có breadcrumb; applicability header; `node_references`; `parse_confidence` | Không bịa Điều/Khoản | P0 |
| K8 | Hàng đợi duyệt theo rủi ro | Parser confidence thấp, nhảy khoản, chuyển mã, bbox lệch, hiệu lực chưa duyệt, đề xuất AI ⇒ vào hàng đợi, xếp theo rủi ro | Metadata hiệu lực luôn cần người duyệt | P0 |
| K9 | Curator Split-View | Trái: PDF.js bản bất biến, chọn trang/highlight span. Phải: cây `document_nodes` + form (label, position, cửa sổ hiệu lực node, link amendment). Click node nhảy PDF và ngược lại | Autosave draft ≠ Approve; `If-Match`/revision; audit actor; phím tắt không duyệt khi đang nhập; xác nhận khi sửa hiệu lực/amendment | P0 |
| K10 | Quan hệ sửa đổi và hiệu lực node | CURATOR tạo/sửa nháp `node_amendments`; REVIEWER phê duyệt với revision và audit; trạng thái node theo `as_of_date` | Accept đề xuất AI chỉ tạo/cập nhật nháp; không publish hoặc tăng approved revision khi thiếu REVIEWER | P0 |
| K11 | Snapshot hiệu lực | Resolver chạy đến fixed point (phát hiện cycle/đứt cạnh/chồng chéo/xung đột), staged → atomic publish theo `snapshot_revision`; stale fail-closed; invalidate cache | Không rò văn bản ngoài ACL | P0 |
| K12 | Phiên bản tài liệu | Hash khác ⇒ version mới; chọn bản tại ngày; so sánh phiên bản (A5) | PDF cũ giữ nguyên | P0 |
| K13 | Đề xuất AI cho curator | Xem C1 ở C.5 | Chỉ đề xuất | P0/P1 |

### C.9 Mô hình AI, chính sách và chế độ vận hành (SYS_ADMIN)

| Mã | Tính năng | Mô tả hành vi | Ràng buộc | Ưu tiên |
|---|---|---|---|---|
| R1 | Model Registry | Admin cấu hình API hoặc Local: adapter/provider, endpoint/runtime được duyệt, model ID/artifact, capability, tham số, revision, secret reference, trạng thái và định mức | Không hardcode provider/model/endpoint/key/model path; không LiteLLM; thay model trong capability/adapter được hỗ trợ không phải sửa mã | P0 |
| R2 | Stage routes | Mỗi stage chọn model cho API Mode và Local Mode; chuyển model qua Registry | Embedding đổi model ⇒ index mới song song rồi cutover | P0 |
| R3 | Hai chế độ vận hành | API Mode / Local Mode, đặt theo cấu hình hệ thống và chính sách danh mục | Local Mode: offline trọn vẹn (tìm kiếm, embedding, rerank, phân tích, xem PDF); không dịch vụ ngoài cho đăng nhập, bản quyền, khởi động | P0 |
| R4 | Egress policy | `remote_allowed` theo công thức SRS §8.4 với `mode == API`; mặc định chặn; audit mỗi quyết định route | Remote denied ⇒ `REMOTE_AI_DENIED`; fallback chỉ cùng privacy zone | P0 |
| R5 | Quản lý secret | Key nhập một lần, mã hóa, che; không đọc lại raw key | Không log key | P0 |
| R6 | Kiểm soát egress ở Local Mode | Egress guard trong ứng dụng + rule Windows Firewall mẫu + script `verify-egress` | Ngắt Internet thật vẫn do hạ tầng/OS bảo đảm thêm | P0 |

**Hợp đồng cấu hình và ngân sách LLM**

- Chỉ hai giá trị vận hành `API` / `LOCAL`. Admin cấu hình route từng stage cho hai chế độ; USER xem huy hiệu chỉ đọc, không nhập key/endpoint trong chat. API Mode dùng LLM qua API được duyệt; Local Mode dùng LLM nội bộ và không có đường fallback ra Internet. Provider mới ngoài giao thức adapter được hỗ trợ cần adapter có test; không giả định mọi API đều tương thích.
- Embedding, reranker và LLM là các capability cấu hình độc lập. POC không biến model thử nghiệm thành model cố định của sản phẩm. Yêu cầu ONNX ở POC embedding/reranker không cấm LLM GGUF hoặc định dạng khác chạy bằng runtime local đã kiểm chứng. Model path/runtime path lấy qua cấu hình/manifest/platform API.
- Chưa có model/key: hệ thống vẫn trả evidence/extractive thật; UI ghi “Chưa cấu hình mô hình AI”, `answer_generated=false`, không giả lập phân tích AI. Owner tự nhập secret qua giao diện quản trị sau; không đưa secret vào prompt, fixture hay log.
- Mỗi `run_id` có `llm_attempt_budget=2` cho Analyze + Generate. Mỗi lần gửi request đến LLM, kể cả timeout/lỗi/retry/fallback, tiêu thụ một lượt; retry ngầm không vượt budget. Nếu chỉ còn một lượt, ưu tiên stage cần thiết hoặc trả extractive. Summary P0, gợi ý A2 và tách aspect không tạo thêm lời gọi LLM ngoài budget.
- Stop hủy công việc còn có thể hủy, không thu hồi được request provider đã xử lý và không tự hoàn tiền budget. User bấm Thử lại tạo run mới, có rate limit và quota; không tự lặp vô hạn.
- Profile B lexical + extractive là khả năng suy giảm công khai, không phải mode thứ ba. S0 có thể nghiệm thu khả thi lõi offline theo profile này nếu model chưa đạt, ghi rõ dense/rerank/generation nào chưa được kiểm. Gate S3 cho cấu hình AI phải kiểm provider/model thực đã chọn; mock/FakeAdapter hoặc profile B không thay bằng chứng đó.

### C.10 Chất lượng, vận hành và bảo mật

| Mã | Tính năng | Mô tả hành vi | Ưu tiên |
|---|---|---|---|
| Z1 | Gold Dataset v0 | 150–200 câu từ PDF thật, reviewer duyệt. Mỗi case có căn cứ/phiên bản/ngày/source hash, `scenario_group_id` và `split_revision`; các câu diễn đạt lại hoặc cùng tình huống nằm cùng một split | P0 |
| Z2 | Benchmark B0–B7 và ablation | Chạy trên Gold đã duyệt; `ranx`/bootstrap; pin corpus hash, model/tokenizer revision; báo cáo có khoảng tin cậy | P0 |
| Z3 | Trap set và chỉ số chống ảo giác | Xem C.6 | P0 |
| Z4 | Dashboard chất lượng | `retrieval_ms`, `evidence_ready_ms`, `generation_ms`, tokens, cost, `fallback_reason`, abstention rate, các chỉ số L0–L7; không hiển thị chain-of-thought | P0 |
| Z5 | Audit | Append-only; ghi truy cập tài liệu, quyết định route, phê duyệt, thay đổi cấu hình, mở citation cũ; thời hạn lưu cấu hình (mặc định 2 năm) | P0 |
| Z6 | Backup/restore | Backup mã hóa, diễn tập khôi phục ra máy sạch | P0 |
| Z7 | Gói phân phối Windows | Core Pack, Model Pack manifest (id, sha256, license, revision, dimension, RAM/disk), Data Pack; demo cài sạch dưới 10 GB, đo trong CI | P0 |
| Z8 | RBAC + ABAC | Quyền theo role và thuộc tính (danh mục, mức mật); SYS_ADMIN không đọc nội dung mặc định | P0 |
| Z9 | Bảo mật nhập liệu | SSRF, MIME giả, prompt injection qua PDF/metadata, XSS từ PDF, CSP, rò rỉ ACL qua cache/tokenizer | P0 |

Calibration dùng chỉnh ngưỡng; regression dùng lặp trong phát triển; held-out và trap hold-out khóa quyền nội dung/đáp án đối với người tune, chỉ chạy sau khi khóa candidate/config ở đợt chốt. Manifest split bất biến theo revision và kiểm nhóm/trùng lặp ngữ nghĩa có người rà soát; chỉ trùng case ID bằng không chưa đủ. Nếu dùng kết quả held-out để sửa/tune, đánh dấu tập đó đã dùng và không báo là đánh giá độc lập của candidate sau; cần tập chưa xem mới. Corpus nguồn vẫn phải nằm trong chỉ mục benchmark để retrieval tìm được; không nhầm tách câu đánh giá với gỡ nguồn khỏi kho benchmark.

### C.11 Luồng sử dụng chính

**L-1. Hỏi lần đầu (USER).** Chọn danh mục → (tùy chọn) đổi ngày áp dụng → nhập tình huống → thấy FactChips và skeleton "Đang tìm căn cứ…" → thẻ căn cứ gộp hiện ra (Pha 1) → câu trung tính "Đã tìm thấy và kiểm tra nguồn của X căn cứ. Đang phân tích điều kiện áp dụng, hiệu lực, quy định chuyển tiếp và ngoại lệ…" → claims và nhãn trạng thái (Pha 2) → checklist độ phủ → gợi ý câu hỏi tiếp theo.

**L-2. Sửa dữ kiện.** Sửa một hay nhiều chip → hiện dải "Đã chỉnh sửa dữ kiện…" → bấm "Cập nhật dữ kiện & Tra cứu lại" → kết quả cũ gắn `stale` → kết quả mới thay thế.

**L-3. Mở căn cứ đã bị sửa đổi.** Bấm `[1]` → viewer mở đúng trang, highlight, banner cố định "Khoản này … đã được sửa đổi bởi … từ ngày …" → "Xem văn bản sửa đổi" mở PDF thay thế đúng trang và node → "Xem nội dung áp dụng tại ngày tra cứu".

**L-4. Hỏi nhanh bằng Chat Agent.** Bấm icon góc phải → panel trượt ra với phạm vi gợi ý theo trang → hỏi → thẻ căn cứ gọn → bấm căn cứ mở viewer → quay lại hội thoại → "Mở trang đầy đủ".

**L-5. Curator nạp tài liệu.** Upload PDF hoặc import URL (domain đã cho phép) → job chạy, thấy tiến độ → hàng đợi duyệt (theo rủi ro) → CURATOR lưu nháp node/metadata và đề xuất → REVIEWER duyệt tài liệu/phiên bản/metadata hiệu lực/quan hệ sửa đổi → snapshot hiệu lực publish.

**L-6. Admin thêm domain nguồn.** Quản trị → Domain cho phép → Thêm → nhập tên miền → hệ thống kiểm tra (DNS, HTTPS, không địa chỉ nội bộ) → xác nhận người xác minh + ghi chú → bật.

**L-7. Local Mode.** Quản trị đặt chế độ → chạy `verify-egress` → toàn bộ hỏi đáp, xem PDF chạy không Internet; mọi thao tác dùng model local; lỗi Local LLM ⇒ trả evidence đã verified kèm "Giải thích tạm thời không khả dụng", không gọi API.

**L-8. USER trên Windows.** Mở shortcut app → đăng nhập trong app → cửa sổ đăng nhập biến mất hoàn toàn → Orb tròn góc phải desktop → click mở chat/click lại thu → mở PDF hoặc workspace cùng phiên → thu về Orb không mất hội thoại → đăng xuất hoặc Thoát qua menu khay hệ thống. Không cần mở trình duyệt, không hiện cửa sổ console.

### C.12 Ứng dụng USER trên Windows và ranh giới portal

| Mã | Hành vi P0 | Nghiệm thu |
|---|---|---|
| W1 | Shell desktop Tauri 2 tái sử dụng User Portal/components/API/auth/RAG; Admin Portal là layout riêng | Một backend/DB/pipeline; không fork chatbot; client LAN kết nối server cấu hình, không tự cài một DB trên mỗi máy USER |
| W2 | Shortcut và đăng nhập trong app; endpoint backend lấy từ cấu hình triển khai | Hết phiên quay về đăng nhập; không tự mở browser; không hardcode host/port, không chiếm hoặc tắt dịch vụ lạ |
| W3 | Orb tròn, panel và login có trạng thái cửa sổ riêng; login/panel nền đục, chỉ vùng ngoài Orb trong suốt | Không còn khung login/ô vuông/bóng mờ dư; hit-test ngoài Orb không chặn app phía dưới |
| W4 | Click toggle; thu/mở, workspace và viewer giữ cùng session/turn/facts/revisions | Không nhân đôi lượt, không mất nháp; đóng panel chỉ thu Orb, không xóa phiên |
| W5 | Kéo/resize có vùng riêng, có thể tắt; nút và tiêu đề không bị vùng kéo che | Kéo không kích hoạt click mở/đóng; không có lớp kéo phủ composer/citation; khôi phục vị trí trong work area khi đổi DPI/màn hình |
| W6 | Khay hệ thống: Hiện/Ẩn trợ lý, Đăng xuất, Thoát; always-on-top là lựa chọn người dùng | Ẩn không đồng nghĩa đăng xuất; đăng xuất dừng stream, xóa state và secret phiên; Thoát không dừng backend LAN dùng chung |
| W7 | Phân tích/gợi ý/citation thật theo pipeline chung; stop/retry, trạng thái mất kết nối và chưa có model rõ | Không progress giả hoặc tự gắn nhãn AI cho template; bản native và web dùng cùng hợp đồng |
| W8 | Chữ và responsive đồng bộ User/Admin/desktop; UI USER không có upload kho, ingestion, quản lý user/model | Kiểm nhiều kích thước/DPI, bàn phím, contrast, reduced-motion; các quyền server vẫn được kiểm |

Web User Portal là bề mặt dùng cùng chức năng khi được triển khai; desktop là lối sử dụng chính của USER trên Windows. Admin Portal có Dashboard, Tài liệu, Danh mục, Ingestion/jobs, Tài khoản/quyền, Cấu hình AI, Monitoring/audit và Evaluation; mỗi module phải có màn hình hoặc trạng thái chưa có dữ liệu rõ ràng, không sidebar dẫn tới trang giả. Các vai trò quản trị chỉ thấy module được cấp quyền, không mặc định xem hội thoại riêng hoặc nội dung nghiệp vụ.
