# Schema node effectivity

Mỗi node có review status và validity riêng. Quan hệ sửa đổi là đồ thị có hướng giữa các node đã được duyệt. Resolver chạy đến fixed point, không dừng ở hai hop của context BFS.

Trạng thái đầu ra:

- `active`: không có cạnh hiệu lực;
- `modified`/`repeal`/`suspend`: theo cạnh đã duyệt;
- `unknown`: cycle, conflict, missing edge, unverified relation hoặc resource guard.

Snapshot được stage rồi publish nguyên tử theo `snapshot_revision`; cache phải recheck revision và ACL. Worker lỗi khiến snapshot stale và hệ thống fail-closed.

## Cập nhật theo mã nguồn hiện hành (migration `0011_effectivity.sql`, `backend/app/effectivity/`)

- **Mô hình hai trục (ADR-008):**
  - Trục A (`effective_status` / `status`): `active`, `not_yet_effective`, `modified` (cấp văn bản: `partially_modified`), `suspended`, `repealed`, `replaced`, `unknown`.
  - Trục B (`verification_state`): `verified`, `unverified`, `not_found`. Trạng thái `active` + `verified` chỉ sinh từ bản xác nhận của người (`effectivity_attestations`).
- **Phân cấp văn bản và điều khoản:** `document_effective_intervals` lưu khoảng hiệu lực cấp văn bản; `node_effective_intervals` lưu ngoại lệ cấp nút (kèm cây con). Trạng thái chấm dứt của cả văn bản (`repealed`, `replaced`, `suspended`, `not_yet_effective`) thắng ngoại lệ cấp nút.
- **Quan hệ phạm vi `node` (`node_amendments.scope = 'node'`):** hỗ trợ `replace`, `suspend`, `modify`, `repeal_partial`. Sau khi được duyệt và xuất bản snapshot, `replace` tạo khoảng `replaced` (`verified`), `repeal_partial` tạo khoảng `repealed` (`verified`), `suspend` tạo khoảng `suspended` (`verified`), và `modify` tạo khoảng `modified` (`unverified`).
