# Spec: Windows LAN Portable (offline), bản dịch

**Ngôn ngữ / Language:** Tiếng Việt · bản chuẩn: [`.kiro/specs/windows-lan-portable/`](../../../../.kiro/specs/windows-lan-portable/)

> Spec dựng lại từ mã nguồn đã triển khai ngày 09/11/2026 (`Spec reconstructed from the implemented code on 2026-11-09`). Không phải spec lịch sử do Kiro tạo. Hướng dẫn vận hành: `deploy/lan-portable/README.txt` (tiếng Anh: `README.en.txt`).

## Giới thiệu
Một thư mục chạy toàn bộ hệ thống trên Windows 64-bit không cần Internet và không cần cài Python, Node.js, PostgreSQL, Ollama hay Tesseract. Máy trạm chỉ cần trình duyệt.

## Yêu cầu (EARS)

**Y1. Khởi động một lệnh.**
1. WHEN người vận hành chạy `Start-Server.bat` THE SYSTEM SHALL kiểm runtime, model, cơ sở dữ liệu, cổng, cấu hình; khởi động PostgreSQL kèm pgvector, Ollama và máy chủ web/API đóng kèm; kiểm sẵn sàng và in địa chỉ LAN.
2. WHEN chạy lần hai khi đang chạy THE SYSTEM SHALL KHÔNG tạo tiến trình thứ hai.
3. IF thiếu thành phần hoặc cổng bận THEN THE SYSTEM SHALL nêu tên và ghi chi tiết vào `logs/launcher.log`.

**Y2. Lần chạy đầu từ bản dữ liệu gốc (seed).**
1. WHEN lần chạy đầu chưa có cơ sở dữ liệu THE SYSTEM SHALL khởi tạo từ seed đóng kèm, đối chiếu nội dung các bảng với seed, và khôi phục dữ liệu, vector, chỉ mục mà không nạp lại, không OCR lại, không tạo lại embedding.
2. THE SYSTEM SHALL KHÔNG chứa mật khẩu dạng rõ; tài khoản, vai trò, ACL và audit lấy từ seed.

**Y3. Mở mạng.**
1. THE SYSTEM SHALL chỉ nghe LAN ở cổng web (mặc định 8800); PostgreSQL (55433) và Ollama (21434) SHALL chỉ nghe `127.0.0.1`.
2. THE SYSTEM SHALL KHÔNG tự đổi Windows Firewall; `tools/Allow-LAN-Firewall.bat` SHALL chỉ thêm quy tắc cho cổng web, mạng con cục bộ, profile Private/Domain, sau hộp thoại quyền quản trị, và SHALL hỗ trợ `remove`.
3. THE SYSTEM SHALL nêu rõ kết nối là HTTP không mã hóa, chỉ phù hợp mạng tin cậy.

**Y4. Dừng, trạng thái, kiểm gói.**
1. WHEN chạy `Stop-Server.bat` THE SYSTEM SHALL chỉ dừng tiến trình khởi động từ thư mục gói (PostgreSQL dừng nhanh).
2. THE SYSTEM SHALL cung cấp `tools/Status.bat` và `tools/Verify-Package.bat`, so SHA-256 của runtime, model, ứng dụng và tệp gốc với `checksums.sha256` của bản phát hành.

**Y5. Sao lưu và phục hồi.**
1. WHEN chạy `Backup-Data.bat` THE SYSTEM SHALL ghi ảnh chụp nhất quán của cơ sở dữ liệu và kho tệp gốc kèm SHA-256 từng tệp, khi máy chủ đang chạy.
2. WHEN chạy `Restore-Data.bat` THE SYSTEM SHALL kiểm toàn vẹn, hiển thị nội dung, yêu cầu gõ `KHOI PHUC`, sao lưu dữ liệu hiện tại vào `backups\pre-restore-*`, dựng cơ sở dữ liệu mới, đối chiếu bảng rồi mới chuyển và giữ thư mục dữ liệu cũ.
3. THE SYSTEM SHALL chỉ bổ sung vào kho tài liệu khi phục hồi và không bao giờ xóa tệp.

