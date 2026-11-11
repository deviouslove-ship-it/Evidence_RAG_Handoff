# Spec: Hiệu lực văn bản và điều khoản, bản dịch

**Ngôn ngữ / Language:** Tiếng Việt · bản chuẩn: [`.kiro/specs/effectivity/`](../../../../.kiro/specs/effectivity/)

> Spec dựng lại từ mã nguồn đã triển khai ngày 09/11/2026, cập nhật 11/11/2026 (`Spec reconstructed from the implemented code on 2026-11-09`). Không phải spec lịch sử do Kiro tạo. Nguồn quy tắc: ADR-008 và `docs/thiet-ke-tra-cuu-hieu-luc.md`.

## Giới thiệu
Hiệu lực được mô hình hóa hai trục: tình trạng pháp lý (trục A) và trạng thái xác minh (trục B: `verified`, `unverified`, `not_found`). Đề xuất của máy không bao giờ được hiển thị là kết luận đã xác minh.

## Yêu cầu (EARS)

**Y1. Hai trục.**
1. THE SYSTEM SHALL lưu tình trạng pháp lý theo văn bản và theo Điều/Khoản/Điểm, và trạng thái xác minh trong `document_effective_intervals`, `node_effective_intervals` (migration `0011_effectivity.sql`).
2. WHEN tính trạng thái THE SYSTEM SHALL đánh giá tại `as_of_date` trên các khoảng của snapshot.
3. WHEN ngày tra cứu sau ngày dữ liệu của kho THE SYSTEM SHALL giới hạn xác minh tối đa "chưa xác minh".

**Y2. "Còn hiệu lực + Đã xác minh" chỉ từ xác nhận của người.**
1. THE SYSTEM SHALL chỉ sinh "còn hiệu lực + đã xác minh" từ `effectivity_attestations`, và lớp truy vấn SHALL hạ xuống nếu nguồn khác khẳng định (`resolver.py::cap_verification`).
2. IF không có quan hệ chấm dứt THEN THE SYSTEM SHALL hiển thị "chưa xác định" kèm "không tìm thấy thông tin trong kho" và ngày có hiệu lực nếu biết.
3. IF đề xuất chưa duyệt THEN THE SYSTEM SHALL KHÔNG đổi trục A và SHALL thêm ghi chú có đề xuất chưa xác nhận.
4. IF quan hệ có điều kiện hoặc chuyển tiếp THEN THE SYSTEM SHALL hiển thị "chưa xác định" kèm điều kiện.
5. WHEN quan hệ đã duyệt mới chạm đích sau ngày xác nhận THE SYSTEM SHALL chuyển bản xác nhận sang `needs_reverify` (trigger `effectivity_mark_reverify`).
6. THE SYSTEM SHALL chỉ khẳng định "còn hiệu lực" đến ngày xác nhận (`ATTESTATION_FUTURE_DATE`).

**Y3. Đề xuất bằng quy tắc.**
1. WHEN văn bản được duyệt THE SYSTEM SHALL đọc ngày ban hành, cơ quan, ngày hiệu lực, quan hệ thay thế/bãi bỏ/sửa đổi/ngưng và hợp nhất bằng quy tắc (`effectivity/extract.py`), đọc ngày hiệu lực riêng của từng mục (`item_valid_from`) khi mục có ghi, tách câu có nhiều đơn vị đích thành một đề xuất cho mỗi đích, và tạo đề xuất `replace` phạm vi `node` có đích rỗng (`target_path=None`) khi câu chỉ ghi "thay thế một phần / một số điều" mà không nêu Điều cụ thể.
2. WHEN câu có từ khóa quan hệ mà quy tắc không đọc được THE SYSTEM SHALL đếm là ứng viên cho giai đoạn AI `relation`, chỉ để đề xuất.
3. IF đọc quan hệ lỗi THEN THE SYSTEM SHALL vẫn cho duyệt nguồn và ghi `EFFECTIVITY_PROCESSING_FAILED` vào kiểm toán.
4. WHEN khớp số hiệu đích THE SYSTEM SHALL chuẩn hóa số hiệu, rồi loại, rồi ngày ban hành; nhiều ứng viên → `ambiguous`, không có → `unresolved` (`effectivity/store.py::match_target`).

**Y4. Rà soát và quyền.**
1. WHEN duyệt đề xuất THE SYSTEM SHALL yêu cầu REVIEWER có `can_review` trên danh mục của văn bản nguồn hoặc đích mới.
2. THE SYSTEM SHALL KHÔNG cho người đề xuất tự duyệt, và SYS_ADMIN SHALL KHÔNG duyệt.
3. WHEN reviewer sửa hành động, ngày hoặc đích THE SYSTEM SHALL lưu bản mới và giữ đề xuất làm lịch sử.
4. IF đề xuất phạm vi `node` chưa gắn `target_node_id` THEN THE SYSTEM SHALL từ chối phê duyệt với `RELATION_TARGET_REQUIRED` (`effectivity/service.py::_approve`).

