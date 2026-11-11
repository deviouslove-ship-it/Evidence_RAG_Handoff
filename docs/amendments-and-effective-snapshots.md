# Amendments and effective snapshots

Quan hệ sửa đổi được review như một thay đổi riêng của node. CURATOR tạo draft; REVIEWER duyệt trước khi edge tham gia snapshot. Một tài liệu sửa một khoản không làm mất hiệu lực của các khoản khác.

Snapshot đăng ký là staged rồi publish nguyên tử. Mỗi run có `snapshot_revision`; từ thời điểm evidence được pin, mọi nguồn trong run phải dùng cùng snapshot. Nếu snapshot stale hoặc graph không xác định, hệ thống trả temporal unknown và chặn kết luận pháp lý.

## Cập nhật theo mã nguồn hiện hành (`backend/app/effectivity/`)

- Quan hệ trong `node_amendments` (migration `0011_effectivity.sql`) có thể ở phạm vi văn bản (`scope = 'document'`) hoặc phạm vi điều khoản (`scope = 'node'`), được sinh từ bộ đọc quy tắc (`extract.py`), đề xuất AI giai đoạn `relation` (`ai.py`) hoặc người tạo.
- Chỉ `REVIEWER` khác người đề xuất và có quyền `can_review` trên danh mục của văn bản nguồn hoặc đích mới được phê duyệt (`service.py`). Với quan hệ phạm vi `node`, hệ thống yêu cầu phải có `target_node_id` đã gắn trước khi duyệt (thiếu sẽ bị từ chối với mã `RELATION_TARGET_REQUIRED`).
- Mỗi lần duyệt nguồn, duyệt quan hệ hoặc xác nhận/thu hồi hiệu lực đều tự động xuất bản snapshot mới (giữ 3 bản gần nhất) và ghi nhật ký kiểm toán chuỗi băm cùng `superseded_by`.
