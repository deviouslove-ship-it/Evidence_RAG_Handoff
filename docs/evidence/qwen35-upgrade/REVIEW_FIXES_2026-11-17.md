# Rà soát và sửa lỗi nâng cấp Qwen3.5 / OCR AI — 17/11/2026

## Phạm vi và cách kiểm chứng

Rà soát đợt nâng cấp đang sửa trong checkout `Evidence_RAG_Handoff`, trên nền commit `e985408fcfb0d425bd219e6539a6b868905a0014`. Các thay đổi của AI trước được giữ lại; đây là phần sửa lỗi bổ sung, chưa commit/push. Công việc bắt đầu ngày 16/11 và hoàn tất kiểm chứng ngày 17/11/2026.

- Đã lưu bản sao các file thay đổi trước rà soát tại `<TEMP>/evidence-qwen35-before-review-20261116-194748`.
- PostgreSQL thử nghiệm dùng cluster riêng trong `<TEMP>/evidence-qwen35-review-pg-20261116-194838`; các test tạo/xóa schema ở database tạm. Luồng model thật dùng database tạm khác để không tranh khóa với bộ test.
- Ollama thử nghiệm dùng executable được cấu hình trong `EVIDENCE_PROGRAMS_ROOT`, cổng loopback riêng, `OLLAMA_NO_CLOUD=true`, kho model đã có. Không tải hoặc sửa weights/model manifest.
- Không kết nối để sửa database vận hành; không nhập lại tài liệu, không tạo lại vector/index của kho cũ. Không sửa/thay ZIP hoặc thư mục Portable r4.

## Các lỗi đã sửa

| Vấn đề trước rà soát | Kết quả sau sửa | Nơi xử lý chính |
|---|---|---|
| Câu “text trang 17 của văn bản này” bị coi phần “văn bản này” là tên tài liệu; yêu cầu đọc lại ảnh chưa ép dùng vision | Nhận diện ngữ cảnh của lượt đang chọn; giữ tên/số hiệu rõ ràng; chuyển đúng `prefer_ai` qua bước chọn tài liệu và xác nhận trang in | `frontend/src/components/pageTextIntent.ts`, `frontend/src/pages/EvidenceChat.tsx` |
| UUID dự phòng sai định dạng khi HTTP LAN không có `crypto.randomUUID`, API trả 422 | Helper UUID v4 dùng chung, ưu tiên `getRandomValues` | `frontend/src/requestId.ts`, `OcrAiPanel.tsx`, `EvidenceChat.tsx` |
| Nút sao chép không làm việc khi thiếu Clipboard API và không báo thất bại | Có fallback đồng bộ cho HTTP LAN và thông báo trạng thái nhìn thấy/đọc được bằng trình đọc màn hình | `PageTextPanel.tsx` |
| PDF tải xong sau logout/đổi trang vẫn có thể được gắn vào iframe | Abort và kiểm tra đúng request/ngữ cảnh trước khi tạo blob URL; thu hồi URL cũ | `PageTextPanel.tsx` |
| Phản hồi áp dụng/bỏ qua/hủy OCR của tài liệu cũ có thể ghi vào panel tài liệu mới | Chặn phản hồi đến muộn theo token, document, version, page và revision | `OcrAiPanel.tsx` |
| Xóa dữ liệu tạm chỉ dừng polling; một số thao tác đổi lượt để lại tác vụ và trạng thái đang đọc cũ | Hủy tác vụ đã nhận ID, kết thúc trạng thái chờ, bỏ phản hồi của controller cũ khi dừng/đổi yêu cầu/xóa phiên | `EvidenceChat.tsx` |
| GET vẫn trả chữ AI của task hết TTL; cleanup bị rollback khi trả lỗi | Cleanup commit riêng, xóa candidate JSON/text, trả 410; worker cũng dọn task hết hạn khi polling hàng đợi | `backend/app/documents/page_text.py`, `ocr_ai_store.py`, `ocr_ai_jobs.py` |
| USER có thể nhận kết quả theo revision/chữ trang cũ | So revision, SHA PDF và SHA chữ trang trước/trong/sau inference và khi trả task đã ready | `page_text.py`, `ocr_ai_jobs.py` |
| Worker thứ hai coi task đang được worker sống xử lý là task mồ côi; cleanup temp có thể đụng render khác | Khóa advisory theo session giữ trong toàn tác vụ; chỉ phục hồi/dọn orphan khi không có worker đang sở hữu khóa | `ocr_ai_jobs.py` |
| Hủy chỉ đổi trạng thái DB; HTTP inference vẫn chờ đến hết timeout | Kiểm tra task/ACL/nguồn trong lúc chờ và hủy coroutine HTTP; thêm ngân sách toàn tác vụ 360 giây, lease dài hơn ngân sách; không retry tự động | `ocr_ai_jobs.py` |
| Request mới vẫn vào queue khi worker tắt | Mặc định OCR AI tắt theo phương án; bật có chủ đích bằng `EVIDENCE_OCR_AI_ENABLED=true`. Khi tắt, API trả 503 cho đọc ảnh mới; chữ trang đã duyệt vẫn trả trực tiếp | `config.py`, hai router và hai service OCR/page-text |
| Digest lấy từ `/api/show` có thể rỗng trên Ollama thật | Lấy digest từ native `/api/tags` khi cần, chuẩn hóa `sha256:` | `model_registry/adapters/ollama_local.py` |
| Kết quả cũ vẫn có thể được giữ/áp dụng khi profile, weights hoặc prompt đã đổi | Lưu fingerprint profile + model + ảnh trước inference; so lại sau inference; kiểm tra route/digest trước apply và profile/prompt trong transaction | `model_registry/runtime.py`, `profiles.py`, `ocr_ai_jobs.py`, `ocr_ai_store.py`, router OCR |
| Probe chỉ nhận HTTP 200/chữ không rỗng hoặc ảnh 1 px | Kiểm tra chữ đã biết trên ảnh tổng hợp. Probe chỉ chấp nhận đúng chữ/số, cho phép khác dấu phân cách; không coi probe là điểm chất lượng OCR | `diagnostics.py`, `runtime.py`, `portable.ps1`, `config/ocr-probe.png` |
| Cảnh báo/tiêu đề bị cắt trên khung hẹp dù toàn trang không có thanh cuộn ngang | Cho header xuống dòng, status wrap, grid OCR co theo khung; không che lỗi bằng clipping | `frontend/src/styles.css` |
| Hợp đồng OpenAPI và hướng dẫn chưa theo luồng mới | Xuất lại OpenAPI; thêm hướng dẫn đọc một trang, bật OCR, TTL và giới hạn; sửa mô tả tài khoản và phân biệt template với gói đã kiểm chứng | `docs/openapi.json`, hai hướng dẫn repo và các hướng dẫn Portable |
| Script test dừng toàn bộ Ollama hoặc tiến trình bất kỳ chiếm cổng | Đổi sang hồ sơ sở hữu theo checkout/cổng, PID + executable + thời điểm tạo; PostgreSQL chỉ dừng nếu lần chạy đã ghi nhận sở hữu | `ung-dung-test.ps1` — mới kiểm chứng cú pháp, giới hạn kiểm tra động ở phần cuối |