**Y5. Hiệu lực cấp điều khoản.**
1. THE SYSTEM SHALL ghi ngoại lệ cấp nút (`replace`, `suspend`, `modify`, `repeal_partial`) cho nút và cây con (`effectivity/store.py`, `resolver.py`); trạng thái chấm dứt cấp văn bản thắng ngoại lệ cấp nút.
2. WHEN quan hệ cấp nút `replace`, `repeal_partial` hoặc `suspend` được duyệt THE SYSTEM SHALL đánh dấu nút đích đã hết hiệu lực (`replaced`/`repealed`/`suspended`, `verified`, ẩn khỏi tìm kiếm mặc định); WHEN quan hệ cấp nút `modify` được duyệt THE SYSTEM SHALL đánh dấu nút đích `modified` (`unverified`).
3. THE SYSTEM SHALL tính `clause_level_reviewed` và chỉ hiện cảnh báo chung khi kết quả còn văn bản chưa đạt mức đó.

**Y6. Snapshot.**
1. WHEN nguồn, quan hệ hoặc xác nhận được duyệt/thu hồi THE SYSTEM SHALL xuất bản snapshot nguyên tử (`POST /api/v1/admin/effectivity/snapshots/publish`), giữ 3 bản gần nhất, đặt `data_date` là ngày xuất bản.
2. IF snapshot cũ hoặc đồ thị không xác định THEN THE SYSTEM SHALL trả "temporal unknown" và chặn kết luận pháp lý (`docs/amendments-and-effective-snapshots.md`).

## Thiết kế (tóm tắt)

| Mối quan tâm | Tệp |
|---|---|
| Bộ đọc quy tắc | `effectivity/extract.py` |
| Quy tắc cứng, tính trạng thái | `effectivity/resolver.py`, test `backend/tests/test_effectivity_rules.py`, `backend/tests/test_effectivity_node_scope_pg.py` |
| Lưu trữ, khớp đích | `effectivity/store.py`, `service.py` |
| Đường dẫn khoản | `effectivity/node_paths.py`, `documents/node_effectivity.py` |
| Đề xuất AI (chỉ đề xuất) | `effectivity/ai.py` |
| API | `api/v1/effectivity.py` |
| Giao diện | `EffectivityReviewPanel.tsx`, `EffectivityBadges.tsx`, `effectivityLabels.ts` |
| Đo lường | `evaluation/coverage/measure_g3_relations.py`, `g3_relations_reference.json` |

Luồng: văn bản đã duyệt → quy tắc `extract.py` → đề xuất `node_amendments` → reviewer duyệt → quan hệ đã duyệt → snapshot; xác nhận của người cũng vào snapshot; thay đổi quan hệ về sau kích hoạt `needs_reverify`.

Quyết định (ADR-008): quan hệ chấm dứt đã duyệt cho trục B "đã xác minh"; sửa đổi một phần cho trục A "sửa đổi một phần" và trục B "chưa xác minh". Quy tắc cứng nằm trong mã và trigger; AI chỉ đề xuất. API chỉ cộng thêm trường (`effectivity`, `clause_level_warning`, `data_date`), không đổi `amendment_state`.

Giới hạn: trên kho thử 286 văn bản có 671 đề xuất quan hệ và 293 quan hệ liên quan, phần lớn đích "chưa có trong kho". 31/31 quan hệ cấp khoản khớp bộ đối chiếu do tác nhân soạn, chưa được chuyên gia xác nhận (`docs/implementation-status.md`).

## Tasks
- [x] 1. Migration `0011_effectivity` có tệp down
- [x] 2. Bộ đọc quy tắc
- [x] 3. Resolver với quy tắc cứng và test
- [x] 4. Khớp đích
- [x] 5. API duyệt, xác nhận, thu hồi, snapshot
- [x] 6. Quan hệ cấp khoản (`node_paths.py`, `documents/node_effectivity.py`, `test_effectivity_node_scope_pg.py`)
- [x] 7. Đề xuất quan hệ bằng AI, chỉ đề xuất
- [x] 8. Giao diện duyệt và huy hiệu
- [x] 9. Script trích xuất (`scripts/extract_effectivity.py`)
- [ ] 10. Chuyên gia xác nhận bộ đối chiếu quan hệ (chưa có)
- [ ] 11. Bộ chọn nút đích trên giao diện cho đích chưa ghép (chưa có; xem hướng dẫn)
