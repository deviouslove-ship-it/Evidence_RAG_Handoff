# Amendments and effective snapshots

Quan hệ sửa đổi được review như một thay đổi riêng của node. CURATOR tạo draft; REVIEWER duyệt trước khi edge tham gia snapshot. Một tài liệu sửa một khoản không làm mất hiệu lực của các khoản khác.

Snapshot đăng ký là staged rồi publish nguyên tử. Mỗi run có `snapshot_revision`; từ thời điểm evidence được pin, mọi nguồn trong run phải dùng cùng snapshot. Nếu snapshot stale hoặc graph không xác định, hệ thống trả temporal unknown và chặn kết luận pháp lý.
