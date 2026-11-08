# ADR-008 — Hiệu lực hai trục, quan hệ đề xuất, bản xác nhận và snapshot (G1, G3)

- Ngày: 07/11/2026
- Trạng thái: Đã triển khai
- Căn cứ: thiết kế chốt `docs/thiet-ke-tra-cuu-hieu-luc.md` mục 3, 4, 5, 9; quyết định D1, D2, D7,
  D9, D10, D12, D14; điểm nhất quán 1, 7, 8, 11.

## 1. Quyết định

1. **Hai trục.** Trục A dùng enum `effective_status` sẵn có cho cấp Điều/Khoản/Điểm và cột chữ
   (cùng tập giá trị, thêm `replaced` = "Bị thay thế") cho cấp văn bản; trục B là cột
   `verification_state` (`verified`, `unverified`, `not_found`) trên `document_effective_intervals`
   (mới) và `node_effective_intervals`. API chỉ **cộng thêm** trường `effectivity` (không đổi
   `amendment_state`), cộng `clause_level_warning`, `data_date` cho tìm kiếm.
2. **Một bảng quan hệ.** `node_amendments` mở rộng (migration `0011`): phạm vi văn bản/nút, đích
   văn bản, đích chưa có trong kho (số hiệu, loại, ngày, đường dẫn Điều/Khoản/Điểm), điều kiện,
   nguồn đề xuất (quy tắc, AI, người), độ tin cậy, phiên bản bộ đọc/model, mã lô duyệt,
   `superseded_by`. `node_references.reference_kind` cho căn cứ, hướng dẫn, hợp nhất, dẫn chiếu.
   Lịch sử = nhật ký kiểm toán chuỗi băm + `superseded_by`; không có bảng sự kiện riêng.
3. **Quy tắc cứng nằm trong mã** (`backend/app/effectivity/resolver.py`, trigger
   `effectivity_mark_reverify`), có test `backend/tests/test_effectivity_rules.py`:
   1. "Còn hiệu lực + Đã xác minh" chỉ sinh từ `effectivity_attestations`; lớp truy vấn hạ lại nếu
      nguồn khác (`cap_verification`).
   2. Không có quan hệ chấm dứt → "Chưa xác định" + "Không tìm thấy thông tin trong kho", kèm "Có
      hiệu lực từ D1".
   3. Đề xuất chưa duyệt không đổi trục A, chỉ thêm ghi chú "có đề xuất chưa xác nhận".
   4. Quan hệ có điều kiện/chuyển tiếp → "Chưa xác định" + điều kiện.
   5. Quan hệ mới chạm đích sau thời điểm xác minh → trigger chuyển bản xác nhận sang
      `needs_reverify`; bản đó không còn xác minh gì.
4. **Diễn giải đã chọn** (thiết kế không nói rõ): quan hệ chấm dứt đã duyệt (bãi bỏ, thay thế,
   ngưng) cho trục B "Đã xác minh" vì có người duyệt, thời điểm, câu nguồn (D1); sửa đổi một phần đã
   duyệt cho trục A "Sửa đổi một phần", trục B "Chưa xác minh" (biết bị sửa, chưa biết còn hiệu lực).
   "X hết hiệu lực kể từ ngày [văn bản này] có hiệu lực" trong điều khoản thi hành được đề xuất là
   "thay thế"; "bãi bỏ" là "bãi bỏ". Người duyệt sửa được hành động, ngày, đích khi duyệt (lưu bản
   mới, bản đề xuất giữ làm lịch sử).
5. **Thời điểm (D14).** Mọi trạng thái tính theo `as_of_date` trên các khoảng của snapshot; bản xác
   nhận "còn hiệu lực" chỉ được khẳng định đến ngày xác minh (`ATTESTATION_FUTURE_DATE`); ngày tra
   cứu sau ngày dữ liệu của kho thì trục B tối đa "Chưa xác minh".
6. **Đọc bằng quy tắc** (`effectivity/extract.py`): ngày ban hành, cơ quan ở phần đầu; ngày hiệu lực
   ("X này có hiệu lực ... từ ngày", "kể từ ngày ký"); thay thế, bãi bỏ (toàn bộ/một phần, kể cả danh
   sách "sau đây:"), sửa đổi, ngưng; danh mục hết hiệu lực (dòng bảng, độ tin cậy 0,5, người duyệt
   điền ngày); phần đầu Văn bản hợp nhất → quan hệ `consolidation`. Câu có từ khóa quan hệ mà quy tắc
   không đọc được được đếm là ứng viên cho giai đoạn AI `relation` (chỉ đề xuất).
7. **Khớp số hiệu** (`store.match_target`): số hiệu chuẩn hóa (+ dạng bỏ hậu tố "(A11)") → loại →
   ngày ban hành → văn bản chính (có ngày hiệu lực) thay vì phụ lục cùng số. Còn nhiều ứng viên →
   `ambiguous` (người chọn). Không có → `unresolved`; duyệt văn bản mới tự khớp lại.
8. **Quyền (D10).** `category_acl.can_review`; chỉ `REVIEWER` có `can_review` trên danh mục của văn
   bản nguồn hoặc đích mới thấy và duyệt; người đề xuất không tự duyệt; SYS_ADMIN không duyệt.
9. **Snapshot.** Xuất bản tự động sau mỗi lần duyệt nguồn, duyệt quan hệ, xác nhận/thu hồi; giữ 3 bản
   gần nhất; `data_date` = ngày xuất bản (≥ ngày duyệt văn bản mới nhất).
10. **Cấp Điều/Khoản/Điểm (G3).** Ngoại lệ cấp nút ghi cho nút và cây con; trạng thái chấm dứt của văn
    bản thắng ngoại lệ. Mức rà soát cấp điều khoản được **tính** (`clause_level_reviewed`): mọi quan
    hệ nhắm vào văn bản đã duyệt và mọi sửa đổi một phần có ít nhất một quan hệ cấp nút đã duyệt.
    Thanh cảnh báo chung chỉ hiện khi còn văn bản trong kết quả chưa đạt mức đó.

## 2. Hệ quả

- Duyệt nguồn không bị chặn khi đọc quan hệ lỗi (ghi `EFFECTIVITY_PROCESSING_FAILED` vào kiểm toán).
- Dữ liệu thử 286 văn bản: 671 đề xuất quan hệ, 293 quan hệ liên quan; phần lớn đích "chưa có trong
  kho" vì kho thử chỉ là một phần văn bản của Bộ.
- Hạ migration `0011` xóa các quan hệ không biểu diễn được ở lược đồ cũ (không ngày, `repeal_partial`,
  `commence`).
