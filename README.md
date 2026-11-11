# Vietnamese Evidence RAG Agent

**Ngôn ngữ / Language:** Tiếng Việt · [English](README.en.md)

Tra cứu văn bản hành chính, nghiệp vụ của cơ quan bằng tiếng Việt, có căn cứ nguồn. Một backend
FastAPI, một PostgreSQL và một kho tài liệu bất biến theo SHA-256 phục vụ **User Portal** (hỏi
đáp, tìm kiếm văn bản),
**Admin Portal** và **ứng dụng Windows USER (Tauri 2)**. Trạng thái hiện hành:
[`docs/implementation-status.md`](docs/implementation-status.md).

## Tải ứng dụng (cho giám khảo)

- **Gói:** `Evidence-RAG-Portable-20261111-r4.zip` (~3,52 GiB, 3.777.436.554 byte; gồm tài liệu và model AI cục bộ). Giải nén bằng 7-Zip hoặc trình giải nén của Windows.
- **Tải về:** https://drive.google.com/file/d/1C9bSKqt_7Rwuqe5NqtTZNzhABVqd7dj6/view?usp=sharing
- **SHA-256:** `989848708e2c1cd3be0d4a0e8978737bc03201f6c75415a37f2a434806636ed8` (kiểm: `Get-FileHash .\Evidence-RAG-Portable-20261111-r4.zip -Algorithm SHA256`)
- **Cấu hình tối thiểu:** Windows 10 / Server 2016 trở lên (x64), RAM khoảng 8 GB, trống 6 GB đĩa (theo `deploy/lan-portable/README.txt`; model AI chạy bằng CPU).
- **Khuyến nghị (đã thử):** Intel Core i3, RAM DDR4 32 GB, SSD 512 GB.
- **Khởi động:** giải nén TOÀN BỘ gói bằng WinRAR hoặc 7-Zip vào thư mục có đường dẫn ngắn (không chạy trong tệp nén), bấm đúp `Start-Server.bat`, chờ cửa sổ in địa chỉ dạng `http://<IP LAN>:8800/` rồi mở bằng trình duyệt. Lần đầu mất thêm 1-3 phút. Dừng bằng `Stop-Server.bat`. Chi tiết: [`deploy/lan-portable/README.txt`](deploy/lan-portable/README.txt) (tiếng Anh: [`README.en.txt`](deploy/lan-portable/README.en.txt)).
- **Tài khoản thử:** thông tin đăng nhập demo nằm trong file tài khoản `Acount_Demo.md` ở thư mục gốc của gói zip. `chuyenvien` tra cứu được ngay. Để thử quy trình đầy đủ, admin cấp cho `curator` các danh mục tra cứu, cấp cho `reviewer` cả danh mục tra cứu và danh mục xác nhận hiệu lực (**Tài khoản & Phân quyền**). Gói r4 đã cấp sẵn cả 9 danh mục cho hai tài khoản này; admin có thể sửa tại đó. Người dùng không thể tự duyệt bản do chính mình gửi duyệt.
## Phát triển bằng Kiro (Kiroween 2026)

Dự án được phát triển bằng Kiro (Claude Sonnet 5.5 và Claude Opus 5.5) từ 30/10/2026 đến hết 11/11/2026, theo xác nhận của chủ dự án.

- Bằng chứng và giới hạn: [`KIRO_WORK_SUMMARY.vi.md`](KIRO_WORK_SUMMARY.vi.md), [`PROJECT_TIMELINE.vi.md`](PROJECT_TIMELINE.vi.md), phụ lục thống kê từng tệp [`KIRO_STATS_APPENDIX.vi.md`](KIRO_STATS_APPENDIX.vi.md)
- Tổng quan kiến trúc: [`docs/vi/ARCHITECTURE_OVERVIEW.md`](docs/vi/ARCHITECTURE_OVERVIEW.md)
- Specs (10 nhóm), steering và hooks của Kiro: [`.kiro/`](.kiro/). Được dựng lại từ mã nguồn ngày 09/11/2026, không phải spec lịch sử của Kiro. Bản dịch tiếng Việt: [`docs/vi/kiro/`](docs/vi/kiro/README.vi.md)
- MCP của Kiro: **Stitch** – thiết kế UI, kết quả trong [`.stitch/`](.stitch/) (máy chủ cấu hình ở mức người dùng; chủ dự án xác nhận đã dùng, không có nhật ký lệnh gọi: bằng chứng loại B, xem [`KIRO_WORK_SUMMARY.vi.md`](KIRO_WORK_SUMMARY.vi.md) mục 7)

