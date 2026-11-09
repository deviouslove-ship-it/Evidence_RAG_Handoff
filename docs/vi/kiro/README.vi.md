# Bản dịch tiếng Việt của `.kiro/specs` và `.kiro/steering`

**Ngôn ngữ / Language:** Tiếng Việt · bản gốc tiếng Anh nằm trong [`.kiro/`](../../../.kiro/)

Kiro đọc trực tiếp các tệp tiếng Anh trong `.kiro/specs/` và `.kiro/steering/`. Các tệp ở thư mục này chỉ là **bản dịch để người đọc tiếng Việt tham khảo**; không thay thế tệp chuẩn và Kiro không đọc chúng. Nếu hai bản khác nhau, bản tiếng Anh là chuẩn.

**Lưu ý trung thực.** Tất cả spec và steering được **dựng lại từ mã nguồn đã triển khai ngày 09/11/2026**. Chúng không phải spec lịch sử do Kiro tạo ra trong thời gian phát triển (không có phiên Kiro nào dùng chế độ spec). Dấu `[x]` trong tasks nghĩa là hạng mục tồn tại trong repository, không phải bằng chứng đã chạy lại kiểm thử. Xem [`KIRO_WORK_SUMMARY.vi.md`](../../../KIRO_WORK_SUMMARY.vi.md).

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
- `backend-python-lint.json`: sau khi lưu tệp Python trong `backend/`, chạy `ruff check backend` (dùng `ruff` trong PATH hoặc trong `EVIDENCE_PROGRAMS_ROOT`; bỏ qua kèm thông báo nếu không có).
- `frontend-typescript-check.json`: sau khi lưu tệp `.ts`/`.tsx` trong `frontend/src/`, chạy `tsc --noEmit` (bỏ qua nếu chưa cài phụ thuộc).

Cả hai luôn thoát với mã 0 (chỉ thông báo, không chặn thao tác). Lệnh của hook đã được chạy thử trực tiếp (backend: "All checks passed!"). Việc IDE tự kích hoạt hook chỉ có hiệu lực từ phiên Kiro kế tiếp và chưa được quan sát.