**Y6. Cấu hình và tính di động.**
1. THE SYSTEM SHALL đọc cổng, địa chỉ nghe, chế độ AI và giới hạn từ `config\evidence.env`, chỉ dùng đường dẫn tương đối và IP dò lúc chạy.
2. THE SYSTEM SHALL đồng bộ endpoint hồ sơ model local với cổng Ollama đóng kèm khi khởi động.
3. THE SYSTEM SHALL sinh mật khẩu cơ sở dữ liệu ngẫu nhiên khi khởi tạo và lưu ở `secrets\`; khóa API SHALL được mã hóa DPAPI theo tài khoản Windows.

**Y7. Công cụ đóng gói.**
1. THE SYSTEM SHALL cung cấp `scripts/build-lan-portable.ps1` để dựng gói ngoài repository; gói phát hành (khoảng 4,5 GB, zip 3,6 GB) SHALL KHÔNG được commit.

## Thiết kế (tóm tắt)

| Mục | Vai trò |
|---|---|
| `Start-Server.bat`, `Stop-Server.bat` | Điểm vào của người vận hành |
| `Backup-Data.bat`, `Restore-Data.bat` | Sao lưu và phục hồi có kiểm soát |
| `tools/portable.ps1`, `portable-lib.ps1` | Logic launcher |
| `tools/Allow-LAN-Firewall.bat`, `Status.bat`, `Verify-Package.bat` | Tường lửa, trạng thái, kiểm checksum |
| `config/evidence.env` | Cổng, địa chỉ nghe, chế độ AI, giới hạn |
| `README.txt` / `README.en.txt` | Hướng dẫn vận hành (Việt / Anh) |
| `scripts/build-lan-portable.ps1` | Công cụ dựng gói, chạy trên máy phát triển |

Gói đơn giản hơn ở `deploy/portable/` (`start.cmd`, `stop.cmd`, `evidence.ps1`, dựng bằng `scripts/package-portable.ps1`) không có OCR (Tesseract) và không có ứng dụng desktop, tạo cơ sở dữ liệu trống ở lần chạy đầu.

Runtime: trình duyệt LAN → HTTP :8800 → FastAPI + giao diện web đã build → PostgreSQL + pgvector (127.0.0.1:55433), Ollama (127.0.0.1:21434), Tesseract `vie`, kho tệp gốc theo SHA-256.

Quyết định: chỉ dùng đường dẫn tương đối và dò IP mỗi lần chạy để thư mục chuyển được giữa ổ và máy; khôi phục từ seed thay vì nạp lại để tránh lặp OCR và embedding; launcher kiểm các model có trong manifest phát hành, model thêm tay không nằm trong checksum manifest (hướng dẫn mục 7).

Đã kiểm trên máy phát triển: chạy từ thư mục/ổ khác và kiểm thử chấp nhận ghi trong phiên. Chưa kiểm: chuyển sang máy Windows vật lý khác, bản Windows mới cài, antivirus của máy đích.

## Tasks
- [x] 1. Script launcher và điểm vào batch
- [x] 2. Lần chạy đầu từ seed, đối chiếu bảng
- [x] 3. Sao lưu và phục hồi có kiểm soát
- [x] 4. Công cụ tường lửa có tùy chọn gỡ
- [x] 5. Công cụ kiểm gói và trạng thái
- [x] 6. Công cụ dựng gói
- [x] 7. Hướng dẫn vận hành tiếng Việt (`README.txt`) và tiếng Anh (`README.en.txt`)
- [x] 8. Gói một thư mục đơn giản hơn (`deploy/portable/`)
- [ ] 9. Thử trên máy Windows vật lý thứ hai (chưa làm)
- [ ] 10. Wrapper dịch vụ Windows và TLS (chưa có)