## Chạy cục bộ

Công cụ, runtime và dữ liệu dev nằm dưới `E:\Programs\EvidenceRAG` (truyền qua
`-ProgramsRoot` hoặc `EVIDENCE_PROGRAMS_ROOT`).

```powershell
$env:EVIDENCE_BOOTSTRAP_PASSWORD = "<mật khẩu khởi tạo, chỉ cần ở lần chạy đầu>"
.\scripts\start-local-stack.ps1 -ProgramsRoot E:\Programs -LaunchDesktop
```

Script khởi động PostgreSQL `127.0.0.1:55432`, backend `127.0.0.1:8000`
(`/health`), web `127.0.0.1:1420` và (tùy chọn) ứng dụng desktop.

Lần chạy đầu trên DB trống, `scripts/seed_local_runtime.py` tạo một danh mục thử và bốn
tài khoản dùng mật khẩu `EVIDENCE_BOOTSTRAP_PASSWORD`, bắt buộc đổi ở lần đăng nhập đầu:

| Tài khoản | Vai trò | Dùng để |
|---|---|---|
| `admin` | `SYS_ADMIN`, `AUDITOR` | Danh mục, tài khoản, cấu hình AI, nhật ký kiểm toán |
| `curator` | `CURATOR` | Nạp PDF, tạo và gửi bản nháp |
| `reviewer` | `REVIEWER` | Thẩm định, phê duyệt/từ chối bản nháp |
| `chuyenvien` | `USER` | Hỏi đáp và tìm kiếm văn bản |

### Gói chạy sẵn để chép sang máy khác (không cần cài đặt)

Máy phát triển tạo một gói sạch, chạy được trên bất kỳ Windows 64-bit nào (kể cả máy chưa
cài Python, PostgreSQL, Node):

```powershell
.\scripts\package-portable.ps1 -ProgramsRoot E:\Programs -PackageDirectory <thư mục đích> -Zip
```

Chép thư mục (hoặc tệp zip) sang máy đích rồi bấm `start.cmd`. Lần đầu gói tự tạo cơ sở dữ
liệu trống, mật khẩu cơ sở dữ liệu ngẫu nhiên và mật khẩu ban đầu ngẫu nhiên cho bốn tài
khoản (in ra màn hình, lưu ở `secrets\first-login.txt`, buộc đổi ở lần đăng nhập đầu).
Địa chỉ truy cập (IP, tên máy) được dò lúc chạy; cổng, địa chỉ nghe, chế độ AI nằm ở
`config\evidence.env`. Hướng dẫn cho người vận hành: `README.txt` trong gói
(nguồn: `deploy/portable/`). Gói không chứa dữ liệu hay mật khẩu của máy phát triển.

### Chạy cho người khác test qua mạng LAN từ máy phát triển (web)

Cách đơn giản nhất cho giai đoạn test là để người dùng mở **trình duyệt**: không phải cài
gì trên máy họ. Ứng dụng desktop chỉ kết nối `127.0.0.1` nên không dùng cho trường hợp này.

```powershell
# Lần đầu, mở PowerShell "Run as administrator" để mở cổng tường lửa (chỉ mạng nội bộ):
.\scripts\start-local-stack.ps1 -ProgramsRoot E:\Programs -Lan -OpenFirewall
# Các lần sau, shell thường:
.\scripts\start-local-stack.ps1 -ProgramsRoot E:\Programs -Lan
```

Script in các địa chỉ dạng `http://<IP máy chủ>:8000/` để gửi cho người test. Backend phục
vụ luôn bản web đã build (`frontend/dist`) trên cùng cổng nên không cần cấu hình CORS hay
địa chỉ API; PostgreSQL vẫn chỉ nghe `127.0.0.1`. Cần build web trước nếu `frontend/dist`
chưa có. Đường dẫn lấy từ vị trí script và `-ProgramsRoot`/`EVIDENCE_PROGRAMS_ROOT`; không
đặt cứng trong mã. Dùng HTTP không mã hóa: chỉ dành cho mạng tin cậy.

Seed không tự duyệt văn bản và không tạo hồ sơ model. Chạy lại không đặt lại mật khẩu,
quyền hay trạng thái duyệt.

## Chức năng

