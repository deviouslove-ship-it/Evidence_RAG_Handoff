# Evidence RAG - Windows Web LAN Portable: Hướng dẫn sử dụng đầy đủ

**Ngôn ngữ / Language:** Tiếng Việt · English: `USER_GUIDE.en.md` (cùng thư mục)

Tài liệu này đi kèm bản **Evidence RAG - Windows Web LAN Portable** và mô tả đúng bộ đóng gói này: khởi động, đăng nhập, sử dụng USER và ADMIN, quản lý tài liệu, OCR, cấu hình AI Local và AI API, sao lưu/phục hồi và xử lý lỗi. Tên nút theo giao diện tiếng Việt của bản đóng gói. Chỉ thực hiện thao tác quản trị, thay model, phục hồi hoặc đổi cấu hình khi có quyền và sau khi hiểu ảnh hưởng tới hệ thống. Hệ thống chỉ hỗ trợ tra cứu: kết quả AI luôn cần chuyên viên kiểm tra, không thay thế nguồn pháp lý chính thức.

## Mục lục

0. [Bản Portable này (đọc trước)](#0-bản-portable-này-đọc-trước)
1. [Đăng nhập và tra cứu](#1-đăng-nhập-và-tra-cứu)
2. [Nhập, OCR và duyệt nguồn](#2-nhập-ocr-và-duyệt-nguồn) · [Quản lý văn bản](#quản-lý-văn-bản)
3. [Danh mục, tài khoản và kiểm toán](#3-danh-mục-tài-khoản-và-kiểm-toán)
4. [Cấu hình AI Local](#4-cấu-hình-ai-local)
5. [Cấu hình AI API](#5-cấu-hình-ai-api)
6. [Phân công AI và embedding](#6-phân-công-ai-và-embedding)
7. [Model local cho Portable offline](#7-model-local-cho-portable-offline)
8. [Khởi động, dừng, sao lưu và phục hồi](#8-khởi-động-dừng-sao-lưu-và-phục-hồi)
9. [Xử lý lỗi](#9-xử-lý-lỗi)
## 0. Bản Portable này (đọc trước)

**Gói gồm gì.** Giao diện web, máy chủ FastAPI, PostgreSQL + pgvector (cơ sở dữ liệu, chỉ mục, vector), kho tài liệu gốc (tên tệp là SHA-256 của nội dung), Tesseract OCR (`vie`, `eng`, `osd`), Ollama và hai model AI cục bộ (`qwen3:1.7b` cho diễn giải/mở rộng/gán nhãn/quan hệ, `qwen3-embedding:0.6b` 1024 chiều cho tìm theo nghĩa). Chạy hoàn toàn offline; không cần cài Python, PostgreSQL, Ollama, Tesseract hay Node.js. Máy trạm chỉ cần trình duyệt.

**Yêu cầu máy chủ.** Windows 10 / Windows Server 2016 trở lên, x64, PowerShell 5.1 (có sẵn). Trống tối thiểu 6 GB cho gói đã giải nén và dữ liệu; RAM tối thiểu 8 GB (khuyến nghị, đã thử: Intel Core i3, DDR4 32 GB, SSD 512 GB) (model chạy bằng CPU, lần gọi đầu phải nạp model vào RAM). Không cần quyền Administrator để chạy.

**Khởi động nhanh.**
1. Giải nén TOÀN BỘ tệp nén (.rar, bằng WinRAR hoặc 7-Zip) vào một thư mục bất kỳ trên ổ bất kỳ (tên thư mục có dấu cách vẫn dùng được; không chạy trong tệp nén). Nên dùng đường dẫn ngắn.
2. Bấm đúp **Start-Server.bat**. Cửa sổ lần lượt kiểm tra thành phần, khởi động PostgreSQL, Ollama và máy chủ web, rồi in địa chỉ dạng `http://<IP LAN>:8800/`. Lần đầu mất thêm 1-3 phút để dựng cơ sở dữ liệu riêng từ bản dữ liệu gốc trong `seed\` và đối chiếu từng bảng; tài liệu, OCR, vector và chỉ mục giữ nguyên, không nạp lại.
3. Gửi địa chỉ đó cho người dùng trong LAN; họ mở bằng trình duyệt và đăng nhập. Nếu máy khác không vào được, xem mục 8.4 (tường lửa). Gói **không tự mở cổng tường lửa**.
4. Dừng bằng **Stop-Server.bat**; chỉ dừng các tiến trình chạy từ thư mục này, không ảnh hưởng PostgreSQL/Ollama/Python khác trên máy.

**Các thư mục.** `app\` (web và backend), `runtime\` (Python, PostgreSQL, Ollama, Tesseract), `models\ollama\` (model AI), `data\documents\` (tài liệu gốc), `data\postgres\` (cơ sở dữ liệu, tạo ở lần chạy đầu), `seed\` (bản dữ liệu gốc để dựng lần đầu), `config\evidence.env` (cấu hình, mục 8.6), `secrets\` (mật khẩu DB sinh ngẫu nhiên và khóa API mã hóa DPAPI; không chia sẻ), `logs\`, `backups\`, `tools\`.

**Tài khoản trong gói và quyền theo danh mục (ABAC).** Gói có 5 tài khoản. Mỗi tài khoản có một **mật khẩu demo riêng**, dùng được ngay sau khi giải nén (không buộc đổi ở lần đăng nhập đầu). Mật khẩu **không** nằm trong gói, README, nhật ký hay mã nguồn (gói chỉ lưu dạng băm scrypt); chúng được bàn giao riêng trong tệp `Acount_Demo.md` đặt cạnh tệp ZIP (không nằm trong ZIP). Đây là mật khẩu demo, không phải mật khẩu vận hành: hãy **đổi ngay sau khi nhận** (Đổi mật khẩu) hoặc đặt lại trong Admin Portal → Tài khoản & Phân quyền trước khi đưa vào sử dụng thật.

| Tài khoản | Vai trò | Quyền trên danh mục |
|---|---|---|
| `chuyenvien` | USER (hỏi đáp, tìm kiếm) | Tra cứu cả 9 danh mục |
| `curator` | CURATOR + USER (nạp, sửa bản nháp, OCR, gửi duyệt; Hỏi đáp, Tìm kiếm) | Tra cứu cả 9 danh mục |
| `reviewer` | REVIEWER + USER (duyệt, xác nhận hiệu lực; Hỏi đáp, Tìm kiếm) | Tra cứu cả 9 danh mục và quyền xác nhận hiệu lực (`can_review`) trên cả 9 danh mục |
| `admin` | SYS_ADMIN + AUDITOR | Quản trị hệ thống và kiểm toán; không có vai trò USER và không được cấp danh mục nên không tự có quyền đọc nội dung văn bản |
| `ocr_tester` | USER (tài khoản thử OCR) | Tra cứu cả 9 danh mục |

Chín danh mục: Luật, Nghị định, Thông tư, Thông tư liên tịch, Quyết định, Chỉ thị, Các loại văn bản khác, Tài liệu thử chưa duyệt (PUBLIC_PDF_TEST), Thử nghiệm OCR (THU_NGHIEM_OCR). Hai danh mục cuối là dữ liệu thử, chưa xác minh nghiệp vụ. Người duyệt không được duyệt bản nháp do chính mình chuẩn bị. Tài khoản có hai vai trò (`curator`, `reviewer`) mở được cả trang người dùng (Hỏi đáp, Tìm kiếm, mở tài liệu gốc) và Admin Portal; quyền nhìn thấy tài liệu luôn do danh mục được cấp (ABAC) quyết định, vai trò quản trị không tự cấp quyền đọc. Quyền có thể sửa trong Admin Portal → Tài khoản & Phân quyền. Phiên đăng nhập cũ không được mang theo trong gói.

**Dữ liệu trong gói.** 105 văn bản, 7.447 đoạn có vector (qwen3-embedding:0.6b, 1024 chiều), 1.566 trang nguồn, 191 tệp tài liệu gốc. Không dùng bộ câu hỏi Gold để chấm điểm AI (ADR-010); AI chỉ hỗ trợ và cán bộ chuyên môn quyết định. Không dùng gói này làm căn cứ khẳng định độ chính xác hay mức sẵn sàng triển khai.

**OCR trong gói.** Tesseract đi kèm trong `runtime\tesseract` được backend dùng tự động (ngôn ngữ `vie+eng`); không cần cài hay cấu hình đường dẫn. Thời gian chờ mỗi trang và mỗi PDF chỉnh bằng `EVIDENCE_OCR_PAGE_TIMEOUT_SECONDS`, `EVIDENCE_PDF_TIMEOUT_SECONDS` trong `config\evidence.env`. Quy trình duyệt trang OCR ở mục 2.

**Chế độ AI.** Mặc định `LOCAL`: mọi xử lý AI chạy trên máy chủ bằng Ollama đi kèm, không gửi dữ liệu ra ngoài. Chế độ API chỉ dùng khi quản trị viên cấu hình và chính sách cho phép (mục 5).
## 1. Đăng nhập và tra cứu

1. Mở địa chỉ do người vận hành cung cấp trên trình duyệt, chọn **Đăng nhập**, nhập tài khoản và mật khẩu được cấp. Nếu được yêu cầu, dùng **Đổi mật khẩu** trước khi tiếp tục. Không dùng chung tài khoản.
2. Tại **Hỏi đáp có căn cứ**, nhập câu hỏi rõ nội dung, số hiệu và Điều nếu biết; gửi câu hỏi. Có thể dừng hoặc thử lại lượt đang xử lý. Đọc câu trả lời và từng thẻ văn bản, nhãn Điều/Khoản, trích đoạn và hiệu lực. “Chưa tìm thấy” nghĩa là không tìm thấy căn cứ phù hợp trong phạm vi và kho hiện tại, không chứng minh quy định không tồn tại.
3. Chọn **Xem tất cả kết quả** khi muốn chuyển câu hỏi sang trang tìm kiếm. Ở **Tìm kiếm văn bản**, nhập nội dung, chọn **Tìm theo nghĩa (toàn diện)**, **Tìm đủ các từ** hoặc **Tìm chính xác cụm từ**, rồi bấm **Tìm kiếm**. Mở **Bộ lọc** để chọn danh mục, loại văn bản, ngày hiệu lực và phạm vi thời gian; có thể lọc thêm trạng thái sau khi có kết quả. Xem từng nhóm và trang kết quả.
4. Trong Hỏi đáp hoặc kết quả tìm kiếm, chọn **Diễn giải AI** nếu cần một bản diễn giải từ những căn cứ phù hợp. Đọc phần thiếu căn cứ, cảnh báo và **Căn cứ hỗ trợ**; dùng **Diễn giải tiếp** nếu có. Các ý được kiểm tự động vẫn cần đối chiếu trước khi sử dụng.
5. Chọn **Mở văn bản gốc** trên thẻ căn cứ. PDF mở riêng tại trang nguồn; Word/TXT tải đúng tệp gốc. Nếu bị từ chối, không có nghĩa tệp bị xóa: phiên, quyền, trạng thái nguồn hoặc kiểm tra toàn vẹn có thể không đạt.

## 2. Nhập, OCR và duyệt nguồn

Các mục hiện theo quyền CURATOR/REVIEWER được cấp.

1. Vào Admin Portal → **Tài liệu & Duyệt nguồn**. Trong **Nhập PDF nguồn (Biên tập viên)** chọn tệp PDF, DOC, DOCX hoặc TXT; nhập tiêu đề, loại văn bản, số hiệu và đường dẫn chính thức HTTPS nếu có. Với nhiều tệp, kiểm từng thông tin trước khi tạo các nháp; hệ thống xử lý lần lượt, cho phép dừng và thử lại các tệp chưa thành công. Nếu kết quả không rõ sau mất kết nối, kiểm hàng đợi trước khi gửi lại.
2. Chọn **Tạo bản nháp**, rồi **Mở PDF & rà soát** để xem nội dung và tác vụ. Sửa/kiểm metadata, bản gốc, trang và cảnh báo. Nếu cần, bấm **Trích xuất lại PDF gốc** khi có quyền và OCR đã được cấu hình; không tự coi chữ OCR là đúng.
3. Với PDF scan, reviewer mở từng trang trong màn hình rà soát, so chữ OCR và các cảnh báo với ảnh trang rồi xác nhận. Không xác nhận trang không đọc được hoặc sai; cấu hình OCR và trích xuất lại, hoặc từ chối nháp theo tình huống. Chữ OCR đã duyệt vẫn cần đối chiếu ảnh khi dùng.
4. Biên tập viên chọn **Gửi duyệt**. Reviewer khác mở nháp đang chờ, xử lý tác vụ còn mở, chọn danh mục áp dụng và nhập ghi chú thẩm định. Bấm **Phê duyệt & Phát hành** khi đủ điều kiện, hoặc **Từ chối**. Trùng byte bị chặn; cảnh báo nội dung trùng cần được xem xét.
5. Vào **Hiệu lực** để rà soát đề xuất hiệu lực, quan hệ và nhãn khi có quyền. Một đề xuất chưa được xác minh không phải kết luận về hiệu lực pháp lý.

### Quản lý văn bản

1. Mở **Admin Portal → Quản lý văn bản**. Tìm theo số hiệu hoặc trích yếu, hoặc lọc theo loại,
   cơ quan ban hành, ngày, trạng thái xử lý, hiệu lực và trạng thái tra cứu. Bấm **Áp dụng bộ lọc**.
2. Chọn **Chi tiết** để xem metadata, danh mục và các phiên bản. Nếu có quyền đọc, mở tệp
   gốc, chuyển trang OCR, xem Điều/Khoản/Điểm và số mục đã có embedding trong chỉ mục
   đang dùng. Mở **Lịch sử xử lý** để xem thao tác gần đây.
3. CURATOR có quyền dùng **Sửa thông tin** (rồi **Lưu thông tin**), **Sửa chữ OCR** của trang scan (rồi **Lưu sửa OCR**) hoặc **Xử lý lại từ tệp gốc** (rồi **Xác nhận xử lý lại**). Xử lý lại chạy bộ trích xuất/OCR đã cấu hình và đưa kết quả về nháp. Khi đã duyệt
   hoặc từ chối, thao tác tạo phiên bản nháp mới. Có thể **Thêm phiên bản từ tệp mới** để đính một PDF, Word hoặc TXT mới vào cùng văn bản, rồi chọn **Tạo phiên bản nháp**. Xác minh thông tin của tệp trước khi
   gửi duyệt.
4. Trong hồ sơ văn bản chọn **Gửi duyệt**, hoặc chọn nhiều bản nháp trong danh sách rồi **Gửi duyệt các bản đã chọn** (xác nhận bằng **Xác nhận gửi duyệt**). Kiểm tra kết quả từng bản. REVIEWER khác mở phiên bản đang chờ, chọn **Mở PDF và thẩm định**, xem tệp nguồn, xử lý tác vụ và xác nhận lại từng
   trang OCR có chỉnh sửa. Ghi lý do rồi chọn **Phê duyệt phiên bản** hoặc **Từ chối phiên bản**. Các danh mục đã gán được
   giữ lại. Reviewer cần quyền duyệt trên tất cả danh mục đã gán. Nếu có thông báo phiên
   bản thay đổi, tải lại chi tiết rồi tiếp tục. Bản đã duyệt trước đó tiếp tục được tra cứu
   trong khi bản sửa chờ duyệt, nếu văn bản đang hoạt động và người dùng có quyền.
5. SYS_ADMIN chọn một hoặc nhiều văn bản để **Tạm ngừng**, **Mở lại tra cứu**,
   **Xóa mềm** hoặc **Khôi phục văn bản**. Kiểm danh sách đã chọn, nhập lý do và xác
   nhận. Dùng bộ lọc **Đã xóa** để khôi phục văn bản xóa mềm. Văn bản từng bị tạm ngừng
   cần **Mở lại tra cứu** riêng. Bản đang chờ duyệt vẫn phải qua thẩm định trước khi phát hành.

Nếu bản sửa làm thay đổi căn cứ của quan hệ cấp Điều/Khoản/Điểm, rà soát lại ở mục
**Hiệu lực**. Khi hệ thống chưa ghép được đích theo đường dẫn pháp lý, quan hệ cần được
xác định đúng nút đích qua API rà soát trước khi phê duyệt. Giao diện hiện chưa có bộ chọn
nút đích. Quyền xem nội dung được cấp riêng cho từng phạm vi, kể cả với tài khoản quản trị.

**Đề xuất hiệu lực cấp Điều/Khoản (bản này).** Hệ thống chỉ *đề xuất*; người có quyền xác nhận hiệu lực quyết định.
- Mục có ghi "kể từ ngày D" riêng (ví dụ "Thay thế khoản 2 Điều 4 … kể từ ngày 01/01/2027") dùng đúng ngày D đó; không có thì mới dùng ngày hiệu lực của cả văn bản. Mục ghi nhiều ngày khác nhau để trống ngày, người duyệt phải nhập.
- "Điều 5 và Điều 6 thay thế Điều 3 và Điều 4" được tách thành một đề xuất cho mỗi Điều đích (nguồn giữ nguyên là nhóm "Điều 5 và Điều 6").
- "Thay thế một phần / một số điều của văn bản X" mà không nêu Điều cụ thể tạo đề xuất *thay thế* có đích để trống: không thể duyệt cho đến khi chọn nút đích (hệ thống trả lỗi `RELATION_TARGET_REQUIRED`).
- "Sửa đổi khoản 2 Điều 4 của văn bản X" hoặc "Bãi bỏ Điều 3 của văn bản X" được gắn đúng nút đích. Sau khi duyệt, Điều bị bãi bỏ hiện **đã hết hiệu lực** nên không xuất hiện trong kết quả tìm kiếm mặc định; khoản được sửa hiện **đã sửa đổi**.

## 3. Danh mục, tài khoản và kiểm toán

- **Danh mục**: SYS_ADMIN tạo/sửa danh mục, mã, tên và tùy chọn cho phép xử lý từ xa. Đánh dấu cho phép không tự vượt qua chính sách egress hay quyền tài khoản. Xóa mềm danh mục ảnh hưởng quyền truy cập tương ứng.
- **Tài khoản & Phân quyền**: tạo hoặc sửa tài khoản, vai trò, trạng thái và danh mục được phép (xem mục "Quyền theo danh mục" ngay dưới); kiểm tra nhu cầu thực trước khi cấp. Vai trò quản trị không tự cấp quyền đọc mọi tài liệu. Tài khoản mới/đặt lại có thể phải đổi mật khẩu.
- **Quyền theo danh mục**: admin cấp quyền cho từng tài khoản trong **Tài khoản & Phân quyền**, ở hai ô **Danh mục được phép tra cứu (ABAC)** (danh mục tài khoản được tra cứu và mở tài liệu) và **Danh mục được xác nhận hiệu lực (người duyệt)** (ô này chỉ hiện khi tài khoản có vai trò REVIEWER), rồi bấm **Lưu tài khoản**. Tài khoản chưa được cấp danh mục nào thì không thấy văn bản nào. Khi khởi tạo, `chuyenvien` đã được sẵn quyền tra cứu các danh mục thử; `curator` và `reviewer` thấy danh sách trống cho đến khi admin cấp. Vai trò (RBAC) quyết định được làm gì, danh mục (ABAC) quyết định thấy văn bản nào; người dùng không thể tự duyệt bản do chính mình gửi duyệt. Riêng gói Portable này đã cấp sẵn cả 9 danh mục cho `chuyenvien`, `curator` và `reviewer` (và `reviewer` có thêm quyền xác nhận hiệu lực), xem mục 0.
- **Mô hình AI & Kiểm toán** → **3. Nhật ký Kiểm toán**: người có quyền xem hoạt động quản trị và kiểm tra chuỗi audit. Không đưa mật khẩu hay khóa API vào ghi chú hoặc trao đổi thông thường.

## 4. Cấu hình AI Local

Điều kiện: dịch vụ model đã chạy và model có sẵn; backend phải truy cập được địa chỉ đó. Với máy chủ LAN, endpoint cần nằm trong danh sách được phép của cấu hình vận hành. Endpoint `localhost`/`127.0.0.1` được hiểu từ **máy chủ backend**, không phải máy trạm.

1. Đăng nhập SYS_ADMIN, mở **Mô hình AI & Kiểm toán** → **1. Mô hình AI** → **Thêm AI Local**.
2. Nhập **Tên hồ sơ**; chọn **Runtime** Ollama, vLLM hoặc llama.cpp; nhập **Địa chỉ máy chủ** theo endpoint thực tế và **Model ID** đúng tên dịch vụ cung cấp. Giá trị tự điền là gợi ý, cần đối chiếu cổng và đường dẫn API. Runtime phải cung cấp API tương thích với adapter tương ứng.
3. Mở **Nâng cao** nếu cần chọn vai trò/khả năng, phiên bản, giới hạn hoặc số chiều; model embedding có vai trò riêng. Không tùy ý thay tham số nếu chưa biết ảnh hưởng.
4. Bấm **Kiểm tra kết nối** để thử mà chưa lưu, rồi **Kiểm tra & Lưu**. Đọc kết quả từng bước; lựa chọn **Vẫn lưu (chưa dùng được)** chỉ giữ cấu hình khi kiểm tra thất bại, không làm model sẵn sàng. Sau khi sửa dịch vụ, dùng **Kiểm tra** trên thẻ hồ sơ.
5. Vào **2. Phân công AI**, chọn model cho chức năng muốn dùng và bấm **Kiểm tra & Áp dụng**. Có thể xem **Nâng cao** để cấu hình dự phòng, nâng cấp API hoặc giới hạn gọi nếu chính sách cho phép. Kiểm tra kết quả trước khi dùng thật.

LAN Portable đi kèm Ollama sử dụng cổng riêng và launcher có thể đồng bộ endpoint hồ sơ local với cổng gói. Nếu dự định dùng máy model LAN khác, kiểm tra chính sách endpoint và hành vi launcher của phiên bản đó trước; không giả định địa chỉ bạn nhập luôn được giữ nguyên sau khởi động.

## 5. Cấu hình AI API

1. Xác định nhà cung cấp, model ID, Base URL HTTPS, quyền xử lý dữ liệu và chính sách cho phép của tổ chức. Chế độ `API`, allowlist miền, quyền người dùng và cờ xử lý từ xa của danh mục đều có thể ảnh hưởng kết quả. Chế độ LOCAL không tự chuyển ra Internet.
2. Mở **1. Mô hình AI** → **Thêm AI API**. Chọn **Nhà cung cấp** (OpenAI, Gemini hoặc tùy chỉnh), kiểm tra **Base URL**, nhập **Model ID** và **API Key**. Nhà cung cấp tùy chỉnh cần giao thức tương thích adapter. Base URL gợi ý không chứng minh model hoặc khóa hoạt động.
3. Chọn chức năng/vai trò trong **Nâng cao** nếu cần. Bấm **Kiểm tra kết nối**, sau đó **Kiểm tra & Lưu**; xem lỗi chính sách, khóa, kết nối, model hoặc phản hồi. Dùng **Sửa** để thay thông số hoặc nhập khóa mới. Khóa đã lưu không hiển thị lại; trên Windows, kho khóa dùng DPAPI của tài khoản chạy server.
4. Mở **2. Phân công AI**, chọn model ở dòng chức năng tương ứng → **Kiểm tra & Áp dụng**. Với embedding dùng tab riêng dưới đây. Nếu test thất bại, việc chọn vẫn lưu/áp dụng chỉ tạo cấu hình chưa sẵn sàng.

Khóa nhập qua giao diện đi từ trình duyệt đến server; LAN Portable mô tả kết nối HTTP không mã hóa. Chỉ nhập trên đường truyền và máy được tin cậy, hoặc dùng cơ chế bảo vệ truyền tải phù hợp. Kết nối thật OpenAI/Gemini chưa được xác nhận trong báo cáo kiểm thử ngày 08/11; cần kiểm tra bằng tài khoản và chính sách được phép.

## 6. Phân công AI và embedding

| Việc cần đổi | Thao tác | Ảnh hưởng vector |
|---|---|---|
| Model cho **Diễn giải AI** | Trong **2. Phân công AI**, chọn dòng Diễn giải AI, kiểm tra và áp dụng | Không tự tạo lại vector/index. |
| Model tìm theo nghĩa | Tạo hồ sơ vai trò embedding; mở **Embedding (tìm theo nghĩa)** | Preflight và xác nhận tác vụ tạo/bổ sung vector, kiểm chỉ mục mới rồi chuyển; giữ chỉ mục cũ trong thời gian xây dựng và sau khi chuyển. |

Để đổi embedding: tại **Chọn / đổi model embedding**, chọn hồ sơ, quy mô lô và chỉ chọn **Tạo chỉ mục mới từ đầu** khi thực sự cần; bấm **Kiểm tra model**. Xem số chiều, số nút cần tạo, ước tính và các kiểm tra. Nếu đạt, xác nhận tạo tác vụ. Theo dõi tiến độ, lỗi và dùng tạm dừng/tiếp tục/thử lại/hủy theo trạng thái. Worker phải bật; nếu thất bại, chỉ mục đang phục vụ được giữ. Các nút duyệt mới có thể cần **Kiểm tra và bổ sung vector còn thiếu**. Không xóa thủ công chỉ mục cũ để “sửa” lỗi.

## 7. Model local cho Portable offline

Trước khi chuyển, kiểm `MANIFEST.json` của **gói thực tế**: gói LAN theo source đặt Ollama tại `runtime/ollama` và kho model tại `models/ollama`; launcher đặt `OLLAMA_MODELS` trỏ đến kho này và kiểm model có trong manifest phát hành. Không phải mọi gói Portable đều bao gồm Ollama hay cùng cấu trúc.

1. Trên một máy có Internet và được phép, chuẩn bị đúng model, phiên bản và runtime tương thích trong kho Ollama; kiểm tên model và giấy phép. Chuyển bằng thiết bị lưu trữ được phép. Model Ollama gồm manifest và các blob nội dung; chỉ chép một tệp GGUF hoặc một thư mục tên model không đủ để Ollama nhận diện.
2. Trên máy offline, sao lưu gói/kho model, dừng bằng **Stop-Server.bat**. Chuyển đủ manifest và blob tương ứng vào kho `models/ollama` của gói, giữ cấu trúc thư mục và không ghi đè blob/manifest đang dùng nếu chưa kiểm tra. Không chép database, secrets hoặc dữ liệu máy nguồn kèm model.
3. Khởi động lại, xác nhận dịch vụ của gói nhận diện đúng Model ID, sau đó thêm hồ sơ Local và **Kiểm tra kết nối** theo mục 4. Nếu model là embedding, tiếp tục preflight và xác nhận tác vụ riêng ở mục 6; model diễn giải chỉ cần phân công chức năng.

**Giới hạn:** source launcher xác minh các model được liệt kê trong manifest phát hành; model được thêm thủ công không tự trở thành một thành phần được manifest/checksum phát hành chứng thực. Quy trình chép thêm model sau phát hành chưa có bằng chứng kiểm thử riêng trong tài liệu dự án. Nếu yêu cầu xác minh toàn vẹn phát hành hoặc model không được nhận, dùng quy trình phát hành do người vận hành quản lý và kiểm chứng lại gói; không tự sửa checksum để che lỗi. Việc thêm model không đòi hỏi tạo lại vector trừ khi chọn model đó cho embedding.

## 8. Khởi động, dừng, sao lưu và phục hồi

**8.1 Khởi động.** Bấm đúp **Start-Server.bat**, chờ đến khi cửa sổ in địa chỉ truy cập (mọi địa chỉ IP LAN của máy chủ được liệt kê, ví dụ `http://192.168.1.15:8800/`). Chạy lại khi máy chủ đang chạy không tạo tiến trình thứ hai. Gói tự bỏ dấu "blocked" của Windows nếu tải qua Internet/email. Nếu có lỗi, cửa sổ nêu thành phần lỗi; chi tiết ở `logs\launcher.log`. Gói chỉ dùng thành phần trong thư mục của nó và bỏ qua biến môi trường Python/PostgreSQL/Ollama/Tesseract/proxy của máy.

**8.2 Dừng.** Bấm đúp **Stop-Server.bat** và chờ hoàn tất (PostgreSQL dừng bằng `pg_ctl stop -m fast`). Dừng bằng Stop-Server.bat trước khi tắt máy hoặc chép thư mục. Không xóa thư mục `data\` hoặc chép đè `data\postgres` khi đang chạy.

**8.3 Trạng thái và kiểm tra gói.** `tools\Status.bat` hiện tiến trình, cổng, số tài liệu/vector. `tools\Verify-Package.bat` đối chiếu SHA-256 của runtime, model, ứng dụng và tài liệu gốc với `checksums.sha256` (mất vài phút). `MANIFEST.json` liệt kê phiên bản và thành phần.

**8.4 Cho máy khác truy cập (tường lửa).** Gói không đổi cấu hình Windows Firewall. Nếu máy khác không mở được địa chỉ: chạy `tools\Allow-LAN-Firewall.bat` và chấp nhận hộp thoại Administrator (một lần). Quy tắc chỉ mở cổng web (mặc định 8800) cho mạng con nội bộ trên mạng Private/Domain; gỡ bằng `tools\Allow-LAN-Firewall.bat remove`. PostgreSQL (55433) và Ollama (21434) chỉ nghe `127.0.0.1`, không mở ra LAN. Kết nối là HTTP không mã hóa: chỉ dùng trong mạng nội bộ tin cậy.

**8.5 Sao lưu và phục hồi.**
- **Backup-Data.bat** [thư mục đích]: sao lưu nhất quán cơ sở dữ liệu (gồm vector, quyền, nhật ký) và toàn bộ kho tài liệu gốc kèm SHA-256 từng tệp; chạy được khi máy chủ đang chạy. Mặc định ghi vào `backups\backup-<ngày-giờ>\`. Hãy chép bản sao sang ổ khác và bảo vệ quyền truy cập, vì bản sao chứa dữ liệu và phân quyền.
- **Restore-Data.bat** [thư mục sao lưu]: kiểm toàn vẹn, hiện nội dung, yêu cầu gõ `KHOI PHUC`, sao lưu dữ liệu hiện tại vào `backups\pre-restore-*`, dựng cơ sở dữ liệu mới, đối chiếu từng bảng rồi mới chuyển. Dữ liệu cũ giữ ở `data\postgres.before-restore-*` (xóa tay khi chắc chắn). Kho tài liệu chỉ được bổ sung, không xóa tệp. Sau khi phục hồi, kiểm lại tài khoản, quyền, tài liệu và tìm kiếm.

**8.6 Cấu hình (`config\evidence.env`).** Địa chỉ nghe (`EVIDENCE_LISTEN_HOST`), cổng web/PostgreSQL/Ollama (`EVIDENCE_HTTP_PORT`, `EVIDENCE_PG_PORT`, `EVIDENCE_OLLAMA_PORT`), chế độ AI, giới hạn tải lên và thời gian chờ. Sửa xong chạy Stop-Server.bat rồi Start-Server.bat. Đổi cổng nếu bị chương trình khác chiếm (thông báo lỗi nêu tên chương trình). Địa chỉ model cục bộ trong Model Registry được bộ khởi động tự đồng bộ với cổng Ollama của gói. Mật khẩu cơ sở dữ liệu do máy chủ tự sinh ở lần đầu và lưu trong `secrets\`.

**8.7 Chuyển sang máy khác.** Cách an toàn: trên máy cũ chạy Backup-Data.bat và chép thư mục sao lưu; trên máy mới giải nén gói, chạy Start-Server.bat, rồi Restore-Data.bat. Cách nhanh: Stop-Server.bat rồi chép TOÀN BỘ thư mục sang máy mới (đổi ổ, thư mục hoặc tên máy đều được vì đường dẫn tương đối và IP được dò lại mỗi lần chạy); nếu PostgreSQL báo không tương thích thì dùng cách an toàn. Việc chạy trên một máy Windows vật lý khác với máy build chưa được kiểm chứng trong gói này.
## 9. Xử lý lỗi

| Hiện tượng | Cách kiểm tra |
|---|---|
| Không đăng nhập | Kiểm tài khoản, trạng thái khóa, mật khẩu và yêu cầu đổi mật khẩu; liên hệ quản trị viên. |
| Không thấy căn cứ | Kiểm quyền danh mục, nguồn đã duyệt, bộ lọc, cách tìm và ngày hiệu lực; không tự cấp quyền chỉ để có kết quả. |
| Bản gốc không mở | Kiểm phiên và ACL, tình trạng phiên bản, nguồn và hash; đối chiếu log server với người vận hành. |
| Scan không có chữ / không duyệt được | Kiểm Tesseract và dữ liệu ngôn ngữ của gói, tác vụ và xác nhận OCR từng trang. |
| AI kết nối lỗi / `MODEL_NOT_FOUND` | Kiểm dịch vụ, địa chỉ nhìn từ backend, Model ID, adapter, cổng và danh sách model; chạy lại **Kiểm tra kết nối**. |
| `AI_EGRESS_DENIED` | Kiểm chế độ LOCAL/API, allowlist endpoint và chính sách dữ liệu; không tắt bảo vệ chỉ để vượt lỗi. |
| Không tìm theo nghĩa | Xem tab **Embedding**: model, chỉ mục đang hoạt động, worker, vector thiếu và lỗi preflight. Tìm từ khóa có thể vẫn hoạt động. |
| Kết quả chậm / timeout / quá tải | Thu hẹp truy vấn và bộ lọc, thử lại; kiểm tài nguyên máy chủ, DB và model. Lần đầu model local có thể phải nạp vào RAM. |
| Không vào được LAN | Kiểm `tools/Status.bat`, IP/cổng in lúc chạy, mạng Private/Domain và firewall. Không mở cổng PostgreSQL/Ollama ra LAN. |
| Gói báo thiếu tệp hoặc cổng bận | Xem `logs/launcher.log`, chạy Verify-Package; kiểm cấu hình cổng trong `config/evidence.env` và tài liệu gói. Chỉ thay cấu hình khi được phép, sau đó dừng/khởi động lại. |

Các báo cáo tại `docs/evidence/2026-11-08-*` ghi kiểm thử lịch sử trên máy phát triển; chưa thể suy ra việc triển khai cụ thể hoặc một model API mới đã được nghiệm thu.

