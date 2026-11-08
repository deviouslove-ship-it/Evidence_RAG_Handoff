# Schema node effectivity

Mỗi node có review status và validity riêng. Quan hệ sửa đổi là đồ thị có hướng giữa các node đã được duyệt. Resolver chạy đến fixed point, không dừng ở hai hop của context BFS.

Trạng thái đầu ra:

- `active`: không có cạnh hiệu lực;
- `modified`/`repeal`/`suspend`: theo cạnh đã duyệt;
- `unknown`: cycle, conflict, missing edge, unverified relation hoặc resource guard.

Snapshot được stage rồi publish nguyên tử theo `snapshot_revision`; cache phải recheck revision và ACL. Worker lỗi khiến snapshot stale và hệ thống fail-closed.
