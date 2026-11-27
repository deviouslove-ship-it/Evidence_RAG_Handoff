**Ngôn ngữ / Language:** [English](DESIGN.md) · Tiếng Việt

# Evidence RAG — Hệ thống thiết kế giao diện

## 1. Chữ và toàn vẹn dấu tiếng Việt
- **Font giao diện và font đọc chính (`--font-body`, `--font-reading`)**: `"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif`
  - Chọn để bảo đảm phủ 100% glyph tiếng Việt dựng sẵn (`ấ, ầ, ẩ, ẫ, ậ, ố, ồ, ổ, ỗ, ộ, ớ, ờ, ở, ỡ, ợ, ứ, ừ, ử, ữ, ự, đ`) trên Windows, không phụ thuộc codepage ANSI/OEM của hệ điều hành, tránh fallback sang glyph CJK bị tách dấu.
- **Monospace (`--font-mono`)**: `"Cascadia Mono", "Consolas", monospace` cho mã băm SHA-256, số hiệu văn bản và trace ID.

## 2. Token màu
- **Xanh navy thương hiệu (`--color-brand-navy`)**: `#163a5f`
- **Hành động chính (`--color-action`)**: `#2563eb` (hover `#1d4ed8`)
- **Nền và bề mặt**: canvas `#f8fafc`, thẻ/khung `#ffffff`, vùng nền phụ `#f1f5f9`
- **Trạng thái ngữ nghĩa**:
  - Đã xác minh / Đang hiệu lực (`--color-success`): `#047857` trên `#ecfdf5`
  - Chưa xác minh / Cần lưu ý (`--color-warning`): `#92400e` trên `#fffbeb`
  - Lỗi / Bị từ chối (`--color-danger`): `#b91c1c` trên `#fef2f2`

## 3. Bố cục desktop nhiều khung nhìn
- **Thanh trên**: cao cố định `64px`, flexbox có chống xuống dòng, bộ chuyển bề mặt, viên chế độ và điều khiển phiên.
- **Không gian 3 khung (`>= 1024px`)**:
  - Khóa `height: calc(100vh - 64px)` để ba khung cuộn độc lập và ô soạn chat luôn hiện ở góc dưới bên trái.
  - Cao đầu khung đồng bộ `72px` trên cả ba khung (`.pane-header` và `.viewer-toolbar`) để các đường chia ngang thẳng hàng trên suốt chiều rộng màn hình.
- **Dock trợ lý chat nổi (`ChatAgentDock`)**:
  - Cố định góc dưới bên phải (`right: 24px; bottom: 24px; z-index: 850`), mở ngăn Trợ lý chat bằng một lần bấm từ mọi màn hình (không gian người dùng hoặc Cổng quản trị) và thu về Orb gốc của Tauri khi chạy chế độ Desktop.