## Kết quả kiểm tra

| Kiểm tra | Kết quả thực tế |
|---|---|
| Backend toàn bộ với PostgreSQL/pgvector tạm | **341 passed, 0 skipped**; 164,93 giây trong lượt có chạy đồng thời phép thử model thật |
| API OCR/page-text sau kiểm tra tương thích cờ tắt | **3 passed**, 9,03 giây; cluster thử nghiệm đã dừng lại |
| Frontend toàn bộ sau sửa luồng dừng/xóa phiên | **110 passed**, 22 file test |
| Backend Ruff | Passed |
| Backend mypy strict | Passed, 103 source files |
| Frontend ESLint, TypeScript và Vite production build | Passed |
| Dependencies | `uv pip check`: 41 packages compatible |
| Migration pairs | 17 cặp hợp lệ; chỉ áp dụng trên DB thử nghiệm |
| OpenAPI | Export và `--check` passed |
| Kiểm tra literal secret/path trong source | Passed; không nới quy tắc kiểm tra |
| Polarity/temporal fixtures | 4 polarity cases không lỗi; temporal chain A → B → C → D resolved |
| PowerShell parser | `portable.ps1`, `build-lan-portable.ps1`, `ung-dung-test.ps1` passed |
| Chrome qua Playwright | Đăng nhập, yêu cầu trang 17, kết quả/cảnh báo, sao chép, mở PDF gốc; kiểm tra viewport 390×844, 768×900, 1280×800 |
| Responsive sau sửa | `documentWidth == viewport`, không status nào bị cắt tại cả ba kích thước; focus bàn phím có outline |

Các regression mới đã được chạy khi còn lỗi rồi chạy lại sau sửa. Backend còn một cảnh báo deprecation từ Starlette/AnyIO; không có test thất bại. Trình duyệt dùng API fixture **HƯ CẤU**, không đại diện cho kiểm thử toàn hệ thống trên máy trạm LAN; lỗi favicon 404 thuộc fixture, không phải lỗi JavaScript ứng dụng.

## Kiểm tra với model thật

Môi trường: Ollama **0.40.15**, `qwen3.5:4b`, local-only. Tạo PDF **20 trang dạng ảnh** chứa báo cáo hành chính HƯ CẤU; trang 17 có tổng số hồ sơ `1729` và ngày `16/11/2026`.

