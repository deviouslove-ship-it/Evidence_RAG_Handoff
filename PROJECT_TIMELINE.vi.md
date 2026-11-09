# Dòng thời gian dự án và công bố

**Ngôn ngữ / Language:** [English](PROJECT_TIMELINE.md) · Tiếng Việt

Dự án do Vu Tuan Anh tạo ra và sở hữu.

## Trước giai đoạn nộp hồ sơ Kiroween (tháng 10/2026)
- Viết mô tả sản phẩm, đặc tả và kế hoạch triển khai.
- Dựng một khung ban đầu nhưng không đạt thiết kế mong muốn nên dừng.
- Không hoàn thành sản phẩm chạy được trong giai đoạn này.

## Trong giai đoạn nộp hồ sơ Kiroween (30/10 – 09/11/2026)
Bản triển khai hiện tại được xây dựng và hoàn thiện bằng Kiro, gồm:
- Điều chỉnh và thiết kế lại chức năng
- Nâng cấp ứng dụng
- Sinh mã
- Chạy kiểm thử
- Sửa lỗi

Chủ dự án xác nhận Kiro được dùng **từ 30/10/2026 đến hết 09/11/2026**, trên **cả máy cơ quan và máy nhà**. Kiro IDE dùng Claude Sonnet 5.5 và Claude Opus 5.5; công việc do các model này thực hiện trong Kiro được ghi nhận là công việc Kiro hỗ trợ.

## Bằng chứng

| Bằng chứng | Phạm vi | Mức độ |
|---|---|---|
| Nhật ký phiên Kiro lưu cục bộ | 7 phiên trên một máy, từ 05/11 đến 08/11/2026, cùng phiên rà soát ngày 09/11 | Trực tiếp. Chi tiết ở [`KIRO_WORK_SUMMARY.vi.md`](KIRO_WORK_SUMMARY.vi.md) |
| Xác nhận của chủ dự án | 30/10 – 09/11/2026, cả hai máy | Lời xác nhận của chủ dự án. Không có nhật ký cho 30/10 – 04/11 và cho máy còn lại |
| Tái dựng từ code | `.kiro/specs/`, `.kiro/steering/` và mô tả các chức năng đang có | Suy ra từ mã hiện tại. Không phải bản ghi lịch sử của Kiro |

Ghi chú:
- Lịch sử Git chỉ có một tài khoản tác giả và không ghi công cụ nào viết thay đổi. Commit đầu (08/11/2026) là ảnh chụp thư mục làm việc.
- Các tệp `.kiro/specs/`, `.kiro/steering/` và hai hook trong `.kiro/hooks/` được thêm ngày 09/11/2026. Chúng được **dựng lại từ mã nguồn đã triển khai**, không phải spec do Kiro sinh ra trong thời gian phát triển. Tệp Kiro gốc duy nhất trong `.kiro/` là `settings/permissions.yaml`, do Kiro soạn ngày 07/11/2026 và chủ dự án áp dụng.
- Thống kê từ nhật ký còn lưu: 257/471 tệp sản phẩm trong Git (mã, tài liệu, cấu hình) có ít nhất một lệnh ghi/sửa của Kiro; 194 tệp từ nhật ký lịch sử 05/11 đến 09/11 17:19 và 63 tệp lần đầu bị chạm tới ở lượt rà soát hồ sơ hiện tại (specs, steering, hooks, tài liệu song ngữ). 208 tệp có lệnh ghi toàn bộ (`fs_write`). Số tệp là cận dưới, số dòng là cận trên; không gồm máy còn lại và giai đoạn không có nhật ký. Chỉ loại tài liệu pháp luật đầu vào, tệp khóa phụ thuộc, tài sản bên thứ ba và lược đồ sinh tự động; Markdown viết để phát triển dự án vẫn được tính. Phương pháp và danh sách từng tệp: [`KIRO_WORK_SUMMARY.vi.md`](KIRO_WORK_SUMMARY.vi.md) mục 8 và [`KIRO_STATS_APPENDIX.vi.md`](KIRO_STATS_APPENDIX.vi.md).

## Chưa xác minh
Chưa nghiệm thu nghiệp vụ kết quả tìm kiếm, không dùng bộ câu hỏi Gold để chấm AI (ADR-010), chưa chạy gói Portable trên máy Windows vật lý thứ hai, chưa kết nối thật OpenAI/Gemini. Xem `KIRO_WORK_SUMMARY.vi.md` mục 9 và `docs/implementation-status.md`.

## Giấy phép
Cấp phép theo Apache License 2.0. Xem `LICENSE` và `NOTICE`.
