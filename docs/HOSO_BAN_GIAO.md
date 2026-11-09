# HỒ SƠ BÀN GIAO TRIỂN KHAI — Vietnamese Evidence RAG Agent

> **[Không triển khai – xem ADR-010]** Mọi nội dung về bộ câu hỏi Gold, trap set, calibration và held-out trong tài liệu này không được triển khai theo [ADR-010](architecture-decisions/ADR-010-khong-trien-khai-bo-cau-hoi-gold.md). Phần còn lại giữ nguyên.

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
- **Không dùng bộ câu hỏi Gold để chấm AI (ADR-010)**: AI chỉ hỗ trợ, cán bộ chuyên môn quyết định. [Không triển khai – xem ADR-010]
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
| 3 | Gold [Không triển khai – xem ADR-010] v0 | 150–200 câu từ PDF văn bản chính thức thật. Agent soạn, người nắm nghiệp vụ duyệt; AI không tự công nhận. Calibration dùng chỉnh ngưỡng; held-out độc lập với chỉnh ngưỡng và dữ liệu huấn luyện; chia theo nhóm tình huống/câu diễn đạt lại, không chỉ theo case ID |
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
| §15.1, §16, §18 Sprint 1 | Gold [Không triển khai – xem ADR-010] v0 50–100 câu | 150–200 câu, tách tập calibration và held-out |
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
| Chia tập Gold [Không triển khai – xem ADR-010] | Đề xuất khoảng 30% calibration / 70% held-out, ghi ADR | Owner chốt |
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
| 5 | Chia Gold [Không triển khai – xem ADR-010] theo nhóm tình huống; regression dùng thường xuyên, held-out khóa đến đợt chốt | C.10, S11, WP 1.9/2.8/3.11 |
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

**Trap set** (đề xuất 40–60 câu, tách khỏi Gold [Không triển khai – xem ADR-010] v0): agent soạn từ PDF thật, người nắm nghiệp vụ duyệt. Gồm tiền đề sai, Điều không tồn tại, số hiệu gần giống, văn bản hết hiệu lực, hỏi vượt phạm vi, lệnh chèn trong PDF, yêu cầu bỏ qua nguồn, xin tư vấn vượt căn cứ. Ngưỡng chấp nhận do owner chốt sau baseline. Hồ sơ không tuyên bố loại bỏ hoàn toàn ảo giác; mục tiêu là đo được, giảm được và luôn nói rõ khi chưa đủ căn cứ.

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
| Z1 | Gold [Không triển khai – xem ADR-010] Dataset v0 | 150–200 câu từ PDF thật, reviewer duyệt. Mỗi case có căn cứ/phiên bản/ngày/source hash, `scenario_group_id` và `split_revision`; các câu diễn đạt lại hoặc cùng tình huống nằm cùng một split | P0 |
| Z2 | Benchmark B0–B7 và ablation | Chạy trên Gold [Không triển khai – xem ADR-010] đã duyệt; `ranx`/bootstrap; pin corpus hash, model/tokenizer revision; báo cáo có khoảng tin cậy | P0 |
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

---

## D. Thiết kế UX/UI chi tiết

Hướng thiết kế đã chốt: **Modern Enterprise / Evidence-First**, Light Theme mặc định, Navy + Blue + White + Slate. Đây là bảng màu của ứng dụng; không lấy bảng màu ChatGPT, demo DIL hay màu framework làm chuẩn. Dark Mode là P1.

### D.1 Nguyên tắc UX

1. **Căn cứ trước, lời giải thích sau.** Thứ người dùng thấy đầu tiên là nguyên văn nguồn và trang PDF; lời giải thích là lớp thứ hai.
2. **Nói rõ mình biết gì và chưa biết gì.** Mọi kết quả có phạm vi (danh mục, ngày áp dụng, ngày kho dữ liệu), nhãn trạng thái và checklist độ phủ. Không dùng phần trăm tự đánh giá, không dùng màu trang trí để tạo niềm tin.
3. **Màu không là tín hiệu duy nhất.** Mọi trạng thái có icon + nhãn chữ + mô tả theo ngày áp dụng.
4. **Người dùng giữ quyền sửa.** Dữ kiện AI suy ra luôn sửa được; câu hỏi nối tiếp hiện "Đang hiểu là…" để chỉnh; không hành động ngầm.
5. **Không làm mất bối cảnh.** Mở PDF, mở văn bản sửa đổi, mở trang đầy đủ đều giữ nguyên hội thoại và kết quả.
6. **Yên tĩnh, đọc được.** Một điểm nhấn là thẻ căn cứ nguyên văn; mọi thứ xung quanh trung tính. Không hiệu ứng nền, không gradient, không bóng đổ nặng. Chuyển động chỉ đáp lại thao tác của người dùng.
7. **Cùng một ngôn ngữ giao diện cho widget và trang đầy đủ.** Chung component, chung hợp đồng SSE, chung nhãn.
8. **Văn bản giao diện bằng tiếng Việt thuần, câu chủ động, viết thường đầu câu (sentence case)**, nút nêu đúng hành động ("Tra cứu", "Lưu nháp", "Duyệt"), cùng một hành động giữ cùng một tên xuyên suốt.

### D.2 Design system

**D.2.1 Màu — token chính thức (SRS §9.5)**

| Token CSS | HEX | Ứng dụng |
|---|---|---|
| `--color-brand-navy` | `#163A5F` | Sidebar, topbar, tiêu đề vùng quản trị, header panel Chat Agent, launcher |
| `--color-brand-navy-hover` | `#102B47` | Hover thanh Navy, launcher hover |
| `--color-action` | `#2563EB` | Nút tra cứu chính, link citation `[1]`, tab active, focus ring |
| `--color-action-hover` | `#1D4ED8` | Hover CTA |
| `--color-background` | `#F8FAFC` | Nền toàn app |
| `--color-surface` | `#FFFFFF` | Chat, Evidence Cards, PDF Viewer, modal |
| `--color-surface-muted` | `#F1F5F9` | Thẻ thông tin phụ, skeleton, tin nhắn người dùng |
| `--color-text-primary` | `#0F172A` | Nội dung chính và trích dẫn |
| `--color-text-secondary` | `#475569` | Metadata có ý nghĩa, breadcrumb |
| `--color-border` | `#CBD5E1` | Viền input, card, separator |
| `--color-evidence-bg` | `#EFF6FF` | Căn cứ được chọn/đang hiển thị trong viewer |
| `--color-evidence-text` | `#1E40AF` | Nhãn trích dẫn/evidence |
| `--color-success` | `#047857` | Kiểm chứng đạt, nguồn được phép dùng; luôn có icon/text |
| `--color-warning` | `#92400E` | Điều kiện chưa chắc, hiệu lực chưa đầy đủ |
| `--color-warning-bg` | `#FFFBEB` | Sticky Amendment Banner và temporal warning |
| `--color-danger` | `#B91C1C` | Lỗi, bãi bỏ, quyền bị chặn, citation không hợp lệ |
| `--color-danger-bg` | `#FEF2F2` | Vùng cảnh báo nghiêm trọng |

**Token bổ sung (đề xuất, phải qua contrast test; không đạt thì chỉnh token):**

| Token | Giá trị gợi ý | Dùng cho |
|---|---|---|
| `--color-success-bg` | `#ECFDF5` | Nền nhãn "Đã xác định căn cứ" |
| `--color-highlight-fill` | `rgba(37, 99, 235, 0.22)` | Tô span trích dẫn trên PDF (chỉ đúng vùng span, `mix-blend-mode: multiply`) |
| `--color-highlight-stroke` | `#2563EB` | Viền 2px quanh span đang chọn |
| `--color-dirty-bg` / `--color-dirty-border` | `#FFF7ED` / `#C2410C` | Chip đã chỉnh sửa, dải "Đã chỉnh sửa dữ kiện" (neutral/orange nhẹ) |
| `--color-overlay` | `rgba(15, 23, 42, 0.45)` | Nền modal |
| `--color-focus-ring` | `var(--color-action)` | Vòng focus 3px, offset 2px |

**Quy tắc dùng màu**

1. Topbar/Sidebar Navy; vùng đọc văn bản và Evidence Card nền trắng; toàn trang xám rất nhạt. Blue chỉ cho tương tác (link citation, nút "Tra cứu", focus), **không** dùng xanh để tuyên bố căn cứ đúng về pháp lý.
2. Trạng thái dirty dùng neutral/cam nhẹ; kết quả `stale` có nhãn chữ; skeleton trung tính, **không dùng xanh success trước khi claim được kiểm tra**.
3. Nền PDF trắng hoặc theo render gốc; không phủ màu lên nội dung PDF; highlight chỉ trên span được trích.
4. Tất cả màu đi qua CSS variables trong **một theme module**; cấm hardcode HEX trong component (lint rule). Mọi cặp màu/trạng thái có contrast test tự động (WCAG 2.2 AA: 4.5:1 chữ thường, 3:1 chữ lớn và thành phần giao diện).

**D.2.2 Chữ**

Họ chữ ưu tiên `Inter, system-ui, Arial, sans-serif`; fallback tương thích tiếng Việt có dấu. Local Mode không tải font ngoài: chỉ đóng gói Inter cục bộ sau khi kiểm license, nếu không dùng font hệ thống.

| Vai trò | Cỡ / line-height | Độ đậm | Ghi chú |
|---|---|---|---|
| Tiêu đề trang (h1) | 24 / 32 | 600 | Một cho mỗi màn hình |
| Tiêu đề khu vực (h2) | 20 / 28 | 600 | |
| Tiêu đề thẻ (h3) | 18 / 28 | 600 | |
| Nội dung giao diện | 14 / 20 | 400, nhãn 500 | Nút, bảng, chip |
| Nội dung đọc | 15 / 24 | 400 | Câu trả lời, giải thích |
| Trích dẫn nguyên văn và nội dung văn bản dài | 16 / 26 | 400 | line-height tối thiểu 1.5; dòng không quá khoảng 80 ký tự khi bố cục cho phép |
| Metadata có ý nghĩa | 13 / 18 | 400, `--color-text-secondary` | Số hiệu, ngày, breadcrumb; không dưới 13px |

