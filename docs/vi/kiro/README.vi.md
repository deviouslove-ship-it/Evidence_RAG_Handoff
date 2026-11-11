# Bản dịch tiếng Việt của `.kiro/specs` và `.kiro/steering`

**Ngôn ngữ / Language:** Tiếng Việt · bản gốc tiếng Anh nằm trong [`.kiro/`](../../../.kiro/)

Kiro đọc trực tiếp các tệp tiếng Anh trong `.kiro/specs/` và `.kiro/steering/`. Các tệp ở thư mục này chỉ là **bản dịch để người đọc tiếng Việt tham khảo**; không thay thế tệp chuẩn và Kiro không đọc chúng. Nếu hai bản khác nhau, bản tiếng Anh là chuẩn.

**Lưu ý trung thực.** Spec và steering được **dựng lại ban đầu từ mã nguồn đã triển khai ngày 09/11/2026**; spec hiệu lực và ghim trích dẫn được cập nhật ngày 11/11/2026. Chúng không phải spec lịch sử do Kiro tạo ra trong thời gian phát triển (không có phiên Kiro nào dùng chế độ spec). Dấu `[x]` trong tasks nghĩa là hạng mục tồn tại trong repository, không phải bằng chứng đã chạy lại kiểm thử. Xem [`KIRO_WORK_SUMMARY.vi.md`](../../../KIRO_WORK_SUMMARY.vi.md).

## Steering
- [product.vi.md](steering/product.vi.md)
- [tech.vi.md](steering/tech.vi.md)
- [structure.vi.md](steering/structure.vi.md)

## Specs (mỗi spec gộp requirements, design, tasks)
| Spec | Bản dịch | Tệp chuẩn |
|---|---|---|
| Quản lý văn bản | [document-management.vi.md](specs/document-management.vi.md) | [`.kiro/specs/document-management/`](../../../.kiro/specs/document-management/) |
| Tìm kiếm và hỏi đáp | [search.vi.md](specs/search.vi.md) | [`.kiro/specs/search/`](../../../.kiro/specs/search/) |
| Hiệu lực | [effectivity.vi.md](specs/effectivity.vi.md) | [`.kiro/specs/effectivity/`](../../../.kiro/specs/effectivity/) |
| Ghim trích dẫn | [citation-pinning.vi.md](specs/citation-pinning.vi.md) | [`.kiro/specs/citation-pinning/`](../../../.kiro/specs/citation-pinning/) |
| Nhật ký kiểm toán | [audit-log.vi.md](specs/audit-log.vi.md) | [`.kiro/specs/audit-log/`](../../../.kiro/specs/audit-log/) |
| OCR | [ocr.vi.md](specs/ocr.vi.md) | [`.kiro/specs/ocr/`](../../../.kiro/specs/ocr/) |
| Embedding | [embedding.vi.md](specs/embedding.vi.md) | [`.kiro/specs/embedding/`](../../../.kiro/specs/embedding/) |
| Model Registry | [model-registry.vi.md](specs/model-registry.vi.md) | [`.kiro/specs/model-registry/`](../../../.kiro/specs/model-registry/) |
| Diễn giải AI và tổng hợp | [ai-synthesis.vi.md](specs/ai-synthesis.vi.md) | [`.kiro/specs/ai-synthesis/`](../../../.kiro/specs/ai-synthesis/) |
| Windows LAN Portable | [windows-lan-portable.vi.md](specs/windows-lan-portable.vi.md) | [`.kiro/specs/windows-lan-portable/`](../../../.kiro/specs/windows-lan-portable/) |

## Hooks
Hai hook nằm ở [`.kiro/hooks/`](../../../.kiro/hooks/):
- `backend-python-lint.json`: sau khi lưu tệp `.py` trong `backend/`, chạy `ruff check <tệp>`; nếu tệp nằm trong `backend/app` thì chạy thêm `mypy` (strict, `backend/pyproject.toml`).
- `frontend-typescript-check.json`: sau khi lưu tệp `.ts`/`.tsx` trong `frontend/src/`, chạy `eslint <tệp> --max-warnings=0` rồi `tsc --noEmit` (tsc kiểm tra cả dự án frontend vì không kiểm tra riêng được một tệp trong project).

Cả hai gọi [`scripts/kiro-hook-check.ps1`](../../../scripts/kiro-hook-check.ps1). Công cụ lấy từ `EVIDENCE_PROGRAMS_ROOT` qua `configs/development-toolchain.json` (cùng nguồn với `scripts/verify.ps1`) và `frontend/node_modules`; không dùng PATH. Kết quả là PASS (mã 0), FAIL (mã 1) hoặc SKIPPED kèm lý do (mã 3, ví dụ thiếu công cụ). Mỗi lần chạy được ghi vào `.agents/hook-logs/kiro-hooks.log` (không đưa lên Git), vì Kiro không hiển thị đầu ra của `PostFileSave` trong khung chat.

Kiro phát `PostFileSave` cả khi lưu trong editor lẫn khi agent ghi tệp (`fs_write`, `str_replace`, `fs_append`), nên không dùng thêm hook `PostToolUse` để tránh chạy trùng. Đã quan sát hook tự kích hoạt ngày 09/11/2026 khi agent ghi tệp thử có lỗi cố ý (FAIL), rồi sửa lại (PASS). Lưu tệp bằng tay trong editor chưa được thử.
