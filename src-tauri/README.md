# Evidence RAG — Windows Desktop Shell (Tauri 2)

Shell native dành cho USER trên Windows theo mục C.12 và D.5 S14 của hồ sơ bàn giao.

## Cửa sổ và hành vi

- `main`: cửa sổ nền đục (`transparent: false`, `decorations: true`, `minWidth: 360`, `minHeight: 520`), dùng cho đăng nhập, khung chat tra cứu, trình xem PDF nguồn và không gian làm việc.
- `orb`: cửa sổ nổi tròn (`url: index.html#/orb`, `72x72` logical px, `transparent: true`, `decorations: false`, `shadow: false`, `alwaysOnTop: true`, `skipTaskbar: true`), chỉ hiển thị sau khi đăng nhập (`session_started`), neo ở cạnh phải vùng làm việc (`work area`) của màn hình hiện tại và luôn được kẹp (`clamp`) vào trong màn hình.
- Đóng cửa sổ `main` khi đang trong phiên sẽ thu về Orb / khay hệ thống thay vì thoát đột ngột.

## Lệnh IPC (`window.__TAURI__.core.invoke`)

- `session_started`: bật trạng thái phiên, đặt vị trí và hiển thị cửa sổ `orb`.
- `session_ended`: tắt trạng thái phiên, ẩn `orb`, hiện lại cửa sổ `main`.
- `toggle_panel`: mở hoặc thu cửa sổ `main` cạnh `orb` trong phạm vi `work area`.
- `drag_orb_window({ dx, dy })`: di chuyển vị trí cửa sổ `orb` tức thì theo độ lệch chuột `(dx, dy)` có kẹp an toàn vào màn hình hiện tại.
- `orb_drag_finished`: kẹp lại vị trí `orb` vào màn hình gần nhất và lưu tọa độ vào `shell-state.json`.
- `open_evidence_in_workspace({ response, selected, question, accessToken })`: hiển thị và đưa cửa sổ `main` lên trước, đồng thời phát sự kiện `evidence-orb-sync-workspace` nạp câu hỏi, danh sách căn cứ và phiên làm việc vào không gian tra cứu chính.
- `set_always_on_top({ alwaysOnTop })`: bật/tắt ghim nổi cho cửa sổ `main`.
- `quit_app`: thoát hoàn toàn ứng dụng.

## Sự kiện

- `evidence-logout-requested` (và `CustomEvent('evidence:logout')`): phát từ menu khay hệ thống **Đăng xuất** tới cửa sổ `main` để xoá token và kết thúc phiên.
- `evidence-orb-sync-workspace`: phát từ `open_evidence_in_workspace` tới cửa sổ `main` để đồng bộ ngữ cảnh tra cứu từ Orb.

## Tách biệt Web & Native Shell

- Biểu tượng và cửa sổ **Orb nổi tròn** (`#/orb`) chỉ kích hoạt khi chạy trong môi trường Windows Native Desktop Tauri 2 (kiểm tra qua `window.__TAURI__`).
- Trên trình duyệt Web thông thường, biểu tượng Orb và thanh công cụ desktop được ẩn tự động để đảm bảo giao diện gọn gàng, không bị thừa hay xung đột vị trí.
