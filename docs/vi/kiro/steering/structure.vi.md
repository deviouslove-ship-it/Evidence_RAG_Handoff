# Cấu trúc repository (bản dịch)

**Ngôn ngữ / Language:** Tiếng Việt · bản chuẩn: [`.kiro/steering/structure.md`](../../../../.kiro/steering/structure.md)

> Bản dịch tham khảo. Steering dựng lại từ cấu trúc repository ngày 09/11/2026; không phải steering lịch sử của Kiro.

```text
backend/app/
  api/v1/         Route HTTP: auth, user, admin, comprehensive, effectivity, synthesis
  auth_acl/       mật khẩu, chính sách RBAC/ABAC, phiên
  documents/      nhập, chuyển đổi, PDF gốc, OCR, parser cây, span, duyệt, management_*
  effectivity/    bộ đọc quy tắc, resolver, store, đề xuất AI
  evidence/       ánh xạ và kiểm căn cứ
  memory/         bộ nhớ phiên trong RAM
  migrations/     migration SQL theo cặp và runner
  model_registry/ hồ sơ, giai đoạn, runtime, adapter, chẩn đoán, kho khóa
  storage/        tìm kiếm, tìm toàn diện, embedding, trích dẫn, độ liên quan
  synthesis/      focus, kiểm tra, nhãn, dịch vụ
  vietnamese_nlp/ chuẩn hóa Unicode, parser trích dẫn pháp lý
  workflow/       pipeline cố định, câu trả lời chat, chọn AI
backend/tests/    bộ pytest
frontend/src/     pages/, components/ (+ components/ai/), api/, desktop/, theme/
src-tauri/        vỏ Tauri 2 cho Windows USER
deploy/           ghi chú windows/, nguồn gói portable/ và lan-portable/ (LAN offline)
scripts/          verify, start-local-stack, đóng gói, nhập, embedding, benchmark, xuất OpenAPI
evaluation/       corpus công khai, bộ đo tìm kiếm, bao phủ và rerank (ca hư cấu)
configs/          chỉ cấu hình mẫu (không bí mật)
tools/            kiểm egress, kiểm hash nguồn, footprint
docs/             SRS, hồ sơ bàn giao, ADR, runbook, báo cáo bằng chứng, OpenAPI
docs/en, docs/vi  bản tiếng Anh và tiếng Việt của các tài liệu chính
.kiro/            quyền, specs, steering, hooks của Kiro
.stitch/          ghi chú thiết kế giao diện từ Stitch
```

## Quy ước

- Tính năng backend mới: route trong `api/v1/`, logic trong gói miền tương ứng, SQL trong migration theo cặp mới, test trong `backend/tests/`.
- Giao diện quản trị mới: trang trong `frontend/src/pages/`, thành phần trong `components/`, gọi API trong `api/client.ts`, kiểu trong `types.ts`.
- Tài liệu: tệp gốc giữ nguyên ngôn ngữ. Bản đối ứng đặt bên cạnh: `README.en.md`, `*.vi.md` / `*.en.md`, hoặc trong `docs/en/` và `docs/vi/`. Không ghi đè ngôn ngữ này bằng ngôn ngữ kia.
- Tệp Kiro đọc trong `.kiro/specs` và `.kiro/steering` giữ tiếng Anh; bản dịch tiếng Việt ở `docs/vi/kiro/`.
- Dữ liệu sinh ra hoặc runtime không đưa vào Git (`data/`, `backups/`, `.agents/`, tệp nhị phân lớn; xem `.gitignore`).
- Không sửa `.kiro/settings/permissions.yaml` nếu chủ dự án không yêu cầu.
