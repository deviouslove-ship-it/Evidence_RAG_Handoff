# ADR-001 — Runtime Windows và PostgreSQL duy nhất

**Trạng thái:** Đề xuất kỹ thuật, chưa được kiểm chứng trên máy đích.

## Quyết định

- PostgreSQL là cơ sở dữ liệu duy nhất; migration dùng `pgcrypto` và `pgvector`.
- Python dùng FastAPI/asyncpg; công cụ và runtime dự án quản lý resolve từ deployment profile `installation.programs_root` hoặc `EVIDENCE_PROGRAMS_ROOT`.
- Không fallback sang executable trong PATH global, `Program Files`, `AppData`, `Downloads` hoặc ổ khác.
- Dữ liệu PostgreSQL, PDF gốc, log và backup có đường dẫn cấu hình riêng; agent không tự di chuyển.
- Local Mode chỉ cho phép endpoint loopback/LAN nằm trong allowlist; không có cơ chế tự chuyển sang API.

## Hệ quả

1. `DATABASE_URL` bắt buộc ngoài POC in-memory.
2. `verify-egress` phải được chạy trên Windows đích sau khi firewall được cấu hình; ứng dụng tự kiểm không thay thế việc ngắt Internet thật.
3. Nếu pgvector không có bản Windows được duyệt, phải ghi phương án build/cài cụ thể trong ADR tiếp theo; không đổi sang database khác.
4. Acceptance cần clean install, service restart, backup mã hóa và restore ra máy sạch.

## Việc còn chưa chứng minh

Chưa có bằng chứng cài PostgreSQL/pgvector, đăng ký service, exact-vector benchmark, backup/restore hoặc ngắt Internet thật trên máy đích.