1. Yêu cầu thường trả đúng chữ trang đã duyệt, không gọi AI.
2. Yêu cầu đọc lại ảnh chỉ render/gửi trang 17. Qwen trả đúng nội dung mẫu, số `1729`, ngày và số trang; response ghi `ocr_ai_unverified`, `verified=false`.
3. Hai lượt đo cho phần đọc trang USER mất khoảng **77,7 và 94,1 giây**. Đây là thời gian trên máy/tải thử nghiệm này, không phải benchmark chuẩn hoặc cam kết tốc độ; lượt sau chạy cùng bộ regression.
4. USER ngoài phạm vi bị từ chối xem task/PDF. USER task không áp dụng được vào kho dù gọi từ tài khoản có quyền curator.
5. Hash PDF và toàn bộ chữ trang của bản nguồn giữ nguyên sau đọc. Chạy riêng luồng ADMIN với model thật tạo đề xuất, áp dụng thành **bản nháp mới**; bản cũ vẫn `approved`; không phát sinh embedding.
6. Fingerprint lưu và kiểm được; đổi revision profile trong DB tạm khiến snapshot cũ bị từ chối.
7. Adapter sinh văn bản native, `think=false`, JSON mode trả đúng `{"tong":1729}` từ báo cáo mẫu.

| Định danh model đã kiểm | Giá trị |
|---|---|
| SHA-256 file manifest trong model store | `e0b8c85c75aad2573ff49bec177ebb1013772fba665a53d64c04266439a2222d` |
| Digest native `/api/tags` mà runtime ghi nhận | `sha256:d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04` |
| SHA-256 ảnh trang 17 đã render | `79974ca0615cc208ace92ac06136d6294a1352651cf7940bb671b103ea3645c1` |

Hai digest manifest trên là hai định danh khác nhau: file manifest có các layer manifest lồng nhau, bao gồm layer `d8b0…` mà Ollama công bố; không kết luận weights bị đổi chỉ từ việc hai digest khác nhau. Không sửa các số đo lịch sử ngày 16/11 trong báo cáo trước.

## Giới hạn và điều kiện trước phát hành

- **Chưa build/giải nén/di chuyển/chạy một ZIP Portable mới**. Rà script, parser và asset chỉ là kiểm chứng source. R4 đang bàn giao giữ nguyên `qwen3:1.7b`; không gán các tính năng source mới cho ZIP r4.
- Kế hoạch cần giữ model cũ để quay lui. Hiện `models/ollama` của repo và kho dưới `EVIDENCE_PROGRAMS_ROOT` chỉ liệt kê `qwen3.5` và `qwen3-embedding`; model `qwen3` vẫn có trong r4. Cần chuẩn bị đủ manifest/blob cho các profile/fallback cần đóng gói, xác nhận các route/index trên **DB bản sao**, rồi mới build gói mới. Đợt rà soát này không tự copy/đổi model store hoặc Registry vận hành.
- OCR AI mặc định tắt. Người vận hành cần kiểm tra model, phân công `ocr`, bật cờ và restart bản triển khai được chọn. Không tự bật cờ trên hệ thống đang vận hành.
- Chưa kiểm thử thêm máy Windows/GPU/RAM khác, máy trạm LAN, ZIP offline cô lập, mất điện, OOM/soak hoặc khối lượng người dùng đồng thời. Kết quả tổng hợp không thay cho đối chiếu nghiệp vụ trên PDF scan thật, bảng khó, dấu/chữ ký hoặc chữ viết tay.
- Dấu phân cách trên ảnh probe từng bị model đọc nhầm `OCR-PROBE-17` thành `OCR:PROBE-17`. Probe xác nhận khả năng nhận ảnh/chữ, không bảo đảm độ chính xác của OCR; luôn giữ cảnh báo và quy trình reviewer.
- Bài kiểm tra động dừng tiến trình giả/giữ dịch vụ ngoài của `ung-dung-test.ps1` bị bộ duyệt tự động từ chối với thông báo **“blocked by policy”**, không kèm lý do chi tiết hơn. Bản sửa đã qua parser; chưa xác nhận động toàn bộ start/stop của launcher này. Không thực hiện lại bài kiểm tra bị chặn bằng cách khác và không yêu cầu cấp thêm quyền.
- Thử chạy trực tiếp `ung-dung-test.ps1 -Action status` cũng bị Windows từ chối vì tệp chưa ký trong ngữ cảnh `RemoteSigned`. Không đổi Execution Policy hoặc bỏ đánh dấu bảo mật của tệp; các BAT hiện có vốn gọi PowerShell với tham số riêng của launcher. Đây không phải xác nhận BAT/start/stop đã chạy qua.

Các dịch vụ thử nghiệm tạo trong đợt rà soát (PostgreSQL tạm, Ollama cổng riêng, server UI HƯ CẤU và browser Playwright) đã dừng. Giữ lại bản sao source trước rà soát và log/ảnh trong thư mục TEMP ở trên để đối chiếu. Không commit/push, không ghi lại lịch sử Git.
