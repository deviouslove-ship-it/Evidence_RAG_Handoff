# Vietnamese Evidence RAG Agent

Tra cứu pháp lý tiếng Việt có căn cứ nguồn. Một backend FastAPI, một PostgreSQL và một
kho PDF bất biến theo SHA-256 phục vụ **User Portal** (hỏi đáp, tìm kiếm văn bản),
**Admin Portal** và **ứng dụng Windows USER (Tauri 2)**. Trạng thái hiện hành:
[`docs/implementation-status.md`](docs/implementation-status.md).

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

- **Hỏi đáp có căn cứ**: câu trả lời ngắn có cấu trúc, mỗi văn bản một thẻ (loại, số hiệu,
  ngày, cơ quan, trích yếu, Điều/Khoản, trích dẫn nguyên văn ngắn, hiệu lực) và nút “Mở văn
  bản gốc” (PDF mở tab riêng đúng trang, Word/TXT tải đúng tệp đã nạp); khớp theo cụm từ,
  danh mục liệt kê văn bản tách riêng; SSE có dừng/thử lại; bộ nhớ phiên chỉ trong RAM.
- **Tìm kiếm văn bản** (một trang, trên tìm toàn diện G2): theo nghĩa, đủ các từ, chính xác
  cụm từ; lọc danh mục, loại văn bản, hiệu lực, thời gian; gộp theo văn bản, phân trang; kết
  quả chỉ khớp một phần ở nhóm riêng.
- **Admin Portal**: tài liệu & duyệt nguồn (tách biệt người tạo/người duyệt), danh mục,
  tài khoản RBAC/ABAC, mô hình AI (hồ sơ, định tuyến giai đoạn chọn căn cứ, kiểm tra kết
  nối), nhật ký kiểm toán chuỗi băm.
- **Nạp tài liệu**: PDF, Word (`.docx`, `.doc`) và TXT. Word/TXT được vẽ thành một PDF có
  lớp chữ (cùng nội dung, cùng kết quả mỗi lần) để dùng chung một đường trích dẫn; tệp gốc
  được lưu cùng mã băm riêng (`document_versions.source_format`, `source_file_sha256`). PDF
  scan cần OCR (Tesseract). Nạp hàng loạt theo cây thư mục: `scripts/import_official_corpus.py`
  (xem [`test-data/README.md`](test-data/README.md)).
- **AI**: chế độ `API` hoặc `LOCAL` (Ollama/vLLM/llama.cpp hoặc dịch vụ tương thích
  OpenAI: `/v1`, Google Gemini `/v1beta/openai`, `/openai/v1`, `/api/v1`). Model chỉ chọn tối
  đa 3 căn cứ trong số căn cứ đã kiểm nguồn; không sinh trích dẫn. Model lỗi/chậm thì lượt
  chat vẫn trả căn cứ gốc. Mô hình đề xuất và cấu hình máy:
  [`docs/ai-model-recommendations.md`](docs/ai-model-recommendations.md).
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
| `docs/architecture-decisions/ADR-000…006` | Quyết định kiến trúc |
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
deploy/windows/   Hướng dẫn triển khai Windows
tools/            Kiểm egress, hash, footprint
scripts/          verify, seed, khởi động stack, benchmark, smoke
docs/             Đặc tả, ADR, OpenAPI, runbook, bằng chứng
parts/            Bản trích hồ sơ chính (sinh lại từ docs/HOSO_BAN_GIAO.md)
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
7. Gold/trap chỉ được công nhận sau khi người nắm nghiệp vụ duyệt.