**D.2.3 Khoảng cách, bo góc, độ nổi, lớp**

- Khoảng cách theo bước 4px: 4, 8, 12, 16, 24, 32, 48. Khoảng trong thẻ 16; giữa các khối trong câu trả lời 12–16; giữa các vùng 24.
- Bo góc: 6px (input, nút), 8px (thẻ căn cứ, bảng), 12px (panel Chat Agent, drawer, modal), tròn đầy (chip, launcher, huy hiệu). Không dùng một bán kính cho mọi thứ.
- Độ nổi: thẻ dùng viền 1px `--color-border`, không đổ bóng; chỉ panel nổi (`0 8px 24px rgba(15,23,42,0.16)`) và modal (`0 16px 40px rgba(15,23,42,0.24)`) có bóng.
- Lớp (z-index): nội dung 0 · header dính 10 · viewer drawer 30 · launcher và panel Chat Agent 40 · modal xác nhận 50 · toast 60. Modal xác nhận luôn nằm trên Chat Agent.

**D.2.4 Biểu tượng và chuyển động**

- Bộ icon đóng gói cục bộ (đề xuất `lucide`, giấy phép ISC; ghi vào manifest). Không dùng icon từ CDN.
- Chuyển động chỉ đáp lại thao tác: mở/đóng panel (160–200ms, trượt + mờ nhẹ), mở accordion, xác nhận. Không có animation tự chạy ngoài skeleton và chỉ báo "đang xử lý". Tôn trọng `prefers-reduced-motion` (tắt trượt, dùng hiện/ẩn tức thời).

### D.3 Kiến trúc thông tin và điều hướng

| Khu vực | Vai trò | Mục điều hướng |
|---|---|---|
| User Portal | USER hoặc quyền `rag.query` được cấp tường minh + scope tài liệu | Trang chủ Orb · Hỏi đáp/workspace · Lịch sử của tôi · Bộ nhớ của tôi · Theo dõi (P1) |
| Kho tài liệu | CURATOR, REVIEWER | Tài liệu · Hàng đợi duyệt · Quan hệ sửa đổi · Đề xuất của AI |
| Quản trị | SYS_ADMIN | Danh mục · Người dùng và quyền · Domain cho phép · Mô hình AI và chế độ · Cấu hình bộ nhớ |
| Chất lượng | CURATOR, REVIEWER, SYS_ADMIN | Bộ kiểm thử (Gold [Không triển khai – xem ADR-010], trap set) · Chạy benchmark · Dashboard |
| Kiểm toán | AUDITOR | Nhật ký · Bằng chứng truy cập |

- **Chat Agent (launcher góc phải) hiện ở mọi trang Tra cứu và Kho tài liệu (chế độ đọc)**; ẩn ở đăng nhập và thu nhỏ ở Curator Split-View.
- Mục điều hướng người dùng không có quyền **không hiển thị** (lọc từ server, không chỉ ẩn bằng giao diện).
- Vùng Tra cứu chỉ có thanh trên (Navy). Vùng quản trị và kho tài liệu thêm thanh bên trái (Navy, thu gọn được).

Route chuẩn: `/login` dùng chung; `/app/*` là User Portal; `/admin/*` là Admin Portal với layout/state/navigation riêng; `/` định tuyến theo quyền hoặc lựa chọn portal của tài khoản nhiều quyền. SYS_ADMIN không được mặc nhiên vào Tra cứu. Chuyển portal không nâng quyền và không chuyển nội dung hội thoại riêng sang màn hình quản trị. Desktop mở User Portal trong shell; route quản trị chỉ mở khi có quyền và thao tác tường minh.

### D.4 Bố cục chung và đáp ứng kích thước

| Điểm ngắt | Bố cục |
|---|---|
| ≥ 1280px | Hỏi đáp: hai vùng — cột trái "Hỏi và căn cứ" (khoảng 5/12) và PDF Viewer (khoảng 7/12); tách kéo được. Split-View: hai nửa bằng nhau |
| 768–1279px | Một cột hỏi/căn cứ; PDF Viewer mở thành drawer phải rộng ~70% màn hình |
| < 768px | Một cột; PDF Viewer và Chat Agent mở toàn màn hình có nút quay lại; thao tác chính đặt ở vùng dễ chạm (≥ 44×44px) |

Panel + viewer chỉ đặt cạnh nhau nếu vùng khả dụng đủ `panel_width + viewer_min_width + gap + safe_areas`; `viewer_min_width=480px` và gap 16px là token cấu hình ban đầu. Không áp “viewer 60% + panel 380px” vô điều kiện ở tablet. Thiếu chỗ: viewer thay vùng nội dung panel hoặc mở toàn khung với “Quay lại hội thoại”; giữ phiên/scroll, không chồng hai vùng tương tác. Bề rộng thực tế và zoom quyết định chuyển layout, không chỉ tên breakpoint.

Thanh trên (topbar) của trang Hỏi đáp: logo/tên hệ thống · **Danh mục ▼** · **Loại tài liệu ▼** · **Ngày áp dụng** (mặc định "Hôm nay" kèm ngày cụ thể) · huy hiệu chế độ chỉ đọc (**API Mode** hoặc **Local Mode · offline**) · menu người dùng. Khi `as_of_date` khác hôm nay, ô ngày chuyển sang kiểu nhấn (viền cam nhẹ + nhãn "Tra cứu theo ngày quá khứ").

### D.5 Màn hình chi tiết

#### S1. Hỏi đáp (trang đầy đủ)

Mục đích: hỏi, thấy căn cứ trước, đọc phân tích, mở nguồn.

```text
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ Evidence RAG  [Danh mục ▼] [Loại tài liệu ▼] [Ngày áp dụng: 21/10/2026 ▼] [Local Mode]  │ Navy
├───────────────────────────────────────────────┬─────────────────────────────────────────┤
│ [Trả lời] [Phân tích] [Liên quan]              │ PDF VIEWER (S2)                          │
│                                               │ Số hiệu · Cơ quan · Version · Hash       │
│ Phạm vi: Danh mục X · Ngày áp dụng 21/10/2026 │ Chương > Điều 5 > Khoản 2                │
│ · Kho dữ liệu cập nhật 20/10/2026             │ ┌──────────────────────────────────────┐ │
│                                               │ │ ⚠ Khoản này đã được sửa đổi bởi …    │ │ sticky
│ ┌ Mô tả tình huống hoặc hỏi về Điều, Khoản… ┐ │ │   từ ngày … — Xem văn bản sửa đổi    │ │
│ └───────────────────────────────  [Tra cứu] ┘ │ └──────────────────────────────────────┘ │
│                                               │   …nội dung PDF…                         │
│ Dữ kiện: [Đối tượng ✎] [Thời điểm ✎]          │   [ĐOẠN ĐƯỢC TÔ SÁNG]                   │
│          [Hồ sơ ✎ chưa xác nhận]              │                                          │
│ ▸ Đã chỉnh sửa dữ kiện — kết quả bên dưới dựa │ ‹ Trang 12/48 ›  Tìm trong văn bản       │
│   trên dữ kiện trước đó [Cập nhật dữ kiện &   │ Bản hiện hành │ Bản tại ngày …           │
│   Tra cứu lại]                                │ Liên kết trang công bố chính thức        │
│                                               │                                          │
│ ● Có điều kiện — cần xác minh thêm hiệu lực   │                                          │
│ CĂN CỨ  [Quy định chính][Điều kiện][Ngoại lệ] │                                          │
│  [1] Điều 5 khoản 2 · số hiệu … · bản 3        │                                          │
│      “…nguyên văn 2–3 dòng…”  [Mở trong PDF]  │                                          │
│  [2] …                                        │                                          │
│ PHÂN TÍCH CÓ DẪN CHỨNG                         │                                          │
│  • Nhận định … [1][2]                          │                                          │
│ THÔNG TIN CÒN THIẾU  [Ngày xảy ra sự việc] …   │                                          │
│ ĐÃ KIỂM TRA  ✔ Nguồn  ✔ Trích dẫn  ⚠ Hiệu lực │                                          │
│ CÂU HỎI TIẾP THEO  (chip) (chip)               │                                          │
│ Sao chép kèm phạm vi · Phản hồi                │                                          │
│ Kết quả hỗ trợ tra cứu và tham mưu, không …    │                                          │
└───────────────────────────────────────────────┴─────────────────────────────────────────┘
```

Thứ tự khối trong tab **Trả lời**: phạm vi → ô hỏi → dữ kiện → dải "đã chỉnh sửa" (nếu có) → nhãn trạng thái → căn cứ gộp theo vai trò → phân tích có dẫn chứng → thông tin còn thiếu → checklist độ phủ → câu hỏi tiếp theo → hành động và lưu ý.

Tab **Phân tích** (A1, A3, A4, A5): bảng "Điều kiện áp dụng" (đã thỏa / chưa xác minh / ngoại lệ / mốc thời gian / hệ quả nêu trong văn bản, mỗi dòng có `[n]`), danh sách điểm cần lưu ý, so sánh phiên bản của Điều đang xem. Tab **Liên quan** (A6, A10): văn bản hướng dẫn, văn bản sửa đổi, tham chiếu đến/từ node đang xem, chuỗi sửa đổi.

Trạng thái:

