EVIDENCE RAG - BẢN CHẠY DI ĐỘNG CHO MẠNG LAN (WINDOWS, OFFLINE)
================================================================

Ngôn ngữ / Language: Tiếng Việt (bản gốc) · English: README.en.txt cùng thư mục.
Hướng dẫn sử dụng đầy đủ: HUONG_DAN_SU_DUNG.vi.md (tiếng Việt) và USER_GUIDE.en.md (English), cùng thư mục.

Mọi thứ nằm trong thư mục này: giao diện web, máy chủ FastAPI, PostgreSQL + pgvector (cơ sở dữ
liệu, chỉ mục, vector), kho tài liệu gốc, Tesseract OCR tiếng Việt, Ollama và các model AI cục bộ.
Không cần Internet, không cần cài Python, Node.js, PostgreSQL, Ollama hay Tesseract.
Máy trạm chỉ cần trình duyệt.

YÊU CẦU MÁY CHẠY
  - Windows 10 / Windows Server 2016 trở lên, 64-bit; PowerShell 5.1 (có sẵn trong Windows).
  - Dung lượng trống: khoảng 6 GB cho gói và dữ liệu; RAM nên từ 8 GB (model AI chạy trên CPU).
  - Giải nén TOÀN BỘ gói vào một thư mục có đường dẫn ngắn, ví dụ D:\EvidenceRAG
    (tránh thư mục sâu; đường dẫn dưới 120 ký tự). Không chạy trực tiếp trong tệp ZIP.
  - Không cần quyền Administrator để chạy. Chỉ cần khi mở cổng tường lửa (mục 4).

1. KHỞI ĐỘNG
  Bấm đúp  Start-Server.bat  (không cần gõ lệnh nào khác). Chương trình lần lượt:
    [1] kiểm tra runtime, model, cơ sở dữ liệu, cổng mạng, cấu hình;
    [2] khởi động PostgreSQL + pgvector riêng của gói (dữ liệu trong data\postgres);
    [3] khởi động Ollama của gói (chỉ nghe 127.0.0.1, model ở models\ollama);
    [4] khởi động máy chủ web/API (FastAPI);
    [5] kiểm tra sẵn sàng (web, API, model embedding và model sinh văn bản chạy offline);
    [6] in địa chỉ truy cập qua IP LAN, ví dụ  http://192.168.1.15:8800/
  Lần chạy ĐẦU TIÊN mất thêm 1-3 phút: gói tự khởi tạo cơ sở dữ liệu riêng từ bản dữ liệu gốc
  (thư mục seed\), rồi đối chiếu nội dung từng bảng với bản gốc trước khi dùng. Dữ liệu, vector
  và chỉ mục được khôi phục nguyên trạng, KHÔNG nạp lại tài liệu, KHÔNG OCR lại, KHÔNG tạo lại
  vector. Các lần sau khởi động trong vài chục giây.
  Chạy lại Start-Server.bat khi máy chủ đang chạy thì không tạo tiến trình thứ hai.
  Nếu có lỗi, cửa sổ ghi rõ thành phần nào thiếu hoặc lỗi; chi tiết ở  logs\launcher.log.

2. NGƯỜI DÙNG TRONG LAN
  Gửi địa chỉ http://<IP máy chủ>:8800/ cho người dùng; họ mở bằng trình duyệt.
  Tài khoản, vai trò, quyền theo danh mục (ACL) và nhật ký kiểm toán được giữ trong cơ sở dữ liệu của gói.
  Mỗi tài khoản demo có mật khẩu riêng, dùng ngay được; mật khẩu được bàn giao riêng, KHÔNG nằm trong gói.
  Đổi mật khẩu sau khi nhận (xem HUONG_DAN_SU_DUNG.vi.md, mục 0).
  Phiên đăng nhập cũ không được mang theo, mọi người đăng nhập lại.

3. DỪNG
  Bấm đúp  Stop-Server.bat. Chỉ dừng đúng các tiến trình chạy từ thư mục này (web, Ollama,
  PostgreSQL bằng pg_ctl stop -m fast); không ảnh hưởng PostgreSQL/Ollama/Python khác trên máy.
  Nên dừng bằng Stop-Server.bat trước khi tắt máy hoặc sao chép thư mục.

4. MỞ CỔNG CHO CÁC MÁY KHÁC (WINDOWS FIREWALL)
  Gói không tự đổi Windows Firewall. Nếu máy khác không mở được địa chỉ:
    - Bấm đúp  tools\Allow-LAN-Firewall.bat  và đồng ý hộp thoại quyền Administrator (một lần).
      Quy tắc tạo ra chỉ cho phép cổng web (mặc định 8800), từ mạng con nội bộ, trên mạng
      Private/Domain. Gỡ bằng:  tools\Allow-LAN-Firewall.bat remove
    - Hoặc khi Windows hỏi "cho phép python.exe truy cập mạng", chọn mạng Private.
  PostgreSQL (55433) và Ollama (21434) chỉ nghe 127.0.0.1, không cần và không nên mở ra mạng.
  Kết nối là HTTP không mã hóa: chỉ dùng trong mạng nội bộ tin cậy.

