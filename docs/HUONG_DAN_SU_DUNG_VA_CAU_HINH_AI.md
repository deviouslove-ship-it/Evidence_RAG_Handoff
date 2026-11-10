# Hướng dẫn sử dụng và cấu hình AI Evidence RAG

**Ngôn ngữ / Language:** Tiếng Việt · [English](en/USER_ADMIN_AND_AI_GUIDE.md)

Đối chiếu giao diện và source ngày 09/11/2026. Tên nút dưới đây thuộc source hiện tại; gói đang chạy có thể là bản khác. Xem [mô tả hệ thống](TAI_LIEU_MO_TA_HE_THONG.md) để hiểu kiến trúc và giới hạn. Chỉ thực hiện các thao tác quản trị, thay model, phục hồi hoặc thay cấu hình khi có quyền và sau khi hiểu ảnh hưởng tới hệ thống.

## Mục lục

1. [Đăng nhập và tra cứu](#1-đăng-nhập-và-tra-cứu)
2. [Nhập, OCR và duyệt nguồn](#2-nhập-ocr-và-duyệt-nguồn) · [Quản lý văn bản](#quản-lý-văn-bản)
3. [Danh mục, tài khoản và kiểm toán](#3-danh-mục-tài-khoản-và-kiểm-toán)
4. [Cấu hình AI Local](#4-cấu-hình-ai-local)
5. [Cấu hình AI API](#5-cấu-hình-ai-api)
6. [Phân công AI và embedding](#6-phân-công-ai-và-embedding)
7. [Model local cho Portable offline](#7-model-local-cho-portable-offline)
8. [Khởi động, dừng, sao lưu và phục hồi](#8-khởi-động-dừng-sao-lưu-và-phục-hồi)
9. [Xử lý lỗi](#9-xử-lý-lỗi)

## 1. Đăng nhập và tra cứu

1. Mở địa chỉ do người vận hành cung cấp trên trình duyệt, chọn **Đăng nhập**, nhập tài khoản và mật khẩu được cấp. Nếu được yêu cầu, dùng **Đổi mật khẩu** trước khi tiếp tục. Không dùng chung tài khoản.
2. Tại **Hỏi đáp có căn cứ**, nhập câu hỏi rõ nội dung, số hiệu và Điều nếu biết; gửi câu hỏi. Có thể dừng hoặc thử lại lượt đang xử lý. Đọc câu trả lời và từng thẻ văn bản, nhãn Điều/Khoản, trích đoạn và hiệu lực. “Chưa tìm thấy” nghĩa là không tìm thấy căn cứ phù hợp trong phạm vi và kho hiện tại, không chứng minh quy định không tồn tại. Màn hình gồm hai khung: khung trái **Hỏi đáp** giữ lịch sử câu hỏi và câu trả lời ngắn của phiên (kèm số trích dẫn [1], [2]…, ô nhập và phạm vi danh mục ở đáy); khung phải **Kết quả và căn cứ** hiển thị văn bản, Điều/Khoản/Điểm, trích đoạn, hiệu lực của câu hỏi đang chọn. Bấm một câu hỏi cũ để xem lại kết quả của nó (không tra cứu lại); bấm số [n] để cuộn tới căn cứ tương ứng. Kéo thanh giữa để đổi độ rộng (được nhớ cho lần sau). Cửa sổ hẹp gộp thành hai tab “Hỏi đáp” và “Kết quả”. Lịch sử chỉ nằm trong phiên làm việc và bị xóa khi đăng xuất. Nút **Diễn giải AI** áp dụng cho cả tập căn cứ của câu hỏi đang chọn.
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

## 3. Danh mục, tài khoản và kiểm toán

- **Danh mục**: SYS_ADMIN tạo/sửa danh mục, mã, tên và tùy chọn cho phép xử lý từ xa. Đánh dấu cho phép không tự vượt qua chính sách egress hay quyền tài khoản. Xóa mềm danh mục ảnh hưởng quyền truy cập tương ứng.
- **Tài khoản & Phân quyền**: tạo hoặc sửa tài khoản, vai trò, trạng thái và danh mục được phép (xem mục "Quyền theo danh mục" ngay dưới); kiểm tra nhu cầu thực trước khi cấp. Vai trò quản trị không tự cấp quyền đọc mọi tài liệu. Tài khoản mới/đặt lại có thể phải đổi mật khẩu.
- **Quyền theo danh mục**: admin cấp quyền cho từng tài khoản trong **Tài khoản & Phân quyền**, ở hai ô **Danh mục được phép tra cứu (ABAC)** (danh mục tài khoản được tra cứu và mở tài liệu) và **Danh mục được xác nhận hiệu lực (người duyệt)** (ô này chỉ hiện khi tài khoản có vai trò REVIEWER), rồi bấm **Lưu tài khoản**. Tài khoản chưa được cấp danh mục nào thì không thấy văn bản nào. Khi khởi tạo, `chuyenvien` đã được sẵn quyền tra cứu các danh mục thử; `curator` và `reviewer` thấy danh sách trống cho đến khi admin cấp. Vai trò (RBAC) quyết định được làm gì, danh mục (ABAC) quyết định thấy văn bản nào; người dùng không thể tự duyệt bản do chính mình gửi duyệt.
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

Áp dụng cho gói có các BAT trong `deploy/lan-portable/`; bản `deploy/portable/` dùng `start.cmd`/`stop.cmd` và có cách khởi tạo riêng. Không nhầm source launcher với một gói đã đóng đủ runtime.

1. Giải nén đầy đủ gói LAN vào thư mục trên Windows 64-bit, kiểm manifest và tài liệu kèm gói. Bấm **Start-Server.bat** và chờ kiểm tra sẵn sàng; cửa sổ in địa chỉ `http://<IP máy chủ>:<cổng>/`. Lần đầu có thể mất lâu hơn do khởi tạo. Không đóng cưỡng bức hoặc chép đè dữ liệu khi DB đang chạy.
2. Từ máy trạm cùng mạng, mở địa chỉ được in và đăng nhập. Nếu không kết nối được, kiểm IP/cổng, mạng và Windows Firewall. `tools/Allow-LAN-Firewall.bat` là thao tác quản trị cần quyền Administrator; xem chính sách mạng trước khi chạy. DB và Ollama được thiết kế chỉ nghe loopback; HTTP web không mã hóa.
3. Khi cần dừng, chạy **Stop-Server.bat** và chờ hoàn tất. `tools/Status.bat` xem trạng thái; `tools/Verify-Package.bat` đối chiếu checksum của bản phát hành.
4. Chạy **Backup-Data.bat** để tạo bản sao nhất quán DB và kho tệp, hoặc chỉ định thư mục đích theo README gói. Kiểm kết quả, bảo vệ và lưu bản sao ở vị trí khác. Bản sao chứa dữ liệu và phân quyền, cần kiểm soát quyền truy cập.
5. Để khôi phục, dùng **Restore-Data.bat** với thư mục backup theo README gói. Đọc nội dung và kiểm toàn vẹn; thao tác yêu cầu nhập `KHOI PHUC`, tự tạo bản sao trước phục hồi và giữ dữ liệu cũ theo mô tả launcher. Xác nhận chỉ khi đã chọn đúng bản sao và hiểu sẽ thay dữ liệu đang dùng. Kiểm lại tài khoản, quyền, tài liệu và tìm kiếm sau phục hồi.

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