| Trạng thái | Hiển thị |
|---|---|
| Trống | Ô hỏi và 3 ví dụ cách hỏi (chip): "Hỏi theo Điều/Khoản", "Mô tả một tình huống", "So sánh với quy định cũ". Không dữ liệu giả |
| Chưa chọn danh mục | Ô hỏi bị khóa; ghi chú "Chọn danh mục để bắt đầu"; chip danh mục được tô nhấn |
| Pha 1 đang chạy | Skeleton trung tính (`--color-surface-muted`) + "Đang tìm căn cứ trong danh mục đã chọn…" |
| Pha 1 xong | Thẻ căn cứ hiện; dòng "Đã tìm thấy và kiểm tra nguồn của X căn cứ. Đang phân tích điều kiện áp dụng, hiệu lực, quy định chuyển tiếp và ngoại lệ…" |
| Pha 2 xong | Claims, nhãn trạng thái, checklist đầy đủ |
| Không đủ căn cứ | Nhãn "Thiếu căn cứ" + giải thích + gợi ý hỏi lại + (nếu có) các căn cứ gần nhất đã kiểm tra, ghi rõ "chưa trả lời được câu hỏi" |
| Tiền đề sai (L0) | "Không có [Điều X] trong [văn bản]. Văn bản này có Điều 1 đến Điều N." |
| Sinh giải thích lỗi | Giữ căn cứ hợp lệ + "Giải thích tạm thời không khả dụng. Các căn cứ bên dưới đã được kiểm tra nguồn." |
| Snapshot hiệu lực stale | Dải cảnh báo: "Dữ liệu hiệu lực đang được cập nhật. Chưa thể khẳng định hiệu lực tại ngày này." |
| Kết quả cũ (`stale`) | Nhãn "Kết quả dựa trên dữ kiện trước đó" cho tới khi có kết quả mới |
| Lỗi mạng/máy chủ | Thông báo nêu việc gì thất bại và nút "Thử lại"; không xóa nội dung đã nhập |

#### S2. PDF Viewer

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ ‹ Quay lại   Tên văn bản · Số hiệu · Cơ quan · Bản 3 ▼ · Hash 9f3a…   ⤓ ↗  │ toolbar
│ [Đang áp dụng ✔ tại 21/10/2026]  (nhãn hiệu lực của node đang xem)         │
├────────────────────────────────────────────────────────────────────────────┤
│ ⚠ Khoản này trên PDF gốc đã được sửa đổi bởi [văn bản] từ ngày [ngày]      │ sticky
│   [Xem văn bản sửa đổi] [Xem nội dung áp dụng tại ngày tra cứu]  ▾ thu gọn │
├────────────────┬───────────────────────────────────────────────────────────┤
│ MỤC LỤC        │                                                           │
│ ▸ Chương I     │   …trang PDF gốc…                                         │
│ ▾ Chương II    │   ┌─ Điều 5 ─ …                                          │
│   ▾ Điều 5     │   │ 2. [đoạn được tô sáng] ◂ huy hiệu "Đã sửa đổi"         │
│     Khoản 1    │   └────────────────────────────────────────────────────── │
│   ● Khoản 2    │                                                           │
├────────────────┴───────────────────────────────────────────────────────────┤
│ ‹ Trang 12 / 48 ›   Tìm trong văn bản [          ]   Bản hiện hành │ Bản tại ngày … │
└────────────────────────────────────────────────────────────────────────────┘
```

- Toolbar luôn hiện nhãn hiệu lực của node đang xem (thu gọn banner không làm mất nhãn này).
- Mục lục dựng từ DB (`document_nodes`); click nhảy PDF; node đang xem có dấu ● và `aria-current`.
- Highlight: nền `--color-highlight-fill`, viền `--color-highlight-stroke`; chỉ vùng span được trích. Cuộn tự động tới span.
- **Fallback khi bbox không tin cậy:** mở đúng trang, hiện ngăn "Đoạn trích để đối chiếu" bên cạnh, kèm dòng "Chưa tô sáng chính xác vị trí đoạn này trên trang."
- Bản tại ngày: chọn version; PDF cũ vẫn xem nguyên, kèm banner.
- Nút tải PDF chỉ hiện khi có quyền. Link "Trang công bố chính thức" chỉ hiện khi curator đã xác minh.
- Điện thoại: toàn màn hình; mục lục thành ngăn kéo; toolbar rút gọn thành tiêu đề + menu.

#### S3. Chat Agent (widget góc phải)

**Launcher.** Nút tròn 56px, nền `--color-brand-navy`, icon hội thoại màu trắng; cách mép phải và mép dưới 24px (16px trên điện thoại) cộng safe-area; hover `--color-brand-navy-hover`; focus: vòng 3px `--color-focus-ring` cách 2px. Tooltip "Hỏi về văn bản". `aria-label="Mở trợ lý tra cứu"`. Huy hiệu tròn 12px viền trắng: xanh action = có phản hồi mới; cam (`--color-warning`) = có kết quả cần kiểm lại. Không tự bật, không tự mở.

**Panel (web/khung desktop).** Rộng mong muốn 420px (≥1280) hoặc 380px (768–1279), luôn clamp trong work area/safe-area; cao tối đa `min(720px, 100vh − 96px)`, bo 12px. Orb vẫn là điều khiển toggle có nhãn đúng trạng thái, click lần nữa thu panel. Shell native theo S14, không tạo thêm ô vuông hoặc cửa sổ nền quanh Orb.

```text
                                   ┌──────────────────────────────────────┐
                                   │ Trợ lý tra cứu        ⤢  ▁  ✕        │ Navy
                                   ├──────────────────────────────────────┤
                                   │ [Danh mục X ▼] [21/10/2026 ▼] [Local]│ thanh phạm vi
                                   │ Đang hiểu là: “…câu đã viết lại…” ✎  │ (khi hỏi nối tiếp)
                                   │ [Trả lời] [Phân tích] [Liên quan]    │
                                   ├──────────────────────────────────────┤
                                   │                    ┌───────────────┐ │
                                   │                    │ câu hỏi của tôi│ │
                                   │                    └───────────────┘ │
                                   │ ● Có điều kiện                       │
                                   │ ┌ [1] Điều 5 khoản 2 · số hiệu … ──┐ │
                                   │ │ “…nguyên văn…”      [Mở trong PDF]│ │
                                   │ └───────────────────────────────────┘ │
                                   │ Nhận định có dẫn chứng … [1]         │
                                   │ Còn thiếu: (Ngày xảy ra sự việc)     │
                                   │ Hỏi tiếp: (…) (…)                    │
                                   │ Sao chép kèm phạm vi · Phản hồi      │
                                   ├──────────────────────────────────────┤
                                   │ ┌ Mô tả tình huống hoặc hỏi Điều… ┐  │
                                   │ └────────────────────── [Tra cứu] ┘  │
                                   │ Hỗ trợ tra cứu, không thay quyết định │
                                   └──────────────────────────────────────┘
                                                                     (◉) launcher