- **Hỏi đáp có căn cứ**: giao diện hai khung; khung trái lưu lịch sử câu hỏi/trả lời trong phiên
  (RAM), khung phải hiển thị câu trả lời và căn cứ. Căn cứ tự phân trang theo chiều cao khung
  và tính lại khi khung đổi kích thước; bấm `[n]` trong câu trả lời để cuộn tới căn cứ tương ứng.
  Câu trả lời ngắn có cấu trúc, mỗi văn bản một thẻ (loại, số hiệu,
  ngày, cơ quan, trích yếu, Điều/Khoản, trích dẫn nguyên văn ngắn, hiệu lực) và nút “Mở văn
  bản gốc” (PDF mở tab riêng đúng trang, Word/TXT tải đúng tệp đã nạp); khớp theo cụm từ,
  danh mục liệt kê văn bản tách riêng; SSE có dừng/thử lại; bộ nhớ phiên chỉ trong RAM.
- **Tìm kiếm văn bản** (một trang, trên tìm toàn diện G2): theo nghĩa, đủ các từ, chính xác
  cụm từ; lọc danh mục, loại văn bản, hiệu lực, thời gian; gộp theo văn bản, phân trang; kết
  quả chỉ khớp một phần ở nhóm riêng.
- **Admin Portal**: [Quản lý văn bản](docs/HUONG_DAN_SU_DUNG_VA_CAU_HINH_AI.md#quản-lý-văn-bản)
  hỗ trợ tìm/lọc, chi tiết, lịch sử phiên bản, sửa OCR, tạm ngừng và xóa mềm theo quyền.
  Cổng quản trị còn có tài liệu & duyệt nguồn, danh mục,
  tài khoản RBAC/ABAC, mô hình AI (hồ sơ, định tuyến giai đoạn chọn căn cứ, kiểm tra kết
  nối), nhật ký kiểm toán chuỗi băm.
- **Nạp tài liệu**: PDF, Word (`.docx`, `.doc`) và TXT. Word/TXT được vẽ thành một PDF có
  lớp chữ (cùng nội dung, cùng kết quả mỗi lần) để dùng chung một đường trích dẫn; tệp gốc
  được lưu cùng mã băm riêng (`document_versions.source_format`, `source_file_sha256`). PDF
  scan cần OCR (Tesseract). Nạp hàng loạt theo cây thư mục: `scripts/import_official_corpus.py`
  (xem [`test-data/README.md`](test-data/README.md)).
- **AI**: chế độ `API` hoặc `LOCAL` (Ollama/vLLM/llama.cpp hoặc dịch vụ tương thích
  OpenAI: `/v1`, Google Gemini `/v1beta/openai`, `/openai/v1`, `/api/v1`) định tuyến theo giai
  đoạn (`answer`, `summarize`, `expand`, `relation`, `label`, `embedding`, `rerank`). Trong hỏi
  đáp, model chỉ chọn tối đa 3 căn cứ trong số căn cứ đã kiểm nguồn; ở "Diễn giải AI" (`summarize`),
  mỗi ý được kiểm bằng mã trên căn cứ đính kèm; model không bao giờ sinh trích dẫn nguyên văn.
  Model lỗi/chậm thì hệ thống vẫn trả căn cứ gốc. Mô hình đề xuất và cấu hình máy:
  [`docs/ai-model-recommendations.md`](docs/ai-model-recommendations.md).
- **Quan hệ hiệu lực cấp Điều/Khoản/Điểm**: hỗ trợ đề xuất thay thế, sửa đổi, bổ sung và bãi bỏ;
  người có quyền duyệt xác nhận quan hệ và ngày áp dụng riêng của từng mục. Quan hệ thay thế có
  thể mang ngày hiệu lực lùi về trước; tra cứu theo thời điểm dùng ngày áp dụng đó. Ghi chú cảnh
  báo màu vàng xuất hiện khi hiệu lực cấp nút chưa được xác minh hoặc ngày tra cứu vượt ngày dữ
  liệu của kho.
- **Desktop Windows**: Orb nổi, kéo thả theo vùng làm việc đa màn hình/DPI, khay hệ thống.

## Kiểm thử

```powershell
$pw = (Get-Content 'E:\Programs\EvidenceRAG\secrets\postgres-dev.password' -Raw).Trim()
$env:EVIDENCE_TEST_DATABASE_URL = "postgresql://evidence_dev_admin:$pw@127.0.0.1:55432/postgres"
.\scripts\verify.ps1 -ProgramsRoot E:\Programs
```

`verify.ps1` chạy 12 bước: kiểm phụ thuộc, lint/typing/test backend, chính sách mã nguồn
(không đường dẫn cứng), cặp migration, OpenAPI, fixture phân cực và thời điểm, lint/test/
build frontend. Test PostgreSQL dùng schema tạm và xóa sau khi chạy; CI không được
skip chúng. Đo hiệu năng: `scripts/benchmark_search.py`; smoke HTTP:
`scripts/smoke_app_runtime.py`.

## Tài liệu

| Tài liệu | Nội dung |
|---|---|
| `00_README.md` | Chỉ mục hồ sơ bàn giao và thứ tự ưu tiên đặc tả |
| `docs/HOSO_BAN_GIAO.md`, `docs/SRS_v1.3.md` | Hồ sơ chính và đặc tả kỹ thuật hiện hành |
| `docs/architecture-decisions/ADR-000…010` | Quyết định kiến trúc |
| `docs/TAI_LIEU_MO_TA_HE_THONG.md` | Mô tả hệ thống và vòng đời văn bản (bản tiếng Anh: `docs/en/SYSTEM_DESCRIPTION.md`) |
| `docs/HUONG_DAN_SU_DUNG_VA_CAU_HINH_AI.md` | Hướng dẫn sử dụng và quản trị, gồm Quản lý văn bản (bản tiếng Anh: `docs/en/USER_ADMIN_AND_AI_GUIDE.md`) |
| `docs/vi/ARCHITECTURE_OVERVIEW.md` | Tổng quan kiến trúc (bản tiếng Anh: `docs/en/ARCHITECTURE_OVERVIEW.md`) |
| `deploy/lan-portable/README.txt`, `deploy/windows/README.md` | Triển khai Windows LAN Portable và ghi chú Windows (bản tiếng Anh: `README.en.txt`, `README.en.md` cùng thư mục) |
| `KIRO_WORK_SUMMARY.vi.md`, `PROJECT_TIMELINE.vi.md` | Hồ sơ công việc Kiro và dòng thời gian (bản tiếng Anh: `KIRO_WORK_SUMMARY.en.md`, `PROJECT_TIMELINE.md`) |
| `docs/implementation-status.md` | Trạng thái, kiểm chứng, giới hạn còn lại |
| `docs/search-v1-runbook.md` | Vận hành tìm kiếm và truy xuất chat |
| `docs/threat-model.md` | Mô hình đe dọa |
| `docs/evidence/` | Báo cáo và bằng chứng từng đợt |
| `configs/` | Mẫu cấu hình AI, triển khai, policy |

## Cấu trúc thư mục

```text
backend/          FastAPI: xác thực, RBAC/ABAC, duyệt nguồn, tìm kiếm, pipeline, migrations
frontend/         React + TypeScript: User Portal, Admin Portal, giao diện Orb (#/orb)
src-tauri/        Tauri 2 shell cho Windows USER
evaluation/       Corpus công khai, harness đánh giá tìm kiếm (case HƯ CẤU)
configs/          Mẫu cấu hình
deploy/           Hướng dẫn Windows, nguồn gói portable và LAN portable
tools/            Kiểm egress, hash, footprint
scripts/          verify, seed, khởi động stack, benchmark, smoke
docs/             Đặc tả, ADR, OpenAPI, runbook, bằng chứng; docs/en và docs/vi chứa bản dịch
parts/            Bản trích hồ sơ chính (sinh lại từ docs/HOSO_BAN_GIAO.md)
.kiro/            Quyền, specs, steering, hooks của Kiro
```

## Nguyên tắc an toàn

1. Agent chỉ tham mưu, read-only; không có tool ghi hoặc phê duyệt nghiệp vụ.
2. ACL lọc trong SQL theo người dùng trước khi lấy ứng viên; trích dẫn và PDF được kiểm
   lại quyền và mã băm khi mở.
3. Trích dẫn lấy từ `text_original` đã duyệt; LLM không viết trích dẫn hay ID điều khoản.
4. `API` và `LOCAL` qua Registry/Router; gửi dữ liệu ra ngoài mặc định bị chặn; `LOCAL`
   từ chối mọi hồ sơ `public` (`REMOTE_AI_DENIED`).
5. Tách biệt nhiệm vụ: `CURATOR` lập/gửi nháp; `REVIEWER` khác người mới được duyệt
   (`SELF_APPROVAL_DENIED`).
6. Bộ nhớ phiên không bao giờ là căn cứ; mặc định chỉ trong RAM.
7. Không dùng bộ câu hỏi Gold để chấm AI (ADR-010): AI chỉ hỗ trợ, cán bộ chuyên môn quyết định.

## License
Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE. Project history is described in PROJECT_TIMELINE.md ([Tiếng Việt](PROJECT_TIMELINE.vi.md)).