5. SAO LƯU VÀ KHÔI PHỤC
  Backup-Data.bat [thư mục đích]
    Sao lưu cơ sở dữ liệu (kể cả vector, ACL, audit) bằng ảnh chụp nhất quán và toàn bộ kho tài liệu
    gốc, kèm mã SHA-256 từng tệp. Có thể chạy khi máy chủ đang hoạt động. Mặc định ghi vào
    backups\backup-<ngày-giờ>\. Nên chép thư mục sao lưu sang ổ khác.
  Restore-Data.bat [thư mục sao lưu]
    Kiểm tra toàn vẹn bản sao lưu, hiển thị nội dung, yêu cầu gõ  KHOI PHUC  để xác nhận,
    tự sao lưu dữ liệu hiện tại vào backups\pre-restore-*, dựng cơ sở dữ liệu mới, đối chiếu
    từng bảng rồi mới thay. Dữ liệu cũ được giữ ở data\postgres.before-restore-* (xóa tay khi
    chắc chắn). Kho tài liệu chỉ được bổ sung, không xóa tệp nào.
  Không bao giờ xóa thư mục data\ hay sao chép đè lên data\postgres khi máy chủ đang chạy.

6. CHUYỂN SANG MÁY KHÁC
  Cách an toàn nhất (không phụ thuộc phiên bản/CPU của máy):
    a) Trên máy cũ: Backup-Data.bat, rồi chép thư mục sao lưu.
    b) Trên máy mới: giải nén gói phát hành, chạy Start-Server.bat, rồi Restore-Data.bat <thư mục sao lưu>.
  Cách nhanh: chạy Stop-Server.bat, chép NGUYÊN thư mục sang máy mới (đổi ổ đĩa, thư mục, tên máy
  đều được: mọi đường dẫn là tương đối, địa chỉ IP dò lại mỗi lần chạy). Nếu PostgreSQL báo
  không tương thích thì dùng cách an toàn ở trên; Start-Server.bat không tự xóa hay ghi đè dữ liệu.
  Hiện gói đã được kiểm thử chạy ở thư mục/ổ đĩa khác trên máy phát triển; việc chuyển sang máy
  Windows vật lý khác CHƯA được kiểm chứng.

7. CẤU HÌNH  (config\evidence.env)
  Địa chỉ nghe, cổng web, cổng PostgreSQL/Ollama, chế độ AI, giới hạn. Sửa xong chạy Stop-Server.bat
  rồi Start-Server.bat. Đổi cổng nếu bị chương trình khác chiếm (thông báo lỗi nêu rõ chương trình).
  Hồ sơ model, phân công AI và embedding chỉnh trong Admin Portal > Mô hình AI. Địa chỉ model cục bộ
  trong Registry được bộ khởi động đồng bộ với cổng Ollama đi kèm (cổng 21434), không phụ thuộc
  Ollama đã cài sẵn trên máy (nếu có).
  Model Local đi kèm: xem MANIFEST.json (qwen3:1.7b cho Diễn giải AI, mở rộng tìm kiếm, xếp hạng,
  gán nhãn, quan hệ; qwen3-embedding:0.6b cho tìm theo nghĩa).

8. KIỂM TRA GÓI
  tools\Verify-Package.bat   so SHA-256 mọi tệp runtime, model, ứng dụng, tài liệu gốc với
                             checksums.sha256 của bản phát hành (mất vài phút).
  tools\Status.bat           xem tiến trình, cổng, số tài liệu/vector.
  MANIFEST.json              liệt kê runtime, phiên bản, model, dung lượng, thành phần.

9. SỰ CỐ THƯỜNG GẶP
  - "Cổng ... đang được chương trình khác dùng": đổi cổng trong config\evidence.env.
  - "Thiếu thành phần": gói bị chép thiếu hoặc diệt virus xóa tệp. Giải nén lại gói; chạy
    tools\Verify-Package.bat để biết tệp nào hỏng.
  - Gói tải qua Internet/email bị Windows đánh dấu "blocked": Start-Server.bat tự gỡ dấu này.
  - Model AI chậm: model chạy trên CPU; lượt đầu sau khi khởi động cần nạp model vào RAM.
  - Log: logs\launcher.log (khởi động/dừng), logs\backend.err.log, logs\postgres.log, logs\ollama.err.log.

10. BẢO MẬT
  - Chỉ máy chủ web lắng nghe LAN; PostgreSQL và Ollama chỉ nghe 127.0.0.1.
  - Mật khẩu cơ sở dữ liệu do máy này tự sinh ngẫu nhiên khi khởi tạo, lưu trong secrets\ (không chia sẻ
    thư mục này). Khóa API (nếu dùng chế độ API) được mã hóa DPAPI theo tài khoản Windows chạy máy chủ.
  - Gói không chứa API key, token hay phiên đăng nhập.