```

Nút ở header: **⤢ Mở trang đầy đủ** (giữ phiên) · **▁ Thu nhỏ** (về launcher, giữ trạng thái) · **✕ Đóng**.

**Hành vi**

- Mở bằng launcher hoặc phím tắt cấu hình được (mặc định không gán phím tắt toàn cục để tránh xung đột; owner có thể bật). `Esc` đóng panel khi focus ở trong; focus trở về launcher.
- Trạng thái phiên giữ ở server; chuyển trang trong ứng dụng không làm mất hội thoại.
- Bấm `[n]` hoặc "Mở trong PDF": đủ chỗ theo D.4 thì viewer cạnh panel; thiếu chỗ ở tablet/cửa sổ hẹp thì chuyển một khung có “Quay lại hội thoại”. Không che citation/composer bằng panel khác; ở native ưu tiên workspace cùng phiên khi cần đọc PDF rộng.
- Tin nhắn người dùng: căn phải, nền `--color-surface-muted`. Câu trả lời của trợ lý: khối trắng có viền, **không dùng bong bóng chat**; các khối bên trong theo đúng thứ tự ở S1 nhưng thẻ căn cứ ở dạng gọn (số hiệu, Điều/Khoản/Điểm, 2 dòng trích, nút mở).
- Hỏi nối tiếp: hiện dải "Đang hiểu là: …" (có nút sửa); thiếu điều kiện then chốt thì hỏi lại **một** câu bằng chip lựa chọn.
- Kết quả cũ sau khi snapshot đổi: nhãn "Cần kiểm lại" kèm nút "Tra cứu lại với dữ liệu mới"; launcher có huy hiệu cam.
- Không có nút phê duyệt hay thực hiện nghiệp vụ.
- Chế độ không lưu: biểu tượng khóa trong header và dòng "Hội thoại này sẽ không được ghi nhớ."
- Có nút “Dừng” khi đang chạy; dừng chỉ lượt hỏi đáp, không ảnh hưởng tác vụ quản trị. “Thử lại” sau lỗi là run mới có chủ ý; hiển thị kết quả cũ là lượt trước và không nhân đôi lời hỏi.

**Điện thoại:** panel toàn màn hình (bottom sheet cao 100%), header dính, composer dính đáy theo `visualViewport` để bàn phím không che.

**Trạng thái đặc biệt**

| Trạng thái | Hiển thị |
|---|---|
| Lần đầu | Lời chào ngắn + 3 chip ví dụ cách hỏi; không bài giới thiệu dài |
| Chưa chọn danh mục | Thanh phạm vi tô nhấn, composer khóa kèm lý do |
| Mất kết nối | "Mất kết nối tới máy chủ. Nội dung bạn nhập vẫn được giữ." + Thử lại |
| Local Mode, model local lỗi | Căn cứ đã kiểm tra vẫn hiện; "Giải thích tạm thời không khả dụng"; **không** chuyển sang API |
| Không có quyền | "Chưa tìm thấy tài liệu được phép truy cập." (không tiết lộ tài liệu tồn tại) |

#### S4. Danh sách tài liệu và hồ sơ tài liệu (CURATOR/REVIEWER)

```text
┌ Tài liệu ──────────────────────────────────────────────────────────────────┐
│ [Tìm theo số hiệu, tiêu đề]  [Danh mục ▼] [Loại ▼] [Trạng thái ▼]          │
│                                   [Tải PDF lên]  [Nhập từ URL]              │
├────────────────────────────────────────────────────────────────────────────┤
│ Tiêu đề / số hiệu │ Loại │ Cơ quan │ Danh mục │ Phiên bản │ Trạng thái │ ⋯ │
│ …                                                                          │
└────────────────────────────────────────────────────────────────────────────┘
```

- Cột **Trạng thái tài liệu**: Nháp · Chờ duyệt · Đã duyệt · Tạm đình chỉ · Đã thay thế · Hết hiệu lực · Chưa rõ (icon + chữ). Cột **Hiệu lực node** tóm tắt: "Có N node chưa xác minh".
- **Tải PDF lên:** hỗ trợ chọn nhiều PDF cùng lúc (`multiple`); cho phép khai báo thông tin metadata độc lập từng văn bản (tiêu đề, số hiệu, URL nguồn chính thức, ngày ban hành); cơ chế gửi tuần tự từng tệp vào `POST /api/v1/admin/documents/upload` để tránh quá tải bộ xử lý PDF; hiển thị tiến độ `Đang nhập tệp n/tổng…`, trạng thái riêng biệt cho từng tệp (`ready`, `uploading`, `success`, `failed`, `unknown`), nút "Dừng nhập tệp" (`AbortController`), và nút "Thử lại các tệp chưa thành công"; kiểm tra trùng lặp 2 tầng (chặn trùng byte SHA-256 mã 409 `DUPLICATE_PDF_HASH`, cảnh báo trùng nội dung chữ NFC `possible_duplicate_content` kèm danh sách tối đa 5 bản nháp/nguồn đối chiếu).
- **Nhập từ URL:** ô nhập; nếu tên miền không có trong danh sách: "Tên miền này chưa nằm trong danh sách cho phép. Nhờ quản trị viên thêm tên miền sau khi xác minh." Không có nút bỏ qua.
- Trang hồ sơ tài liệu có tab: **Thông tin** (metadata chuẩn, nguồn, hash, nút "Mở trang công bố chính thức" nếu đã xác minh) · **Phiên bản** · **Cây điều khoản** · **Quan hệ** (sửa đổi/tham chiếu) · **Lịch sử** (audit).
- Danh sách chỉ hiện tài liệu người dùng có quyền (lọc server).

#### S5. Hàng đợi duyệt (risk-prioritized)

Bảng: **Tài liệu và phiên bản · Lý do vào hàng đợi · Rủi ro · Người phụ trách · Hạn · Trạng thái**.

- Lý do: Độ tin cậy parse thấp · Nhảy khoản · Chuyển mã font · Tọa độ trang lệch · Hiệu lực chưa duyệt · Đề xuất của AI.
- Rủi ro: **Cao / Trung bình / Thấp** hiển thị bằng icon + chữ (không chỉ màu), mặc định xếp Cao lên trước.
- Bộ lọc theo lý do, rủi ro, người phụ trách. Hành động hàng loạt chỉ cho việc **gán người phụ trách**; duyệt luôn từng mục.
- Hàng trống: "Không có mục chờ duyệt. Tài liệu mới nạp sẽ xuất hiện ở đây."

#### S6. Curator Split-View

```text
┌ Tài liệu X · bản 3 · Mục 4/17 trong hàng đợi │ Đã lưu nháp 14:32 │ Revision 8 ─────────┐
├───────────────────────────────────────┬───────────────────────────────────────────────┤
│ PDF.js — bản bất biến                 │ [Cây node] [Hiệu lực] [Quan hệ] [Đề xuất của AI]│
│ [Trang 12 ▼]  tô sáng span đang chọn  │ ▾ Chương II                                   │
│                                       │   ▾ Điều 5                                     │
│   …trang PDF…                         │     ● Khoản 2  (độ tin cậy parse: thấp)        │
│   [span]                              │ ─ Form node ──────────────────────────────────│
│                                       │ Nhãn [Khoản 2]  Vị trí [5.2]                   │
│                                       │ Hiệu lực từ [..] đến [..]  Trạng thái [Chưa rõ]│
│                                       │ Quan hệ sửa đổi [+ Thêm]                       │
│                                       │              [Bỏ qua]  [Lưu nháp]  [Duyệt]     │
└───────────────────────────────────────┴───────────────────────────────────────────────┘
```

- Click node → PDF nhảy tới span; click vào PDF → focus node tương ứng; điều khoản chưa có node → mở tác vụ "Phân tích lại trang".
- **Lưu nháp tự động** (chỉ báo "Đã lưu nháp") khác **Duyệt**: Duyệt dùng endpoint riêng, role REVIEWER, kiểm `If-Match`/revision; xung đột revision thì hiện "Mục này vừa được người khác sửa. Tải lại để xem thay đổi."
- Phím tắt (đi tiếp/lùi node) **vô hiệu khi đang nhập văn bản**; không có phím tắt duyệt.
- Duyệt thay đổi hiệu lực hoặc quan hệ sửa đổi: hộp thoại xác nhận: "Thay đổi này ảnh hưởng cách hệ thống trả lời với các ngày từ [ngày]. Hành động được ghi nhật ký." — nút "Duyệt" / "Quay lại".
- Tab **Đề xuất của AI** (C1): mỗi đề xuất có loại, span nguồn, độ tin cậy dạng nhãn, nút **Chấp nhận vào nháp / Sửa / Từ chối**. Accept của CURATOR chỉ lưu nháp và audit; phê duyệt tài liệu/hiệu lực/amendment qua REVIEWER và endpoint riêng, không publish ngầm. Thao tác hàng loạt cần xác nhận.
- Chat Agent thu nhỏ ở màn hình này (không che form).

#### S7. Danh mục (SYS_ADMIN/CURATOR)

Cây danh mục kéo thả, độ sâu cấu hình; cột: Tên · Mã cố định · Người phụ trách · Quyền xem · Số tài liệu · Trạng thái (Hoạt động/Ẩn/Đã xóa). Hành động: Thêm · Sửa · Ẩn · Xóa mềm · Khôi phục · Nhập/Xuất JSON/CSV (có bước kiểm tra trước khi áp dụng). Xóa mềm nêu rõ: "Tệp gốc và embedding vẫn được giữ nếu tài liệu còn thuộc danh mục khác." Cấm tạo vòng lặp: báo lỗi ngay tại ô chọn danh mục cha.

#### S8. Domain cho phép (SYS_ADMIN)

Bảng: **Tên miền · Người xác minh · Ngày xác minh · Ghi chú · Trạng thái (Bật/Tắt) · Lần dùng gần nhất**. Nút **Thêm tên miền** mở trình hướng dẫn 3 bước: (1) nhập tên miền → hệ thống kiểm tra DNS, HTTPS, không phải địa chỉ nội bộ; (2) xác nhận người xác minh và ghi chú nguồn; (3) bật. Mọi thay đổi có audit. Tắt một tên miền: cảnh báo "Các lần nhập mới từ tên miền này sẽ bị chặn."

#### S9. Mô hình AI và chế độ vận hành (SYS_ADMIN)

- **Chế độ:** hai thẻ **API Mode** và **Local Mode** hiển thị trạng thái hiện hành, điều kiện cần (với Local Mode: kết quả `verify-egress`, model local sẵn sàng). Đổi chế độ cần xác nhận và ghi audit.
- **Model Registry:** bảng Provider · Endpoint · Model · Capability (chip: Phân tích/Chat · Embedding · Rerank · Sinh · OCR) · Vùng riêng tư · Trạng thái · Chi phí/định mức · [Kiểm tra kết nối]. Khóa API chỉ nhập một lần, hiển thị dạng che, không đọc lại.
- **Stage routes:** ma trận Stage × (API Mode, Local Mode) chọn model; fallback chỉ cùng vùng riêng tư; cảnh báo nếu stage Local Mode trỏ vào model không chạy local.
- Form cấu hình API gồm adapter/provider được hỗ trợ, endpoint, model ID, tham số và secret nhập một lần; form Local gồm runtime/endpoint nội bộ được duyệt, artifact/model ID, revision và tham số. Có trạng thái “Chưa cấu hình”, “Chưa kiểm tra”, “Sẵn sàng”, “Lỗi”; không điền sẵn một model/key/host bắt buộc. Kiểm tra kết nối chỉ bằng dữ liệu tổng hợp và vẫn theo egress policy.
- Runtime/model local chọn bằng manifest ID hoặc đường dẫn tương đối trong root cài đã kiểm; server resolve/kiểm containment theo B.8. API/LAN endpoint vẫn là cấu hình endpoint có policy; không cho form trở thành lối đọc/chạy file tùy ý ngoài root.
- **Chính sách theo danh mục:** công tắc "Cho phép xử lý bằng AI từ xa" mặc định **Tắt**; bật cần xác nhận kèm cảnh báo về dữ liệu được gửi ra ngoài.
- Không hiển thị chain-of-thought của model ở bất kỳ đâu.

#### S10. Bộ nhớ của tôi (USER)

Các khối: **Chế độ không lưu** (công tắc) · **Hội thoại gần đây** (danh sách; xem tóm tắt, xóa từng phiên) · **Sở thích** (opt-in: danh mục mặc định, phạm vi hay dùng) · **Thời hạn lưu** (chỉ đọc, do quản trị đặt) · **Xóa tất cả bộ nhớ**. Văn bản giải thích ngắn: "Bộ nhớ giúp trợ lý hiểu câu hỏi nối tiếp. Câu trả lời luôn lấy căn cứ lại từ kho tài liệu." Xóa tất cả cần xác nhận và là xóa thật.

#### S11. Bộ kiểm thử: duyệt Gold [Không triển khai – xem ADR-010] và trap set (REVIEWER/chuyên gia nghiệp vụ)

```text
┌ Bộ kiểm thử · Gold v0 · Đã duyệt 62 / 180 · Calibration 54 │ Held-out 126 (khóa) ───┐
├──────────────────────┬──────────────────────────────────────────────────────────────┤
│ Danh sách case       │ Case G-0073                                                   │
│ [lọc: Chưa duyệt ▼]  │ Câu hỏi: …                          Ngày áp dụng: …           │
│ G-0071 ✔ Đã duyệt    │ Căn cứ do agent đề xuất: số hiệu · Điều/Khoản/Điểm · bản       │
│ G-0072 • Chưa duyệt  │ “…đoạn trích…”  [Mở trong PDF]                                 │
│ G-0073 • Chưa duyệt  │ Đáp án mẫu (agent soạn): …                                    │
│ …                    │ Loại: [Trực tiếp ▼]  Có cần trả lời "không đủ căn cứ"? [ ]    │
│                      │ [Duyệt]  [Yêu cầu sửa + ghi chú]  [Loại bỏ case]              │
└──────────────────────┴──────────────────────────────────────────────────────────────┘
```

- Mỗi case có trạng thái **Nháp → Đã duyệt / Cần sửa / Loại bỏ**, người duyệt, thời điểm. **Chỉ case Đã duyệt tính vào chuẩn.**
- Người duyệt luôn thấy đoạn nguồn gốc và mở được PDF; không có nút "duyệt tất cả".
- Tập held-out khóa cả API lẫn giao diện đối với người tune; case/đáp án không nằm trong log benchmark của họ. Hiện `scenario_group_id`, `split_revision` và trạng thái candidate đã khóa; chỉ đánh giá cuối sau khi freeze cấu hình. Tập đã dùng để quyết định sửa/tune không tiếp tục được gọi là held-out độc lập.
- Trap set có tab riêng cùng cách duyệt.

#### S12. Dashboard chất lượng (SYS_ADMIN, REVIEWER)

Thẻ số liệu và biểu đồ theo thời gian: `retrieval_ms`, `evidence_ready_ms`, `first_claim_ms`, `final_answer_ms` (P50/P95, đường theo thời gian); tỷ lệ từ chối đúng/sai; `unsupported_claim_rate`, `wrong_doc_rate`, `wrong_node_rate`, `false_premise_detection_rate`, `validator_reject_rate`; tiến độ duyệt Gold [Không triển khai – xem ADR-010] (đã duyệt/mục tiêu 150–200); lịch sử chạy benchmark với bộ lọc theo model/tokenizer/corpus hash. Mỗi số liệu ghi **môi trường đo và thời điểm**; không hiển thị số khi chưa có dữ liệu (hiện "Chưa có số đo").

#### S13. Đăng nhập, quyền và trang lỗi

- Đăng nhập cục bộ; không dùng dịch vụ ngoài (captcha, font, analytics). Sai mật khẩu: "Tên đăng nhập hoặc mật khẩu không đúng." Khóa tạm sau nhiều lần sai, nêu thời gian chờ.
- Không có quyền vào một trang: "Bạn chưa có quyền vào mục này." (không gợi ý mục đó chứa gì).
- 404/500: nêu việc gì xảy ra, mã tham chiếu để báo quản trị, nút về trang chủ.

#### S14. Shell desktop USER

Tái sử dụng S3 (chat), S1 (workspace), S2 (viewer), S10 (bộ nhớ) và S13 (đăng nhập); không nhân bản workflow. Chuỗi trạng thái: `SIGNED_OUT → LOGIN → ORB ↔ PANEL ↔ WORKSPACE`; mất phiên quay về LOGIN, mất mạng giữ draft và trạng thái lỗi rõ.

- **Login:** cửa sổ nền đục, chữ dễ đọc, không trong suốt. Đăng nhập thành công đóng/ẩn hẳn khung login trước khi hiện Orb; không để bóng mờ hoặc bề mặt tương tác dư phía sau.
- **Orb:** hình tròn 56–64px, nền/vùng hit-test khớp hình; không hình tròn trong hình vuông, không khung viền/bóng cửa sổ ngoài. Mở/thu bằng click lặp; nếu bật kéo, phân biệt drag với click và không bắt sự kiện ngoài Orb.
- **Panel/workspace:** nền đục theo theme; vùng kéo riêng không đè tên trợ lý, nút hoặc text; vùng resize ở cạnh/góc riêng, kích thước tối thiểu và clamp work area. Không yêu cầu cửa sổ trong suốt cho nội dung đọc.
- **Vị trí:** lấy work area, DPI và màn hình từ platform API; nhớ lựa chọn vị trí/kích thước theo user nếu cho phép, không lưu nội dung hội thoại vào local storage. Sau đổi màn hình/DPI, đưa cửa sổ về vùng nhìn thấy.
- **Khay hệ thống:** Hiện/Ẩn trợ lý, Đăng xuất, Thoát; có điều khiển tương đương trong app cho người dùng bàn phím. Đóng panel thu về Orb; Ẩn tạm chỉ còn tray; Thoát kết thúc client, không dừng server LAN.
- **Cài đặt:** shell/helper/runtime desktop dùng dependency-manifest dưới root cấu hình `E:\Programs` theo B.8; Không hardcode PATH/LLM trong frontend, shell hoặc helper; lấy executable/model từ cấu hình/manifest, không dựa vào PATH toàn cục hoặc cài tool ngầm vào hồ sơ user.
- **Bật/tắt luôn trên cùng:** là sở thích user, mặc định OFF; không chặn cửa sổ đăng nhập/modal hệ thống. Không mở cửa sổ console/cmd khi chạy app hoặc helper nền.
- **Luồng chung:** mở đầy đủ/PDF/thu lại không mất session; backend là nguồn trạng thái hội thoại, state trình bày tách khỏi dữ liệu nghiệp vụ. Không giả lập AI khi model chưa cấu hình; không trộn User/Admin.

### D.6 Thư viện component

Tất cả component dùng chung design tokens và có story/test trạng thái.

| Component | Trạng thái và thuộc tính chính | Trợ năng |
|---|---|---|
| `AppShell`, `TopBar`, `SideNav` | Thu gọn/mở; mục theo quyền | Landmark `banner`/`navigation`/`main`; skip link |
| `ScopeBar` (`CategorySelect`, `DocTypeSelect`, `AsOfDatePicker`, `ModeBadge`) | `as_of_date` quá khứ có nhấn; badge chỉ đọc | Nhãn đầy đủ cho từng điều khiển |
| `QueryComposer` | Rỗng, đang nhập, đang gửi, khóa (chưa chọn danh mục); Enter gửi, Shift+Enter xuống dòng | `aria-describedby` lý do khóa |
| `FactChip` | `user_confirmed` (nét liền), `extracted_unconfirmed` (nét đứt + "chưa xác nhận"), `inferred_uncertain` (nét chấm + "suy đoán"); đang sửa; đã chỉnh (dirty) | Nút sửa/xóa có nhãn; thông báo thay đổi qua `aria-live` |
| `DirtyFactBar` | Hiện khi có chip dirty; nút "Cập nhật dữ kiện & Tra cứu lại" bật khi hợp lệ | Vai trò `status` |
| `ResultStatus` | 4 nhãn + "Chưa tìm thấy tài liệu được phép truy cập" (D.7) | Icon + chữ |
| `EvidenceGroupTabs` | Tab theo vai trò (chỉ hiện tab có thẻ) | Mẫu tabs WAI-ARIA |
| `EvidenceCard` | Thu gọn (2–3 dòng) / mở rộng; chọn; nhãn "Nguồn ngoài danh mục"; `EffectiveBadge`; `stale` | Nút "Mở trong PDF" có tên đầy đủ |
| `CitationLink` (`[n]`) | Hover xem trước 2 dòng; mở viewer; kiểm quyền khi mở | Văn bản thay thế "Căn cứ n: [số hiệu, Điều…]" |
| `CoverageChecklist` | Mỗi mục: Đạt / Chưa đạt / Chưa xác minh; thu gọn "Đã kiểm tra 3/4" | Danh sách có văn bản trạng thái |
| `ClaimItem` | Có `[n]`; trạng thái claim; "chưa xác minh" | Gắn kết claim–căn cứ qua `aria-describedby` |
| `MissingInfoChips`, `FollowUpChips` | Bấm để điền/hỏi; tối đa số chip cấu hình | Nút thật, không phải thẻ `div` |
| `AnalysisTable` (A1) | Hàng: điều kiện · trạng thái (đã thỏa/chưa xác minh/ngoại lệ) · căn cứ `[n]` | Bảng có tiêu đề cột |
| `NoteHighlights` (A4) | Bật/tắt tô nổi trong thẻ và viewer | Công tắc có nhãn |
| `VersionDiff` (A5) | Cạnh nhau/đan xen; chú thích thêm/bớt bằng ký hiệu + chữ | Không chỉ màu |
| `RelatedList` (A6) | Nhóm: văn bản hướng dẫn · sửa đổi · tham chiếu đến · tham chiếu từ; nhãn "chưa duyệt" | Danh sách có cấp |
| `PdfViewer`, `PdfToolbar`, `ArticleTree` | Tải, lỗi, fallback; mục lục thu gọn | Điều hướng bàn phím; `aria-current` |
| `AmendmentBanner` | `modified`, `repealed`, `suspended`, `not_yet_effective`, `unknown`; thu gọn nhưng nhãn còn ở toolbar | Vai trò `alert` khi mở; chữ + icon |
| `TwoPhaseSkeleton` | Pha 1, chuyển Pha 2 | `aria-busy`, thông báo phase |
| `StaleLabel`, `StaleResultOverlay` | Nhãn trên kết quả cũ | `aria-live` polite |
| `FeedbackDialog` | 4 loại + ghi chú | Quản lý focus |
| `CopyWithScope` | Sao chép gồm phạm vi, ngày áp dụng, cảnh báo | Thông báo "Đã sao chép" |
| `AgentLauncher`, `AgentPanel` | Đóng, mở, thu nhỏ, toàn màn hình; huy hiệu | Xem D.9 |
| `DesktopShell`, `DesktopWindowControls`, `TrayMenu` | Login/Orb/Panel/Workspace, kéo/resize, DPI, hiện/ẩn/đăng xuất/thoát | Vùng kéo riêng; menu/nút bàn phím; native không làm mất focus |
| `MemoryCenter`, `SessionMemoryDrawer` | Khối ở S10 & ngăn kéo bộ nhớ phiên RAM: danh sách facts/items, số lượng badge, nút Dừng/Thử lại lượt, xóa từng mục, xóa toàn bộ RAM, công tắc "Lưu vào sở thích tra cứu" | Nhãn công tắc rõ; vai trò status cho các cập nhật |
| `DataTable`, `ReviewQueueTable` | Sắp xếp, lọc, trống, lỗi; phân trang | Tiêu đề cột `scope`; hàng có thể chọn bằng bàn phím |
| `CuratorSplitView`, `NodeForm` | Draft/duyệt, xung đột revision | Phím tắt chỉ khi không ở ô nhập |
| `AiSuggestionPanel` | Chấp nhận/Sửa/Từ chối, lý do từ chối | Nhãn độ tin cậy dạng chữ |
| `ConfirmDialog` | Mô tả hậu quả cụ thể, nút nêu đúng hành động | Modal; trả focus |
| `JobProgress` | Chờ, chạy, cần duyệt, lỗi, hủy, xong | Thanh tiến độ có văn bản |
| `AllowlistTable`, `DomainWizard` | 3 bước, kiểm tra | |
| `ModelRegistryTable`, `ModeCard` | Bảng cấu hình AI Provider/Model: adapter, endpoint (hỗ trợ LAN/localhost), model ID, params (temperature, max_tokens, json_mode), secret_ref (lọc blacklist), in-place update | Mask key; cảnh báo route sai; kiểm tra kết nối (probe) |
| `MetricTile`, `LatencyChart` | Có dữ liệu / "Chưa có số đo" | Biểu đồ kèm bảng dữ liệu thay thế |
| `GoldReviewList`, `GoldCaseView` | Nháp/Đã duyệt/Cần sửa/Loại; held-out khóa | |
| `EmptyState`, `ErrorState`, `Toast` | Nêu hành động tiếp theo | `role="status"` / `alert` |

### D.7 Nhãn và trạng thái chuẩn

**Kết quả hỏi đáp**

| Nhãn | Icon | Màu | Khi nào |
|---|---|---|---|
| Đã xác định căn cứ | check-circle | `--color-success` trên `--color-success-bg` | Nguồn, hiệu lực, điều kiện áp dụng được kiểm theo quy tắc và đủ độ phủ |
| Có điều kiện | alert-triangle | `--color-warning` trên `--color-warning-bg` | Còn điều kiện, ngoại lệ hoặc hiệu lực chưa xác minh |
| Thiếu căn cứ | file-search | `--color-text-secondary` trên `--color-surface-muted` | Không đủ căn cứ để trả lời |
| Nguồn xung đột | alert-octagon | `--color-danger` trên `--color-danger-bg` | Các nguồn nói khác nhau, cần người có thẩm quyền xác minh |
| Chưa tìm thấy tài liệu được phép truy cập | lock hoặc search | trung tính | Không có tài liệu trong quyền; không tiết lộ tồn tại |

**Hiệu lực node theo ngày áp dụng**

| `amendment_state` | Nhãn tiếng Việt | Icon | Màu |
|---|---|---|---|
| `active` | Đang áp dụng tại [ngày] | check-circle | success |
| `modified` | Đã sửa đổi từ [ngày] | file-pen | warning |
| `repealed` | Đã bãi bỏ từ [ngày] | ban | danger |
| `suspended` | Tạm đình chỉ | pause-circle | warning |
| `not_yet_effective` | Chưa có hiệu lực | clock | evidence (xanh dương nhạt) |
| `unknown` | Hiệu lực chưa xác minh | help-circle | trung tính |

Khi `as_of_date` trước ngày sửa đổi, dùng câu: "Quy định được thay đổi từ [ngày] (sau ngày tra cứu). Cần xem quy định chuyển tiếp." Không nói bản cũ chắc chắn không áp dụng.

**Mục checklist độ phủ**

| Mục | Nhãn hiển thị |
|---|---|
| `source_verified` | Nguồn và trích dẫn đã kiểm tra |
| `effective_checked` | Hiệu lực tại ngày áp dụng |
| `applicability_checked` | Điều kiện áp dụng |
| `claim_supported` | Nhận định có căn cứ hỗ trợ |
| `transition_checked` | Quy định chuyển tiếp |
| `required_facts_complete` | Dữ kiện bắt buộc |
| `scope_expansion` | Mở rộng ngoài phạm vi đúng chính sách |

Mỗi mục có 3 trạng thái: **Đạt** (check) · **Chưa đạt** (x) · **Chưa xác minh** (help). Mặc định hiển thị thu gọn "Đã kiểm tra X/Y mục", mở rộng được.

API hiện hành dùng các tên checklist ở bảng trên và enum `passed / failed / unknown`; không dùng boolean để ép “chưa xác minh” thành false. `effective_status_checked`/`node_effective_checked` là tên cũ, không phát từ API v1.3. `claim_supported=passed` đòi hỏi đủ kiểm tra hỗ trợ đã định nghĩa; chỉ pass số liệu/phủ định không được coi là chứng minh ngữ nghĩa của nhận định.

**Công việc ingest:** Chờ · Đang đọc trang · Phân tích cấu trúc · Cần duyệt · Lỗi · Đã hủy · Xong. **Đề xuất AI:** Đề xuất · Đã chấp nhận · Đã từ chối · Hết hạn. **Gold [Không triển khai – xem ADR-010] case:** Nháp · Đã duyệt · Cần sửa · Loại bỏ.

### D.8 Nội dung giao diện (microcopy)

Nguyên tắc: tiếng Việt thuần, câu chủ động, nêu đúng việc sẽ xảy ra; lỗi nêu **chuyện gì đã xảy ra và cách xử lý**, không xin lỗi chung chung; trạng thái rỗng dẫn tới hành động tiếp theo.

| Ngữ cảnh | Nội dung |
|---|---|
| Placeholder ô hỏi | "Mô tả tình huống hoặc hỏi về một Điều, Khoản…" |
| Nút gửi | "Tra cứu" |
| Nút sau khi sửa dữ kiện | "Cập nhật dữ kiện & Tra cứu lại" |
| Dải dirty | "Đã chỉnh sửa dữ kiện — kết quả bên dưới dựa trên dữ kiện trước đó" |
| Skeleton pha 1 | "Đang tìm căn cứ trong danh mục đã chọn…" |
| Pha 2 | "Đã tìm thấy và kiểm tra nguồn của [X] căn cứ. Đang phân tích điều kiện áp dụng, hiệu lực, quy định chuyển tiếp và ngoại lệ…" |
| Câu đã hiểu | "Đang hiểu là: “…”" + nút "Sửa" |
| Thiếu căn cứ | "Chưa đủ căn cứ để trả lời. Các tài liệu được phép truy cập chưa có quy định phù hợp với câu hỏi này." |
| Không tìm thấy/không quyền | "Chưa tìm thấy tài liệu được phép truy cập." |
| Tiền đề sai | "Không có [Điều X] trong [tên văn bản]. Văn bản này có Điều 1 đến Điều [N]." |
| Giải thích lỗi | "Giải thích tạm thời không khả dụng. Các căn cứ bên dưới đã được kiểm tra nguồn." |
| Snapshot stale | "Dữ liệu hiệu lực đang được cập nhật. Chưa thể khẳng định hiệu lực tại ngày này." |
| Kết quả cũ | "Kết quả dựa trên dữ kiện trước đó" · "Cần kiểm lại vì dữ liệu hiệu lực đã thay đổi" |
| Fallback viewer | "Chưa tô sáng chính xác vị trí đoạn này trên trang." |
| Banner sửa đổi | "Khoản này trên PDF gốc đã được sửa đổi/bãi bỏ bởi [văn bản] từ ngày [ngày]." + "Xem văn bản sửa đổi" |
| Hiệu lực chưa rõ | "Hiệu lực chưa xác minh. Hệ thống chưa kết luận khoản này còn hay hết hiệu lực." |
| Nguồn ngoài danh mục | "Nguồn ngoài danh mục đã chọn" |
| Sao chép | "Sao chép kèm phạm vi" → thông báo "Đã sao chép, kèm phạm vi và cảnh báo." |
| Lưu ý cuối kết quả | "Kết quả hỗ trợ tra cứu và tham mưu, không thay thế quyết định của người có thẩm quyền." |
| Phản hồi | "Căn cứ sai" · "Thiếu căn cứ" · "Văn bản hết hiệu lực" · "Trích dẫn sai đoạn" |
| Domain bị chặn | "Tên miền này chưa nằm trong danh sách cho phép. Nhờ quản trị viên thêm tên miền sau khi xác minh." |
| Xung đột revision | "Mục này vừa được người khác sửa. Tải lại để xem thay đổi." |
| Xác nhận hiệu lực | "Thay đổi này ảnh hưởng cách hệ thống trả lời với các ngày từ [ngày]. Hành động được ghi nhật ký." → "Duyệt" / "Quay lại" |
| Xóa bộ nhớ | "Xóa toàn bộ bộ nhớ của bạn? Hành động này không hoàn tác." → "Xóa bộ nhớ" / "Giữ lại" |
| Chế độ không lưu | "Hội thoại này sẽ không được ghi nhớ." |
| Bộ nhớ (giải thích) | "Bộ nhớ giúp trợ lý hiểu câu hỏi nối tiếp. Câu trả lời luôn lấy căn cứ lại từ kho tài liệu." |
| Danh mục trống | "Danh mục chưa có tài liệu đã duyệt. Nhờ người phụ trách nạp tài liệu." |
| Mất kết nối | "Mất kết nối tới máy chủ. Nội dung bạn nhập vẫn được giữ." + "Thử lại" |
| Huy hiệu Local Mode | "Local Mode · offline" (tooltip: "Mọi xử lý chạy trên máy chủ nội bộ, không gửi dữ liệu ra ngoài.") |
| Huy hiệu API Mode | "API Mode" (tooltip: "Chỉ dữ liệu được chính sách cho phép mới được gửi tới nhà cung cấp AI.") |

Cấm dùng trong giao diện: "Đã khóa X căn cứ xác thực", "Đã xác minh X căn cứ" (khi chưa chứng minh hiệu lực và độ phủ), phần trăm độ chính xác, "chắc chắn", "AI đảm bảo".

### D.9 Trợ năng và hiệu năng giao diện

**Trợ năng (WCAG 2.2 AA tối thiểu)**

- Mọi chức năng thao tác được bằng bàn phím; thứ tự focus theo thứ tự đọc; focus luôn nhìn thấy (3px, offset 2px).
- Chat Agent: launcher là `button`; panel là `role="dialog"` **không modal** (`aria-modal="false"`) khi docked, `aria-labelledby` tới tiêu đề; mở panel chuyển focus vào ô nhập; `Esc` đóng và trả focus về launcher; không bẫy focus trừ khi toàn màn hình trên điện thoại; luồng stream nằm trong vùng `aria-live="polite"`, chỉ thông báo mốc quan trọng (đã có căn cứ, đã có kết quả), không đọc từng token.
- Mục tiêu chạm ≥ 44×44px trên điện thoại; hỗ trợ zoom tới 200% mà không mất chức năng; không cuộn ngang ở 320px.
- Màu không là tín hiệu duy nhất; biểu đồ có bảng dữ liệu thay thế.
- `prefers-reduced-motion` tắt chuyển động trượt/mờ.
- Nội dung tiếng Việt có dấu hiển thị đúng; thuộc tính `lang="vi"`; copy văn bản kèm nguồn.

**Hiệu năng giao diện**

- Launcher gần như không tốn tải trang: bundle panel, PDF viewer, biểu đồ **tải lười** (code-splitting); prefetch khi hover launcher hoặc khi nhập vào ô hỏi.
- PDF viewer dựng theo trang (virtualized), chỉ render trang đang xem và lân cận; prefetch trang được trích khi hover `[n]`.
- Danh sách dài (tài liệu, hàng đợi, case Gold [Không triển khai – xem ADR-010]) dùng phân trang hoặc cuộn ảo.
- Local Mode: không tải tài nguyên từ bên ngoài (CDN, font, analytics, telemetry).
- Ngân sách tải trang đo trước/sau khi thêm widget (WP 4.7); không tuyên bố số trước khi đo.

### D.10 Kiểm thử giao diện (bắt buộc)

- **Snapshot ảnh** cho: trạng thái hiệu lực (`active/modified/repealed/suspended/not_yet_effective/unknown`), nhãn kết quả (4 + không tìm thấy), FactChip (3 loại + dirty), Sticky Amendment Banner (mở/thu gọn), EvidenceCard, panel Chat Agent (đóng/mở/thu nhỏ/điện thoại), skeleton hai pha, fallback viewer.
- **Contrast test tự động** cho mọi cặp màu/trạng thái (token); không đạt thì chỉnh token.
- **Lint** cấm HEX cứng trong component.
- **Kiểm tra trợ năng tự động** (axe hoặc tương đương) trên mọi màn hình + kiểm thủ công bàn phím/screen reader cho S1, S3, S6.
- **E2E**: luồng L-1 đến L-7 (C.11); Local Mode không phát sinh request ra ngoài; chuyển trang giữ hội thoại; mở citation cũ kiểm lại quyền.
- **Nội dung**: test chuỗi cấm ở D.8 không xuất hiện trong bundle.
- **Desktop USER:** kiểm thực tế login → Orb → chat → PDF/workspace → thu/mở → tray → logout/exit; Orb tròn không nền vuông/bóng dư, nền login/panel đục, vùng kéo không đè chữ, resize được, không console. Kiểm DPI 100/125/150/200%, đổi màn hình/work area, zoom 200%, các bề rộng 320/768/1024/1280px và thu/mở không mất nội dung.

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
| Bộ kiểm thử | `GET /api/v1/admin/evaluation/cases` · `POST /api/v1/admin/evaluation/cases/{id}/review` · `GET /api/v1/admin/evaluation/splits` | Duyệt Gold [Không triển khai – xem ADR-010]/trap set; xem tách calibration/held-out |
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
| Duyệt Gold [Không triển khai – xem ADR-010]/trap | REVIEWER/chuyên gia được chỉ định | Chỉ xác nhận case đã đọc nguồn; không cấp quyền tune held-out |
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
| 1 | Kho tài liệu, hiệu lực node, ERD (kể cả bộ nhớ), frontend nền, Gold [Không triển khai – xem ADR-010] v0 | Import → parse → review → approve → snapshot chạy trên PDF thật; resolver qua đủ ca; Gold v0 (150–200 câu) được người nắm nghiệp vụ duyệt; tokens + contrast test xanh |
| 2 | Retrieval, evidence-first, chống truy xuất sai, A4–A6, baseline hiệu năng | BFS 2-hop vs full-chain; pre-gate 3 trạng thái; stale snapshot; B0–B7 có số đo thật; `wrong_doc_rate`/`wrong_node_rate`; baseline hiệu năng; C1 tầng quy tắc |
| 3 | Model Router, Local/API Mode, claims, UI hai pha, Chat Agent, bộ nhớ, phân tích và gợi ý P0 | Hai chế độ API/Local chạy được (Local kiểm trên máy ngắt Internet thật); regression polarity/numeric/temporal xanh; widget, bộ nhớ, trap set đạt ngưỡng owner chốt; A1–A3 |
| 4 | Hardening, hiệu năng, đóng gói Windows, P1 owner chọn | Red-team (bộ nhớ, prompt injection, rò rỉ ACL); hồi quy hiệu năng; restore thành công trên máy sạch; footprint trong trần demo |

### F.3 Quyết định mặc định

Dùng bảng B.6. Agent không dừng chờ các điểm đó; ghi ADR khi chọn khác.

### F.4 Luồng làm việc và phụ thuộc

Bảy luồng: **A** DB/ACL/hiệu lực · **B** Ingestion/Parsing · **C** Retrieval/Eval · **D** Validator/Workflow · **E** Model Router · **F** Frontend · **G** Nền tảng/CI.

- Sprint 0 kiểm khả thi trên Windows và các cấu hình đại diện; POC chọn thư viện/runtime tương thích, không cố định provider/model. Profile B chỉ chứng minh lõi offline; các gate AI/local model còn thiếu phải được báo riêng.
- A (schema) chặn B, C, D. B (nodes + span) chặn C và hiển thị viewer. Resolver hiệu lực (A) chặn validator hiệu lực (D).
- Gold [Không triển khai – xem ADR-010] v0 (C) chạy song song từ đầu Sprint 1 nhưng cần PDF thật từ Sprint 0 và người duyệt.
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

### F.6 Sprint 1 — Kho tài liệu, hiệu lực node, Gold [Không triển khai – xem ADR-010] v0

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
| 1.9 | **Gold [Không triển khai – xem ADR-010] v0 150–200 câu** (thay chỉ tiêu 50–100) từ PDF văn bản chính thức thật. Agent tự đọc PDF, soạn câu hỏi, đáp án tham chiếu và căn cứ; mỗi câu có số hiệu văn bản, điều/khoản/điểm, đoạn trích, phiên bản, thời điểm áp dụng khi liên quan, source URL/hash. Phủ: hỏi trực tiếp, tình huống nhiều điều kiện, ngoại lệ, văn bản sửa đổi (kể cả chuỗi A→B→C→D), chuyển tiếp, văn bản bãi bỏ, không đủ căn cứ, ngoài ACL, lời thường, không dấu, số hiệu viết tắt, PDF font lỗi. Agent tự kiểm cấu trúc, trích dẫn (quote khớp `text_original`) và phát hiện trùng lặp. Tách calibration và held-out theo scenario_group_id; các câu diễn đạt lại/cùng tình huống không chia sang hai tập; tỷ lệ đề xuất khoảng 30/70 là theo số case nhưng không phá nhóm. Regression vận hành tách khỏi held-out; manifest/corpus/split revision được khóa trước tuning. Màn hình duyệt S11 | Mỗi case có trạng thái draft → reviewed bởi người nắm nghiệp vụ; **chỉ case đã duyệt được dùng làm chuẩn**; AI không tự công nhận đáp án; báo cáo trùng lặp và kiểm trích dẫn đạt trên mọi case; script kiểm case ID, scenario_group_id, paraphrase/tình huống gần trùng giữa calibration và held-out; freeze split_revision trước tuning; corpus tách khỏi kho nghiệp vụ; fixture UI ở `synthetic_ui_fixtures` |

**Gate S1:** import → parse → review → approve → snapshot chạy thông trên PDF thật; resolver qua đủ ca ở WP 1.7; Gold [Không triển khai – xem ADR-010] v0 (150–200 câu) đã được người nắm nghiệp vụ duyệt; tokens + contrast test xanh.

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
| 2.11 | Định tuyến văn bản, lọc metadata, khử trùng phiên bản, `retrieval_diagnostics` (L0–L2) | Đo `wrong_doc_rate`/`wrong_node_rate` trên Gold [Không triển khai – xem ADR-010]; có ablation |
| 2.12 | Retrieval hints do curator duyệt + alias expansion có audit | Gợi ý chưa duyệt không ảnh hưởng xếp hạng |
| 2.13 | Baseline hiệu năng, tính trước lúc index, connection pool | Báo cáo P50/P95 theo stage trên máy đích |
| 2.14 | Quy tắc điểm cần lưu ý (A4), diff xác định (A5), đồ thị liên quan (A6) | Test trên PDF thật; diff khớp text đã duyệt; A6 không lộ node ngoài ACL |
| 2.15 | Bộ phát hiện đề xuất cho curator tầng quy tắc: quan hệ sửa đổi, tham chiếu chưa giải, node bất thường (C1 a, b, d) | Precision/recall trên tập nhãn lấy từ PDF thật, curator duyệt tập nhãn |

**Gate S2 (release-gate, không phải P1):** BFS 2-hop vs full-chain resolver; pre-gate 3 trạng thái; snapshot stale + worker lỗi; Gold [Không triển khai – xem ADR-010] v0 chạy B0–B7 (chỉ case đã duyệt; đánh giá cuối trên held-out) có số đo thật; baseline hiệu năng; `wrong_doc_rate`/`wrong_node_rate`; A4–A6 và C1 tầng quy tắc.

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
| 4.1 | Bộ test bảo mật/hồi quy: ACL qua cache và `as_of_date`, cross-scope, prompt injection, XSS từ PDF, CSP, KV cache isolation (nếu có local LLM), PDF mojibake, curator thiếu approval, zero-answer | Mọi bug từ feedback có gold [Không triển khai – xem ADR-010] test tái hiện |
| 4.2 | Tải và backpressure: concurrency gate cho CPU LLM, job position, cancel; test 30–60 session; đo `evidence_ready_ms` P50/P95 tách khỏi `final_answer_ms`; so parallel vs serial vs CTE dưới tải | Số đo ghi kèm môi trường; evidence-first vẫn hiện khi inference kẹt |
| 4.3 | Đóng gói cho Windows (installer, dịch vụ Windows): Core Pack, Model Pack manifest (id, sha256, license, revision, dimension, RAM/disk), Data Pack; demo cài sạch **< 10 GB** kiểm trong CI; báo dung lượng Core/Model/PostgreSQL/data riêng; installer đặt mọi công cụ/tool/runtime cần cài dưới `E:\Programs` bằng cấu hình triển khai, gồm cache/store do dự án quản lý | `measure-footprint` chạy trong CI; không PyTorch/full ML extras mặc định; preflight root/quyền/dung lượng; inventory real path đúng root; không PATH/LLM hardcode, không cài global/AppData/Program Files hoặc âm thầm đổi ổ |
| 4.4 | Backup mã hóa + restore máy sạch; retention audit/bộ nhớ/backup, sổ yêu cầu xóa mới nhất, SBOM/license/runbook offline/API và client desktop; runbook ghi root cài, dependency-manifest và cách nạp cấu hình; dữ liệu/backup theo cấu hình riêng | Restore có dữ liệu mẫu đã xóa: áp sổ xóa trước mở dịch vụ, không phục hồi nội dung vào history/cache; thiếu đối soát thì chưa mở truy cập. Cấu hình endpoint/path qua môi trường triển khai; secret do người vận hành nhập/khôi phục theo chính sách, không chép secret từ máy cũ; restore/reinstall giữ đúng root cài công cụ; không chép đường dẫn máy cũ vào source hoặc tự di chuyển dữ liệu |
| 4.5 | Gold [Không triển khai – xem ADR-010] mở rộng vượt v0 (150–200 câu) **khi có reviewer**; P1 (PyVi, BM25 re-score, ParadeDB, HNSW, ONNX INT8, KV prefix) chỉ mở nếu benchmark/ADR chứng minh | Không bật mặc định khi chưa qua non-regression |
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
- **Độ đúng của căn cứ:** người nắm nghiệp vụ duyệt đáp án mẫu Gold [Không triển khai – xem ADR-010] v0 (150–200 câu) và trap set trước khi dùng làm chuẩn; CURATOR xử lý nháp/hints; REVIEWER phê duyệt tài liệu, metadata hiệu lực và quan hệ sửa đổi có tác động đến căn cứ.
- **Quyền truy cập:** phê duyệt chính sách remote AI theo từng category (API Mode); ai được thấy Chat Agent theo role; ánh xạ quyền với app quản lý cán bộ nếu tích hợp.
- **Bảo mật và riêng tư:** admin xác minh và duyệt từng domain đưa vào allowlist; xác nhận cấu hình Local Mode và việc ngắt Internet ở hạ tầng mạng; chốt thời hạn lưu mặc định của bộ nhớ hội thoại và loại dữ liệu được phép lưu.
- **Ngưỡng chấp nhận:** owner chốt ngưỡng cho các chỉ số chống ảo giác và mục tiêu độ trễ sau khi có baseline; chọn tính năng P1 nào làm trước (C.5); curator quyết định chấp nhận hoặc từ chối từng đề xuất của AI.
- **Xác nhận giả định ở B.6**, đặc biệt: người dùng có được tự chọn chế độ hay không, tỷ lệ chia Gold [Không triển khai – xem ADR-010], kích thước trap set.
- **Cung cấp (không phải phê duyệt):** máy Windows đích để đo footprint, latency, backup/restore.

### F.12 Rủi ro chính

| Rủi ro | Cách xử lý trong plan |
|---|---|
| pgvector gặp vấn đề trên Windows | WP 0.2; ADR đề xuất cách khắc phục trên Windows (bản build, cách biên dịch) trước khi bàn đổi kiến trúc |
| Chặn kết nối ở ứng dụng không thay được ngắt mạng thật | WP 0.7, 3.2; agent cung cấp egress guard và rule firewall mẫu; việc ngắt Internet ở hạ tầng do người vận hành bảo đảm |
| Model embedding/reranker Việt không chạy ONNX hoặc vướng license | WP 0.4; profile B không cần LLM/dense |
| PDF cũ lỗi font, bbox lệch khi xoay/CropBox | WP 0.3, 1.5; fallback trang + quote, không tô sai |
| Chuỗi sửa đổi thiếu văn bản trong kho | Resolver báo `temporal_unknown`, không khẳng định "không sót sửa đổi" |
| Gold [Không triển khai – xem ADR-010] 150–200 câu cần nhiều thời gian duyệt của người nắm nghiệp vụ | Agent soạn đủ trích dẫn và tự kiểm trước; duyệt theo lô; case chưa duyệt không tính vào chuẩn; báo rõ số case đã duyệt |
| Dùng lẫn Gold [Không triển khai – xem ADR-010] với chỉnh ngưỡng gây đánh giá thiên lệch | Tách calibration và held-out, script kiểm không giao nhau |
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
- Gold [Không triển khai – xem ADR-010]: kiểm split theo nhóm tình huống, nội dung held-out không được dùng để tune; ghi candidate/config/corpus/split revision.

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
> Tuân thủ B.3/B.7/B.8 và SRS §25: CURATOR nháp, REVIEWER duyệt; cache analysis/retrieval OFF đến khi đủ fingerprint và test; incognito chỉ RAM, retention + opt-in mới lưu; xóa dẫn xuất/cache/job, restore áp sổ xóa; Gold [Không triển khai – xem ADR-010] 150–200 case người nắm nghiệp vụ duyệt, split theo nhóm tình huống, regression tách held-out; llm_attempt_budget=2 tính cả timeout/retry/fallback, summary P0 bằng code. Scope là SELECTED hoặc ALL_AUTHORIZED, server luôn kiểm ACL; SSE dùng query_id/run_id/revisions/sequence, retry tường minh không trộn lượt.
> 
> AI tự dựng ERD/migration/test DB và làm tối đa phần kỹ thuật kiểm chứng được; chỉ cần người quyết các nguyên tắc nghiệp vụ, quyền truy cập, bảo mật và độ đúng căn cứ. Không tự công nhận Gold [Không triển khai – xem ADR-010], không bịa văn bản pháp lý, không thêm dependency bị cấm, không dùng kết quả cũ làm bằng chứng hiện tại. Thiếu key/model/reviewer/thiết bị thì báo đúng gate còn thiếu và làm tiếp việc độc lập. Kết thúc mỗi WP báo cáo F.10, có số đo/môi trường và mục CHƯA XONG.

### G.2 Danh sách file bàn giao

| File | Vai trò |
|---|---|
| `01_HOSO_BAN_GIAO_Vietnamese_Evidence_RAG_Agent.md` | Hồ sơ này: tính năng, UX/UI, API, plan, prompt |
| `02_Vietnamese_Evidence_RAG_Agent_SRS_v1_3.md` | SRS kỹ thuật hiện hành, gồm §25 |
| `03_ADR_000_QUYET_DINH_BAN_GIAO.md` | Ghi nhận quyết định, mặc định và ranh giới nghiệm thu |
| `02_Vietnamese_Evidence_RAG_Agent_SRS_v1_2_1.md` | Bản lịch sử giữ nguyên, không dùng làm yêu cầu hiện hành |

### G.3 Từ điển ngắn

**as_of_date:** ngày áp dụng của tra cứu. **Evidence:** đoạn nguồn đã kiểm chứng kèm vị trí. **Node:** một đơn vị của văn bản (Chương/Mục/Điều/Khoản/Điểm). **Snapshot hiệu lực:** kết quả đã tính của chuỗi sửa đổi, publish nguyên tử theo revision. **Fail-closed:** khi không chắc thì chặn/từ chối thay vì cho qua. **Held-out:** tập đánh giá không dùng để chỉnh ngưỡng. **Dry-run retrieval:** chạy thử truy xuất để kiểm một gợi ý có căn cứ trong quyền người dùng hay không.
