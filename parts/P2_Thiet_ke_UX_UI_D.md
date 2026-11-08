---

## D. Thiết kế UX/UI chi tiết

Hướng thiết kế đã chốt: **Modern Enterprise / Evidence-First**, Light Theme mặc định, Navy + Blue + White + Slate. Đây là bảng màu của ứng dụng; không lấy bảng màu ChatGPT, demo DIL hay màu framework làm chuẩn. Dark Mode là P1.

### D.1 Nguyên tắc UX

1. **Căn cứ trước, lời giải thích sau.** Thứ người dùng thấy đầu tiên là nguyên văn nguồn và trang PDF; lời giải thích là lớp thứ hai.
2. **Nói rõ mình biết gì và chưa biết gì.** Mọi kết quả có phạm vi (danh mục, ngày áp dụng, ngày kho dữ liệu), nhãn trạng thái và checklist độ phủ. Không dùng phần trăm tự đánh giá, không dùng màu trang trí để tạo niềm tin.
3. **Màu không là tín hiệu duy nhất.** Mọi trạng thái có icon + nhãn chữ + mô tả theo ngày áp dụng.
4. **Người dùng giữ quyền sửa.** Dữ kiện AI suy ra luôn sửa được; câu hỏi nối tiếp hiện "Đang hiểu là…" để chỉnh; không hành động ngầm.
5. **Không làm mất bối cảnh.** Mở PDF, mở văn bản sửa đổi, mở trang đầy đủ đều giữ nguyên hội thoại và kết quả.
6. **Yên tĩnh, đọc được.** Một điểm nhấn là thẻ căn cứ nguyên văn; mọi thứ xung quanh trung tính. Không hiệu ứng nền, không gradient, không bóng đổ nặng. Chuyển động chỉ đáp lại thao tác của người dùng.
7. **Cùng một ngôn ngữ giao diện cho widget và trang đầy đủ.** Chung component, chung hợp đồng SSE, chung nhãn.
8. **Văn bản giao diện bằng tiếng Việt thuần, câu chủ động, viết thường đầu câu (sentence case)**, nút nêu đúng hành động ("Tra cứu", "Lưu nháp", "Duyệt"), cùng một hành động giữ cùng một tên xuyên suốt.

### D.2 Design system

**D.2.1 Màu — token chính thức (SRS §9.5)**

| Token CSS | HEX | Ứng dụng |
|---|---|---|
| `--color-brand-navy` | `#163A5F` | Sidebar, topbar, tiêu đề vùng quản trị, header panel Chat Agent, launcher |
| `--color-brand-navy-hover` | `#102B47` | Hover thanh Navy, launcher hover |
| `--color-action` | `#2563EB` | Nút tra cứu chính, link citation `[1]`, tab active, focus ring |
| `--color-action-hover` | `#1D4ED8` | Hover CTA |
| `--color-background` | `#F8FAFC` | Nền toàn app |
| `--color-surface` | `#FFFFFF` | Chat, Evidence Cards, PDF Viewer, modal |
| `--color-surface-muted` | `#F1F5F9` | Thẻ thông tin phụ, skeleton, tin nhắn người dùng |
| `--color-text-primary` | `#0F172A` | Nội dung chính và trích dẫn |
| `--color-text-secondary` | `#475569` | Metadata có ý nghĩa, breadcrumb |
| `--color-border` | `#CBD5E1` | Viền input, card, separator |
| `--color-evidence-bg` | `#EFF6FF` | Căn cứ được chọn/đang hiển thị trong viewer |
| `--color-evidence-text` | `#1E40AF` | Nhãn trích dẫn/evidence |
| `--color-success` | `#047857` | Kiểm chứng đạt, nguồn được phép dùng; luôn có icon/text |
| `--color-warning` | `#92400E` | Điều kiện chưa chắc, hiệu lực chưa đầy đủ |
| `--color-warning-bg` | `#FFFBEB` | Sticky Amendment Banner và temporal warning |
| `--color-danger` | `#B91C1C` | Lỗi, bãi bỏ, quyền bị chặn, citation không hợp lệ |
| `--color-danger-bg` | `#FEF2F2` | Vùng cảnh báo nghiêm trọng |

**Token bổ sung (đề xuất, phải qua contrast test; không đạt thì chỉnh token):**

| Token | Giá trị gợi ý | Dùng cho |
|---|---|---|
| `--color-success-bg` | `#ECFDF5` | Nền nhãn "Đã xác định căn cứ" |
| `--color-highlight-fill` | `rgba(37, 99, 235, 0.22)` | Tô span trích dẫn trên PDF (chỉ đúng vùng span, `mix-blend-mode: multiply`) |
| `--color-highlight-stroke` | `#2563EB` | Viền 2px quanh span đang chọn |
| `--color-dirty-bg` / `--color-dirty-border` | `#FFF7ED` / `#C2410C` | Chip đã chỉnh sửa, dải "Đã chỉnh sửa dữ kiện" (neutral/orange nhẹ) |
| `--color-overlay` | `rgba(15, 23, 42, 0.45)` | Nền modal |
| `--color-focus-ring` | `var(--color-action)` | Vòng focus 3px, offset 2px |

**Quy tắc dùng màu**

1. Topbar/Sidebar Navy; vùng đọc văn bản và Evidence Card nền trắng; toàn trang xám rất nhạt. Blue chỉ cho tương tác (link citation, nút "Tra cứu", focus), **không** dùng xanh để tuyên bố căn cứ đúng về pháp lý.
2. Trạng thái dirty dùng neutral/cam nhẹ; kết quả `stale` có nhãn chữ; skeleton trung tính, **không dùng xanh success trước khi claim được kiểm tra**.
3. Nền PDF trắng hoặc theo render gốc; không phủ màu lên nội dung PDF; highlight chỉ trên span được trích.
4. Tất cả màu đi qua CSS variables trong **một theme module**; cấm hardcode HEX trong component (lint rule). Mọi cặp màu/trạng thái có contrast test tự động (WCAG 2.2 AA: 4.5:1 chữ thường, 3:1 chữ lớn và thành phần giao diện).

**D.2.2 Chữ**

Họ chữ ưu tiên `Inter, system-ui, Arial, sans-serif`; fallback tương thích tiếng Việt có dấu. Local Mode không tải font ngoài: chỉ đóng gói Inter cục bộ sau khi kiểm license, nếu không dùng font hệ thống.

| Vai trò | Cỡ / line-height | Độ đậm | Ghi chú |
|---|---|---|---|
| Tiêu đề trang (h1) | 24 / 32 | 600 | Một cho mỗi màn hình |
| Tiêu đề khu vực (h2) | 20 / 28 | 600 | |
| Tiêu đề thẻ (h3) | 18 / 28 | 600 | |
| Nội dung giao diện | 14 / 20 | 400, nhãn 500 | Nút, bảng, chip |
| Nội dung đọc | 15 / 24 | 400 | Câu trả lời, giải thích |
| Trích dẫn nguyên văn và nội dung văn bản dài | 16 / 26 | 400 | line-height tối thiểu 1.5; dòng không quá khoảng 80 ký tự khi bố cục cho phép |
| Metadata có ý nghĩa | 13 / 18 | 400, `--color-text-secondary` | Số hiệu, ngày, breadcrumb; không dưới 13px |

**D.2.3 Khoảng cách, bo góc, độ nổi, lớp**

- Khoảng cách theo bước 4px: 4, 8, 12, 16, 24, 32, 48. Khoảng trong thẻ 16; giữa các khối trong câu trả lời 12–16; giữa các vùng 24.
- Bo góc: 6px (input, nút), 8px (thẻ căn cứ, bảng), 12px (panel Chat Agent, drawer, modal), tròn đầy (chip, launcher, huy hiệu). Không dùng một bán kính cho mọi thứ.
- Độ nổi: thẻ dùng viền 1px `--color-border`, không đổ bóng; chỉ panel nổi (`0 8px 24px rgba(15,23,42,0.16)`) và modal (`0 16px 40px rgba(15,23,42,0.24)`) có bóng.
- Lớp (z-index): nội dung 0 · header dính 10 · viewer drawer 30 · launcher và panel Chat Agent 40 · modal xác nhận 50 · toast 60. Modal xác nhận luôn nằm trên Chat Agent.

**D.2.4 Biểu tượng và chuyển động**

- Bộ icon đóng gói cục bộ (đề xuất `lucide`, giấy phép ISC; ghi vào manifest). Không dùng icon từ CDN.
- Chuyển động chỉ đáp lại thao tác: mở/đóng panel (160–200ms, trượt + mờ nhẹ), mở accordion, xác nhận. Không có animation tự chạy ngoài skeleton và chỉ báo "đang xử lý". Tôn trọng `prefers-reduced-motion` (tắt trượt, dùng hiện/ẩn tức thời).

### D.3 Kiến trúc thông tin và điều hướng

| Khu vực | Vai trò | Mục điều hướng |
|---|---|---|
| User Portal | USER hoặc quyền `rag.query` được cấp tường minh + scope tài liệu | Trang chủ Orb · Hỏi đáp/workspace · Lịch sử của tôi · Bộ nhớ của tôi · Theo dõi (P1) |
| Kho tài liệu | CURATOR, REVIEWER | Tài liệu · Hàng đợi duyệt · Quan hệ sửa đổi · Đề xuất của AI |
| Quản trị | SYS_ADMIN | Danh mục · Người dùng và quyền · Domain cho phép · Mô hình AI và chế độ · Cấu hình bộ nhớ |
| Chất lượng | CURATOR, REVIEWER, SYS_ADMIN | Bộ kiểm thử (Gold, trap set) · Chạy benchmark · Dashboard |
| Kiểm toán | AUDITOR | Nhật ký · Bằng chứng truy cập |

- **Chat Agent (launcher góc phải) hiện ở mọi trang Tra cứu và Kho tài liệu (chế độ đọc)**; ẩn ở đăng nhập và thu nhỏ ở Curator Split-View.
- Mục điều hướng người dùng không có quyền **không hiển thị** (lọc từ server, không chỉ ẩn bằng giao diện).
- Vùng Tra cứu chỉ có thanh trên (Navy). Vùng quản trị và kho tài liệu thêm thanh bên trái (Navy, thu gọn được).

Route chuẩn: `/login` dùng chung; `/app/*` là User Portal; `/admin/*` là Admin Portal với layout/state/navigation riêng; `/` định tuyến theo quyền hoặc lựa chọn portal của tài khoản nhiều quyền. SYS_ADMIN không được mặc nhiên vào Tra cứu. Chuyển portal không nâng quyền và không chuyển nội dung hội thoại riêng sang màn hình quản trị. Desktop mở User Portal trong shell; route quản trị chỉ mở khi có quyền và thao tác tường minh.

### D.4 Bố cục chung và đáp ứng kích thước

| Điểm ngắt | Bố cục |
|---|---|
| ≥ 1280px | Hỏi đáp: hai vùng — cột trái "Hỏi và căn cứ" (khoảng 5/12) và PDF Viewer (khoảng 7/12); tách kéo được. Split-View: hai nửa bằng nhau |
| 768–1279px | Một cột hỏi/căn cứ; PDF Viewer mở thành drawer phải rộng ~70% màn hình |
| < 768px | Một cột; PDF Viewer và Chat Agent mở toàn màn hình có nút quay lại; thao tác chính đặt ở vùng dễ chạm (≥ 44×44px) |

Panel + viewer chỉ đặt cạnh nhau nếu vùng khả dụng đủ `panel_width + viewer_min_width + gap + safe_areas`; `viewer_min_width=480px` và gap 16px là token cấu hình ban đầu. Không áp “viewer 60% + panel 380px” vô điều kiện ở tablet. Thiếu chỗ: viewer thay vùng nội dung panel hoặc mở toàn khung với “Quay lại hội thoại”; giữ phiên/scroll, không chồng hai vùng tương tác. Bề rộng thực tế và zoom quyết định chuyển layout, không chỉ tên breakpoint.

Thanh trên (topbar) của trang Hỏi đáp: logo/tên hệ thống · **Danh mục ▼** · **Loại tài liệu ▼** · **Ngày áp dụng** (mặc định "Hôm nay" kèm ngày cụ thể) · huy hiệu chế độ chỉ đọc (**API Mode** hoặc **Local Mode · offline**) · menu người dùng. Khi `as_of_date` khác hôm nay, ô ngày chuyển sang kiểu nhấn (viền cam nhẹ + nhãn "Tra cứu theo ngày quá khứ").

### D.5 Màn hình chi tiết

#### S1. Hỏi đáp (trang đầy đủ)

Mục đích: hỏi, thấy căn cứ trước, đọc phân tích, mở nguồn.

```text
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ Evidence RAG  [Danh mục ▼] [Loại tài liệu ▼] [Ngày áp dụng: 21/10/2026 ▼] [Local Mode]  │ Navy
├───────────────────────────────────────────────┬─────────────────────────────────────────┤
│ [Trả lời] [Phân tích] [Liên quan]              │ PDF VIEWER (S2)                          │
│                                               │ Số hiệu · Cơ quan · Version · Hash       │
│ Phạm vi: Danh mục X · Ngày áp dụng 21/10/2026 │ Chương > Điều 5 > Khoản 2                │
│ · Kho dữ liệu cập nhật 20/10/2026             │ ┌──────────────────────────────────────┐ │
│                                               │ │ ⚠ Khoản này đã được sửa đổi bởi …    │ │ sticky
│ ┌ Mô tả tình huống hoặc hỏi về Điều, Khoản… ┐ │ │   từ ngày … — Xem văn bản sửa đổi    │ │
│ └───────────────────────────────  [Tra cứu] ┘ │ └──────────────────────────────────────┘ │
│                                               │   …nội dung PDF…                         │
│ Dữ kiện: [Đối tượng ✎] [Thời điểm ✎]          │   [ĐOẠN ĐƯỢC TÔ SÁNG]                   │
│          [Hồ sơ ✎ chưa xác nhận]              │                                          │
│ ▸ Đã chỉnh sửa dữ kiện — kết quả bên dưới dựa │ ‹ Trang 12/48 ›  Tìm trong văn bản       │
│   trên dữ kiện trước đó [Cập nhật dữ kiện &   │ Bản hiện hành │ Bản tại ngày …           │
│   Tra cứu lại]                                │ Liên kết trang công bố chính thức        │
│                                               │                                          │
│ ● Có điều kiện — cần xác minh thêm hiệu lực   │                                          │
│ CĂN CỨ  [Quy định chính][Điều kiện][Ngoại lệ] │                                          │
│  [1] Điều 5 khoản 2 · số hiệu … · bản 3        │                                          │
│      “…nguyên văn 2–3 dòng…”  [Mở trong PDF]  │                                          │
│  [2] …                                        │                                          │
│ PHÂN TÍCH CÓ DẪN CHỨNG                         │                                          │
│  • Nhận định … [1][2]                          │                                          │
│ THÔNG TIN CÒN THIẾU  [Ngày xảy ra sự việc] …   │                                          │
│ ĐÃ KIỂM TRA  ✔ Nguồn  ✔ Trích dẫn  ⚠ Hiệu lực │                                          │
│ CÂU HỎI TIẾP THEO  (chip) (chip)               │                                          │
│ Sao chép kèm phạm vi · Phản hồi                │                                          │
│ Kết quả hỗ trợ tra cứu và tham mưu, không …    │                                          │
└───────────────────────────────────────────────┴─────────────────────────────────────────┘
```

Thứ tự khối trong tab **Trả lời**: phạm vi → ô hỏi → dữ kiện → dải "đã chỉnh sửa" (nếu có) → nhãn trạng thái → căn cứ gộp theo vai trò → phân tích có dẫn chứng → thông tin còn thiếu → checklist độ phủ → câu hỏi tiếp theo → hành động và lưu ý.

Tab **Phân tích** (A1, A3, A4, A5): bảng "Điều kiện áp dụng" (đã thỏa / chưa xác minh / ngoại lệ / mốc thời gian / hệ quả nêu trong văn bản, mỗi dòng có `[n]`), danh sách điểm cần lưu ý, so sánh phiên bản của Điều đang xem. Tab **Liên quan** (A6, A10): văn bản hướng dẫn, văn bản sửa đổi, tham chiếu đến/từ node đang xem, chuỗi sửa đổi.

Trạng thái:

| Trạng thái | Hiển thị |
|---|---|
| Trống | Ô hỏi và 3 ví dụ cách hỏi (chip): "Hỏi theo Điều/Khoản", "Mô tả một tình huống", "So sánh với quy định cũ". Không dữ liệu giả |
| Chưa chọn danh mục | Ô hỏi bị khóa; ghi chú "Chọn danh mục để bắt đầu"; chip danh mục được tô nhấn |
| Pha 1 đang chạy | Skeleton trung tính (`--color-surface-muted`) + "Đang tìm căn cứ trong danh mục đã chọn…" |
| Pha 1 xong | Thẻ căn cứ hiện; dòng "Đã tìm thấy và kiểm tra nguồn của X căn cứ. Đang phân tích điều kiện áp dụng, hiệu lực, quy định chuyển tiếp và ngoại lệ…" |
| Pha 2 xong | Claims, nhãn trạng thái, checklist đầy đủ |
| Không đủ căn cứ | Nhãn "Thiếu căn cứ" + giải thích + gợi ý hỏi lại + (nếu có) các căn cứ gần nhất đã kiểm tra, ghi rõ "chưa trả lời được câu hỏi" |
| Tiền đề sai (L0) | "Không có [Điều X] trong [văn bản]. Văn bản này có Điều 1 đến Điều N." |
| Sinh giải thích lỗi | Giữ căn cứ hợp lệ + "Giải thích tạm thời không khả dụng. Các căn cứ bên dưới đã được kiểm tra nguồn." |
| Snapshot hiệu lực stale | Dải cảnh báo: "Dữ liệu hiệu lực đang được cập nhật. Chưa thể khẳng định hiệu lực tại ngày này." |
| Kết quả cũ (`stale`) | Nhãn "Kết quả dựa trên dữ kiện trước đó" cho tới khi có kết quả mới |
| Lỗi mạng/máy chủ | Thông báo nêu việc gì thất bại và nút "Thử lại"; không xóa nội dung đã nhập |

#### S2. PDF Viewer

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ ‹ Quay lại   Tên văn bản · Số hiệu · Cơ quan · Bản 3 ▼ · Hash 9f3a…   ⤓ ↗  │ toolbar
│ [Đang áp dụng ✔ tại 21/10/2026]  (nhãn hiệu lực của node đang xem)         │
├────────────────────────────────────────────────────────────────────────────┤
│ ⚠ Khoản này trên PDF gốc đã được sửa đổi bởi [văn bản] từ ngày [ngày]      │ sticky
│   [Xem văn bản sửa đổi] [Xem nội dung áp dụng tại ngày tra cứu]  ▾ thu gọn │
├────────────────┬───────────────────────────────────────────────────────────┤
│ MỤC LỤC        │                                                           │
│ ▸ Chương I     │   …trang PDF gốc…                                         │
│ ▾ Chương II    │   ┌─ Điều 5 ─ …                                          │
│   ▾ Điều 5     │   │ 2. [đoạn được tô sáng] ◂ huy hiệu "Đã sửa đổi"         │
│     Khoản 1    │   └────────────────────────────────────────────────────── │
│   ● Khoản 2    │                                                           │
├────────────────┴───────────────────────────────────────────────────────────┤
│ ‹ Trang 12 / 48 ›   Tìm trong văn bản [          ]   Bản hiện hành │ Bản tại ngày … │
└────────────────────────────────────────────────────────────────────────────┘
```

- Toolbar luôn hiện nhãn hiệu lực của node đang xem (thu gọn banner không làm mất nhãn này).
- Mục lục dựng từ DB (`document_nodes`); click nhảy PDF; node đang xem có dấu ● và `aria-current`.
- Highlight: nền `--color-highlight-fill`, viền `--color-highlight-stroke`; chỉ vùng span được trích. Cuộn tự động tới span.
- **Fallback khi bbox không tin cậy:** mở đúng trang, hiện ngăn "Đoạn trích để đối chiếu" bên cạnh, kèm dòng "Chưa tô sáng chính xác vị trí đoạn này trên trang."
- Bản tại ngày: chọn version; PDF cũ vẫn xem nguyên, kèm banner.
- Nút tải PDF chỉ hiện khi có quyền. Link "Trang công bố chính thức" chỉ hiện khi curator đã xác minh.
- Điện thoại: toàn màn hình; mục lục thành ngăn kéo; toolbar rút gọn thành tiêu đề + menu.

#### S3. Chat Agent (widget góc phải)

**Launcher.** Nút tròn 56px, nền `--color-brand-navy`, icon hội thoại màu trắng; cách mép phải và mép dưới 24px (16px trên điện thoại) cộng safe-area; hover `--color-brand-navy-hover`; focus: vòng 3px `--color-focus-ring` cách 2px. Tooltip "Hỏi về văn bản". `aria-label="Mở trợ lý tra cứu"`. Huy hiệu tròn 12px viền trắng: xanh action = có phản hồi mới; cam (`--color-warning`) = có kết quả cần kiểm lại. Không tự bật, không tự mở.

**Panel (web/khung desktop).** Rộng mong muốn 420px (≥1280) hoặc 380px (768–1279), luôn clamp trong work area/safe-area; cao tối đa `min(720px, 100vh − 96px)`, bo 12px. Orb vẫn là điều khiển toggle có nhãn đúng trạng thái, click lần nữa thu panel. Shell native theo S14, không tạo thêm ô vuông hoặc cửa sổ nền quanh Orb.

```text
                                   ┌──────────────────────────────────────┐
                                   │ Trợ lý tra cứu        ⤢  ▁  ✕        │ Navy
                                   ├──────────────────────────────────────┤
                                   │ [Danh mục X ▼] [21/10/2026 ▼] [Local]│ thanh phạm vi
                                   │ Đang hiểu là: “…câu đã viết lại…” ✎  │ (khi hỏi nối tiếp)
                                   │ [Trả lời] [Phân tích] [Liên quan]    │
                                   ├──────────────────────────────────────┤
                                   │                    ┌───────────────┐ │
                                   │                    │ câu hỏi của tôi│ │
                                   │                    └───────────────┘ │
                                   │ ● Có điều kiện                       │
                                   │ ┌ [1] Điều 5 khoản 2 · số hiệu … ──┐ │
                                   │ │ “…nguyên văn…”      [Mở trong PDF]│ │
                                   │ └───────────────────────────────────┘ │
                                   │ Nhận định có dẫn chứng … [1]         │
                                   │ Còn thiếu: (Ngày xảy ra sự việc)     │
                                   │ Hỏi tiếp: (…) (…)                    │
                                   │ Sao chép kèm phạm vi · Phản hồi      │
                                   ├──────────────────────────────────────┤
                                   │ ┌ Mô tả tình huống hoặc hỏi Điều… ┐  │
                                   │ └────────────────────── [Tra cứu] ┘  │
                                   │ Hỗ trợ tra cứu, không thay quyết định │
                                   └──────────────────────────────────────┘
                                                                     (◉) launcher
```

Nút ở header: **⤢ Mở trang đầy đủ** (giữ phiên) · **▁ Thu nhỏ** (về launcher, giữ trạng thái) · **✕ Đóng**.

**Hành vi**

- Mở bằng launcher hoặc phím tắt cấu hình được (mặc định không gán phím tắt toàn cục để tránh xung đột; owner có thể bật). `Esc` đóng panel khi focus ở trong; focus trở về launcher.
- Trạng thái phiên giữ ở server; chuyển trang trong ứng dụng không làm mất hội thoại.
- Bấm `[n]` hoặc "Mở trong PDF": đủ chỗ theo D.4 thì viewer cạnh panel; thiếu chỗ ở tablet/cửa sổ hẹp thì chuyển một khung có “Quay lại hội thoại”. Không che citation/composer bằng panel khác; ở native ưu tiên workspace cùng phiên khi cần đọc PDF rộng.
- Tin nhắn người dùng: căn phải, nền `--color-surface-muted`. Câu trả lời của trợ lý: khối trắng có viền, **không dùng bong bóng chat**; các khối bên trong theo đúng thứ tự ở S1 nhưng thẻ căn cứ ở dạng gọn (số hiệu, Điều/Khoản/Điểm, 2 dòng trích, nút mở).
- Hỏi nối tiếp: hiện dải "Đang hiểu là: …" (có nút sửa); thiếu điều kiện then chốt thì hỏi lại **một** câu bằng chip lựa chọn.
- Kết quả cũ sau khi snapshot đổi: nhãn "Cần kiểm lại" kèm nút "Tra cứu lại với dữ liệu mới"; launcher có huy hiệu cam.
- Không có nút phê duyệt hay thực hiện nghiệp vụ.
- Chế độ không lưu: biểu tượng khóa trong header và dòng "Hội thoại này sẽ không được ghi nhớ."
- Có nút “Dừng” khi đang chạy; dừng chỉ lượt hỏi đáp, không ảnh hưởng tác vụ quản trị. “Thử lại” sau lỗi là run mới có chủ ý; hiển thị kết quả cũ là lượt trước và không nhân đôi lời hỏi.

**Điện thoại:** panel toàn màn hình (bottom sheet cao 100%), header dính, composer dính đáy theo `visualViewport` để bàn phím không che.

**Trạng thái đặc biệt**

| Trạng thái | Hiển thị |
|---|---|
| Lần đầu | Lời chào ngắn + 3 chip ví dụ cách hỏi; không bài giới thiệu dài |
| Chưa chọn danh mục | Thanh phạm vi tô nhấn, composer khóa kèm lý do |
| Mất kết nối | "Mất kết nối tới máy chủ. Nội dung bạn nhập vẫn được giữ." + Thử lại |
| Local Mode, model local lỗi | Căn cứ đã kiểm tra vẫn hiện; "Giải thích tạm thời không khả dụng"; **không** chuyển sang API |
| Không có quyền | "Chưa tìm thấy tài liệu được phép truy cập." (không tiết lộ tài liệu tồn tại) |

#### S4. Danh sách tài liệu và hồ sơ tài liệu (CURATOR/REVIEWER)

```text
┌ Tài liệu ──────────────────────────────────────────────────────────────────┐
│ [Tìm theo số hiệu, tiêu đề]  [Danh mục ▼] [Loại ▼] [Trạng thái ▼]          │
│                                   [Tải PDF lên]  [Nhập từ URL]              │
├────────────────────────────────────────────────────────────────────────────┤
│ Tiêu đề / số hiệu │ Loại │ Cơ quan │ Danh mục │ Phiên bản │ Trạng thái │ ⋯ │
│ …                                                                          │
└────────────────────────────────────────────────────────────────────────────┘
```

- Cột **Trạng thái tài liệu**: Nháp · Chờ duyệt · Đã duyệt · Tạm đình chỉ · Đã thay thế · Hết hiệu lực · Chưa rõ (icon + chữ). Cột **Hiệu lực node** tóm tắt: "Có N node chưa xác minh".
- **Tải PDF lên:** hỗ trợ chọn nhiều PDF cùng lúc (`multiple`); cho phép khai báo thông tin metadata độc lập từng văn bản (tiêu đề, số hiệu, URL nguồn chính thức, ngày ban hành); cơ chế gửi tuần tự từng tệp vào `POST /api/v1/admin/documents/upload` để tránh quá tải bộ xử lý PDF; hiển thị tiến độ `Đang nhập tệp n/tổng…`, trạng thái riêng biệt cho từng tệp (`ready`, `uploading`, `success`, `failed`, `unknown`), nút "Dừng nhập tệp" (`AbortController`), và nút "Thử lại các tệp chưa thành công"; kiểm tra trùng lặp 2 tầng (chặn trùng byte SHA-256 mã 409 `DUPLICATE_PDF_HASH`, cảnh báo trùng nội dung chữ NFC `possible_duplicate_content` kèm danh sách tối đa 5 bản nháp/nguồn đối chiếu).
- **Nhập từ URL:** ô nhập; nếu tên miền không có trong danh sách: "Tên miền này chưa nằm trong danh sách cho phép. Nhờ quản trị viên thêm tên miền sau khi xác minh." Không có nút bỏ qua.
- Trang hồ sơ tài liệu có tab: **Thông tin** (metadata chuẩn, nguồn, hash, nút "Mở trang công bố chính thức" nếu đã xác minh) · **Phiên bản** · **Cây điều khoản** · **Quan hệ** (sửa đổi/tham chiếu) · **Lịch sử** (audit).
- Danh sách chỉ hiện tài liệu người dùng có quyền (lọc server).

#### S5. Hàng đợi duyệt (risk-prioritized)

Bảng: **Tài liệu và phiên bản · Lý do vào hàng đợi · Rủi ro · Người phụ trách · Hạn · Trạng thái**.

- Lý do: Độ tin cậy parse thấp · Nhảy khoản · Chuyển mã font · Tọa độ trang lệch · Hiệu lực chưa duyệt · Đề xuất của AI.
- Rủi ro: **Cao / Trung bình / Thấp** hiển thị bằng icon + chữ (không chỉ màu), mặc định xếp Cao lên trước.
- Bộ lọc theo lý do, rủi ro, người phụ trách. Hành động hàng loạt chỉ cho việc **gán người phụ trách**; duyệt luôn từng mục.
- Hàng trống: "Không có mục chờ duyệt. Tài liệu mới nạp sẽ xuất hiện ở đây."

#### S6. Curator Split-View

```text
┌ Tài liệu X · bản 3 · Mục 4/17 trong hàng đợi │ Đã lưu nháp 14:32 │ Revision 8 ─────────┐
├───────────────────────────────────────┬───────────────────────────────────────────────┤
│ PDF.js — bản bất biến                 │ [Cây node] [Hiệu lực] [Quan hệ] [Đề xuất của AI]│
│ [Trang 12 ▼]  tô sáng span đang chọn  │ ▾ Chương II                                   │
│                                       │   ▾ Điều 5                                     │
│   …trang PDF…                         │     ● Khoản 2  (độ tin cậy parse: thấp)        │
│   [span]                              │ ─ Form node ──────────────────────────────────│
│                                       │ Nhãn [Khoản 2]  Vị trí [5.2]                   │
│                                       │ Hiệu lực từ [..] đến [..]  Trạng thái [Chưa rõ]│
│                                       │ Quan hệ sửa đổi [+ Thêm]                       │
│                                       │              [Bỏ qua]  [Lưu nháp]  [Duyệt]     │
└───────────────────────────────────────┴───────────────────────────────────────────────┘
```

- Click node → PDF nhảy tới span; click vào PDF → focus node tương ứng; điều khoản chưa có node → mở tác vụ "Phân tích lại trang".
- **Lưu nháp tự động** (chỉ báo "Đã lưu nháp") khác **Duyệt**: Duyệt dùng endpoint riêng, role REVIEWER, kiểm `If-Match`/revision; xung đột revision thì hiện "Mục này vừa được người khác sửa. Tải lại để xem thay đổi."
- Phím tắt (đi tiếp/lùi node) **vô hiệu khi đang nhập văn bản**; không có phím tắt duyệt.
- Duyệt thay đổi hiệu lực hoặc quan hệ sửa đổi: hộp thoại xác nhận: "Thay đổi này ảnh hưởng cách hệ thống trả lời với các ngày từ [ngày]. Hành động được ghi nhật ký." — nút "Duyệt" / "Quay lại".
- Tab **Đề xuất của AI** (C1): mỗi đề xuất có loại, span nguồn, độ tin cậy dạng nhãn, nút **Chấp nhận vào nháp / Sửa / Từ chối**. Accept của CURATOR chỉ lưu nháp và audit; phê duyệt tài liệu/hiệu lực/amendment qua REVIEWER và endpoint riêng, không publish ngầm. Thao tác hàng loạt cần xác nhận.
- Chat Agent thu nhỏ ở màn hình này (không che form).

#### S7. Danh mục (SYS_ADMIN/CURATOR)

Cây danh mục kéo thả, độ sâu cấu hình; cột: Tên · Mã cố định · Người phụ trách · Quyền xem · Số tài liệu · Trạng thái (Hoạt động/Ẩn/Đã xóa). Hành động: Thêm · Sửa · Ẩn · Xóa mềm · Khôi phục · Nhập/Xuất JSON/CSV (có bước kiểm tra trước khi áp dụng). Xóa mềm nêu rõ: "Tệp gốc và embedding vẫn được giữ nếu tài liệu còn thuộc danh mục khác." Cấm tạo vòng lặp: báo lỗi ngay tại ô chọn danh mục cha.

#### S8. Domain cho phép (SYS_ADMIN)

Bảng: **Tên miền · Người xác minh · Ngày xác minh · Ghi chú · Trạng thái (Bật/Tắt) · Lần dùng gần nhất**. Nút **Thêm tên miền** mở trình hướng dẫn 3 bước: (1) nhập tên miền → hệ thống kiểm tra DNS, HTTPS, không phải địa chỉ nội bộ; (2) xác nhận người xác minh và ghi chú nguồn; (3) bật. Mọi thay đổi có audit. Tắt một tên miền: cảnh báo "Các lần nhập mới từ tên miền này sẽ bị chặn."

#### S9. Mô hình AI và chế độ vận hành (SYS_ADMIN)

- **Chế độ:** hai thẻ **API Mode** và **Local Mode** hiển thị trạng thái hiện hành, điều kiện cần (với Local Mode: kết quả `verify-egress`, model local sẵn sàng). Đổi chế độ cần xác nhận và ghi audit.
- **Model Registry:** bảng Provider · Endpoint · Model · Capability (chip: Phân tích/Chat · Embedding · Rerank · Sinh · OCR) · Vùng riêng tư · Trạng thái · Chi phí/định mức · [Kiểm tra kết nối]. Khóa API chỉ nhập một lần, hiển thị dạng che, không đọc lại.
- **Stage routes:** ma trận Stage × (API Mode, Local Mode) chọn model; fallback chỉ cùng vùng riêng tư; cảnh báo nếu stage Local Mode trỏ vào model không chạy local.
- Form cấu hình API gồm adapter/provider được hỗ trợ, endpoint, model ID, tham số và secret nhập một lần; form Local gồm runtime/endpoint nội bộ được duyệt, artifact/model ID, revision và tham số. Có trạng thái “Chưa cấu hình”, “Chưa kiểm tra”, “Sẵn sàng”, “Lỗi”; không điền sẵn một model/key/host bắt buộc. Kiểm tra kết nối chỉ bằng dữ liệu tổng hợp và vẫn theo egress policy.
- Runtime/model local chọn bằng manifest ID hoặc đường dẫn tương đối trong root cài đã kiểm; server resolve/kiểm containment theo B.8. API/LAN endpoint vẫn là cấu hình endpoint có policy; không cho form trở thành lối đọc/chạy file tùy ý ngoài root.
- **Chính sách theo danh mục:** công tắc "Cho phép xử lý bằng AI từ xa" mặc định **Tắt**; bật cần xác nhận kèm cảnh báo về dữ liệu được gửi ra ngoài.
- Không hiển thị chain-of-thought của model ở bất kỳ đâu.

#### S10. Bộ nhớ của tôi (USER)

Các khối: **Chế độ không lưu** (công tắc) · **Hội thoại gần đây** (danh sách; xem tóm tắt, xóa từng phiên) · **Sở thích** (opt-in: danh mục mặc định, phạm vi hay dùng) · **Thời hạn lưu** (chỉ đọc, do quản trị đặt) · **Xóa tất cả bộ nhớ**. Văn bản giải thích ngắn: "Bộ nhớ giúp trợ lý hiểu câu hỏi nối tiếp. Câu trả lời luôn lấy căn cứ lại từ kho tài liệu." Xóa tất cả cần xác nhận và là xóa thật.

#### S11. Bộ kiểm thử: duyệt Gold và trap set (REVIEWER/chuyên gia nghiệp vụ)

```text
┌ Bộ kiểm thử · Gold v0 · Đã duyệt 62 / 180 · Calibration 54 │ Held-out 126 (khóa) ───┐
├──────────────────────┬──────────────────────────────────────────────────────────────┤
│ Danh sách case       │ Case G-0073                                                   │
│ [lọc: Chưa duyệt ▼]  │ Câu hỏi: …                          Ngày áp dụng: …           │
│ G-0071 ✔ Đã duyệt    │ Căn cứ do agent đề xuất: số hiệu · Điều/Khoản/Điểm · bản       │
│ G-0072 • Chưa duyệt  │ “…đoạn trích…”  [Mở trong PDF]                                 │
│ G-0073 • Chưa duyệt  │ Đáp án mẫu (agent soạn): …                                    │
│ …                    │ Loại: [Trực tiếp ▼]  Có cần trả lời "không đủ căn cứ"? [ ]    │
│                      │ [Duyệt]  [Yêu cầu sửa + ghi chú]  [Loại bỏ case]              │
└──────────────────────┴──────────────────────────────────────────────────────────────┘
```

- Mỗi case có trạng thái **Nháp → Đã duyệt / Cần sửa / Loại bỏ**, người duyệt, thời điểm. **Chỉ case Đã duyệt tính vào chuẩn.**
- Người duyệt luôn thấy đoạn nguồn gốc và mở được PDF; không có nút "duyệt tất cả".
- Tập held-out khóa cả API lẫn giao diện đối với người tune; case/đáp án không nằm trong log benchmark của họ. Hiện `scenario_group_id`, `split_revision` và trạng thái candidate đã khóa; chỉ đánh giá cuối sau khi freeze cấu hình. Tập đã dùng để quyết định sửa/tune không tiếp tục được gọi là held-out độc lập.
- Trap set có tab riêng cùng cách duyệt.

#### S12. Dashboard chất lượng (SYS_ADMIN, REVIEWER)

Thẻ số liệu và biểu đồ theo thời gian: `retrieval_ms`, `evidence_ready_ms`, `first_claim_ms`, `final_answer_ms` (P50/P95, đường theo thời gian); tỷ lệ từ chối đúng/sai; `unsupported_claim_rate`, `wrong_doc_rate`, `wrong_node_rate`, `false_premise_detection_rate`, `validator_reject_rate`; tiến độ duyệt Gold (đã duyệt/mục tiêu 150–200); lịch sử chạy benchmark với bộ lọc theo model/tokenizer/corpus hash. Mỗi số liệu ghi **môi trường đo và thời điểm**; không hiển thị số khi chưa có dữ liệu (hiện "Chưa có số đo").

#### S13. Đăng nhập, quyền và trang lỗi

- Đăng nhập cục bộ; không dùng dịch vụ ngoài (captcha, font, analytics). Sai mật khẩu: "Tên đăng nhập hoặc mật khẩu không đúng." Khóa tạm sau nhiều lần sai, nêu thời gian chờ.
- Không có quyền vào một trang: "Bạn chưa có quyền vào mục này." (không gợi ý mục đó chứa gì).
- 404/500: nêu việc gì xảy ra, mã tham chiếu để báo quản trị, nút về trang chủ.

#### S14. Shell desktop USER

Tái sử dụng S3 (chat), S1 (workspace), S2 (viewer), S10 (bộ nhớ) và S13 (đăng nhập); không nhân bản workflow. Chuỗi trạng thái: `SIGNED_OUT → LOGIN → ORB ↔ PANEL ↔ WORKSPACE`; mất phiên quay về LOGIN, mất mạng giữ draft và trạng thái lỗi rõ.

- **Login:** cửa sổ nền đục, chữ dễ đọc, không trong suốt. Đăng nhập thành công đóng/ẩn hẳn khung login trước khi hiện Orb; không để bóng mờ hoặc bề mặt tương tác dư phía sau.
- **Orb:** hình tròn 56–64px, nền/vùng hit-test khớp hình; không hình tròn trong hình vuông, không khung viền/bóng cửa sổ ngoài. Mở/thu bằng click lặp; nếu bật kéo, phân biệt drag với click và không bắt sự kiện ngoài Orb.
- **Panel/workspace:** nền đục theo theme; vùng kéo riêng không đè tên trợ lý, nút hoặc text; vùng resize ở cạnh/góc riêng, kích thước tối thiểu và clamp work area. Không yêu cầu cửa sổ trong suốt cho nội dung đọc.
- **Vị trí:** lấy work area, DPI và màn hình từ platform API; nhớ lựa chọn vị trí/kích thước theo user nếu cho phép, không lưu nội dung hội thoại vào local storage. Sau đổi màn hình/DPI, đưa cửa sổ về vùng nhìn thấy.
- **Khay hệ thống:** Hiện/Ẩn trợ lý, Đăng xuất, Thoát; có điều khiển tương đương trong app cho người dùng bàn phím. Đóng panel thu về Orb; Ẩn tạm chỉ còn tray; Thoát kết thúc client, không dừng server LAN.
- **Cài đặt:** shell/helper/runtime desktop dùng dependency-manifest dưới root cấu hình `E:\Programs` theo B.8; Không hardcode PATH/LLM trong frontend, shell hoặc helper; lấy executable/model từ cấu hình/manifest, không dựa vào PATH toàn cục hoặc cài tool ngầm vào hồ sơ user.
- **Bật/tắt luôn trên cùng:** là sở thích user, mặc định OFF; không chặn cửa sổ đăng nhập/modal hệ thống. Không mở cửa sổ console/cmd khi chạy app hoặc helper nền.
- **Luồng chung:** mở đầy đủ/PDF/thu lại không mất session; backend là nguồn trạng thái hội thoại, state trình bày tách khỏi dữ liệu nghiệp vụ. Không giả lập AI khi model chưa cấu hình; không trộn User/Admin.

### D.6 Thư viện component

Tất cả component dùng chung design tokens và có story/test trạng thái.

| Component | Trạng thái và thuộc tính chính | Trợ năng |
|---|---|---|
| `AppShell`, `TopBar`, `SideNav` | Thu gọn/mở; mục theo quyền | Landmark `banner`/`navigation`/`main`; skip link |
| `ScopeBar` (`CategorySelect`, `DocTypeSelect`, `AsOfDatePicker`, `ModeBadge`) | `as_of_date` quá khứ có nhấn; badge chỉ đọc | Nhãn đầy đủ cho từng điều khiển |
| `QueryComposer` | Rỗng, đang nhập, đang gửi, khóa (chưa chọn danh mục); Enter gửi, Shift+Enter xuống dòng | `aria-describedby` lý do khóa |
| `FactChip` | `user_confirmed` (nét liền), `extracted_unconfirmed` (nét đứt + "chưa xác nhận"), `inferred_uncertain` (nét chấm + "suy đoán"); đang sửa; đã chỉnh (dirty) | Nút sửa/xóa có nhãn; thông báo thay đổi qua `aria-live` |
| `DirtyFactBar` | Hiện khi có chip dirty; nút "Cập nhật dữ kiện & Tra cứu lại" bật khi hợp lệ | Vai trò `status` |
| `ResultStatus` | 4 nhãn + "Chưa tìm thấy tài liệu được phép truy cập" (D.7) | Icon + chữ |
| `EvidenceGroupTabs` | Tab theo vai trò (chỉ hiện tab có thẻ) | Mẫu tabs WAI-ARIA |
| `EvidenceCard` | Thu gọn (2–3 dòng) / mở rộng; chọn; nhãn "Nguồn ngoài danh mục"; `EffectiveBadge`; `stale` | Nút "Mở trong PDF" có tên đầy đủ |
| `CitationLink` (`[n]`) | Hover xem trước 2 dòng; mở viewer; kiểm quyền khi mở | Văn bản thay thế "Căn cứ n: [số hiệu, Điều…]" |
| `CoverageChecklist` | Mỗi mục: Đạt / Chưa đạt / Chưa xác minh; thu gọn "Đã kiểm tra 3/4" | Danh sách có văn bản trạng thái |
| `ClaimItem` | Có `[n]`; trạng thái claim; "chưa xác minh" | Gắn kết claim–căn cứ qua `aria-describedby` |
| `MissingInfoChips`, `FollowUpChips` | Bấm để điền/hỏi; tối đa số chip cấu hình | Nút thật, không phải thẻ `div` |
| `AnalysisTable` (A1) | Hàng: điều kiện · trạng thái (đã thỏa/chưa xác minh/ngoại lệ) · căn cứ `[n]` | Bảng có tiêu đề cột |
| `NoteHighlights` (A4) | Bật/tắt tô nổi trong thẻ và viewer | Công tắc có nhãn |
| `VersionDiff` (A5) | Cạnh nhau/đan xen; chú thích thêm/bớt bằng ký hiệu + chữ | Không chỉ màu |
| `RelatedList` (A6) | Nhóm: văn bản hướng dẫn · sửa đổi · tham chiếu đến · tham chiếu từ; nhãn "chưa duyệt" | Danh sách có cấp |
| `PdfViewer`, `PdfToolbar`, `ArticleTree` | Tải, lỗi, fallback; mục lục thu gọn | Điều hướng bàn phím; `aria-current` |
| `AmendmentBanner` | `modified`, `repealed`, `suspended`, `not_yet_effective`, `unknown`; thu gọn nhưng nhãn còn ở toolbar | Vai trò `alert` khi mở; chữ + icon |
| `TwoPhaseSkeleton` | Pha 1, chuyển Pha 2 | `aria-busy`, thông báo phase |
| `StaleLabel`, `StaleResultOverlay` | Nhãn trên kết quả cũ | `aria-live` polite |
| `FeedbackDialog` | 4 loại + ghi chú | Quản lý focus |
| `CopyWithScope` | Sao chép gồm phạm vi, ngày áp dụng, cảnh báo | Thông báo "Đã sao chép" |
| `AgentLauncher`, `AgentPanel` | Đóng, mở, thu nhỏ, toàn màn hình; huy hiệu | Xem D.9 |
| `DesktopShell`, `DesktopWindowControls`, `TrayMenu` | Login/Orb/Panel/Workspace, kéo/resize, DPI, hiện/ẩn/đăng xuất/thoát | Vùng kéo riêng; menu/nút bàn phím; native không làm mất focus |
| `MemoryCenter`, `SessionMemoryDrawer` | Khối ở S10 & ngăn kéo bộ nhớ phiên RAM: danh sách facts/items, số lượng badge, nút Dừng/Thử lại lượt, xóa từng mục, xóa toàn bộ RAM, công tắc "Lưu vào sở thích tra cứu" | Nhãn công tắc rõ; vai trò status cho các cập nhật |
| `DataTable`, `ReviewQueueTable` | Sắp xếp, lọc, trống, lỗi; phân trang | Tiêu đề cột `scope`; hàng có thể chọn bằng bàn phím |
| `CuratorSplitView`, `NodeForm` | Draft/duyệt, xung đột revision | Phím tắt chỉ khi không ở ô nhập |
| `AiSuggestionPanel` | Chấp nhận/Sửa/Từ chối, lý do từ chối | Nhãn độ tin cậy dạng chữ |
| `ConfirmDialog` | Mô tả hậu quả cụ thể, nút nêu đúng hành động | Modal; trả focus |
| `JobProgress` | Chờ, chạy, cần duyệt, lỗi, hủy, xong | Thanh tiến độ có văn bản |
| `AllowlistTable`, `DomainWizard` | 3 bước, kiểm tra | |
| `ModelRegistryTable`, `ModeCard` | Bảng cấu hình AI Provider/Model: adapter, endpoint (hỗ trợ LAN/localhost), model ID, params (temperature, max_tokens, json_mode), secret_ref (lọc blacklist), in-place update | Mask key; cảnh báo route sai; kiểm tra kết nối (probe) |
| `MetricTile`, `LatencyChart` | Có dữ liệu / "Chưa có số đo" | Biểu đồ kèm bảng dữ liệu thay thế |
| `GoldReviewList`, `GoldCaseView` | Nháp/Đã duyệt/Cần sửa/Loại; held-out khóa | |
| `EmptyState`, `ErrorState`, `Toast` | Nêu hành động tiếp theo | `role="status"` / `alert` |

### D.7 Nhãn và trạng thái chuẩn

**Kết quả hỏi đáp**

| Nhãn | Icon | Màu | Khi nào |
|---|---|---|---|
| Đã xác định căn cứ | check-circle | `--color-success` trên `--color-success-bg` | Nguồn, hiệu lực, điều kiện áp dụng được kiểm theo quy tắc và đủ độ phủ |
| Có điều kiện | alert-triangle | `--color-warning` trên `--color-warning-bg` | Còn điều kiện, ngoại lệ hoặc hiệu lực chưa xác minh |
| Thiếu căn cứ | file-search | `--color-text-secondary` trên `--color-surface-muted` | Không đủ căn cứ để trả lời |
| Nguồn xung đột | alert-octagon | `--color-danger` trên `--color-danger-bg` | Các nguồn nói khác nhau, cần người có thẩm quyền xác minh |
| Chưa tìm thấy tài liệu được phép truy cập | lock hoặc search | trung tính | Không có tài liệu trong quyền; không tiết lộ tồn tại |

**Hiệu lực node theo ngày áp dụng**

| `amendment_state` | Nhãn tiếng Việt | Icon | Màu |
|---|---|---|---|
| `active` | Đang áp dụng tại [ngày] | check-circle | success |
| `modified` | Đã sửa đổi từ [ngày] | file-pen | warning |
| `repealed` | Đã bãi bỏ từ [ngày] | ban | danger |
| `suspended` | Tạm đình chỉ | pause-circle | warning |
| `not_yet_effective` | Chưa có hiệu lực | clock | evidence (xanh dương nhạt) |
| `unknown` | Hiệu lực chưa xác minh | help-circle | trung tính |

Khi `as_of_date` trước ngày sửa đổi, dùng câu: "Quy định được thay đổi từ [ngày] (sau ngày tra cứu). Cần xem quy định chuyển tiếp." Không nói bản cũ chắc chắn không áp dụng.

**Mục checklist độ phủ**

| Mục | Nhãn hiển thị |
|---|---|
| `source_verified` | Nguồn và trích dẫn đã kiểm tra |
| `effective_checked` | Hiệu lực tại ngày áp dụng |
| `applicability_checked` | Điều kiện áp dụng |
| `claim_supported` | Nhận định có căn cứ hỗ trợ |
| `transition_checked` | Quy định chuyển tiếp |
| `required_facts_complete` | Dữ kiện bắt buộc |
| `scope_expansion` | Mở rộng ngoài phạm vi đúng chính sách |

Mỗi mục có 3 trạng thái: **Đạt** (check) · **Chưa đạt** (x) · **Chưa xác minh** (help). Mặc định hiển thị thu gọn "Đã kiểm tra X/Y mục", mở rộng được.

API hiện hành dùng các tên checklist ở bảng trên và enum `passed / failed / unknown`; không dùng boolean để ép “chưa xác minh” thành false. `effective_status_checked`/`node_effective_checked` là tên cũ, không phát từ API v1.3. `claim_supported=passed` đòi hỏi đủ kiểm tra hỗ trợ đã định nghĩa; chỉ pass số liệu/phủ định không được coi là chứng minh ngữ nghĩa của nhận định.

**Công việc ingest:** Chờ · Đang đọc trang · Phân tích cấu trúc · Cần duyệt · Lỗi · Đã hủy · Xong. **Đề xuất AI:** Đề xuất · Đã chấp nhận · Đã từ chối · Hết hạn. **Gold case:** Nháp · Đã duyệt · Cần sửa · Loại bỏ.

### D.8 Nội dung giao diện (microcopy)

Nguyên tắc: tiếng Việt thuần, câu chủ động, nêu đúng việc sẽ xảy ra; lỗi nêu **chuyện gì đã xảy ra và cách xử lý**, không xin lỗi chung chung; trạng thái rỗng dẫn tới hành động tiếp theo.

| Ngữ cảnh | Nội dung |
|---|---|
| Placeholder ô hỏi | "Mô tả tình huống hoặc hỏi về một Điều, Khoản…" |
| Nút gửi | "Tra cứu" |
| Nút sau khi sửa dữ kiện | "Cập nhật dữ kiện & Tra cứu lại" |
| Dải dirty | "Đã chỉnh sửa dữ kiện — kết quả bên dưới dựa trên dữ kiện trước đó" |
| Skeleton pha 1 | "Đang tìm căn cứ trong danh mục đã chọn…" |
| Pha 2 | "Đã tìm thấy và kiểm tra nguồn của [X] căn cứ. Đang phân tích điều kiện áp dụng, hiệu lực, quy định chuyển tiếp và ngoại lệ…" |
| Câu đã hiểu | "Đang hiểu là: “…”" + nút "Sửa" |
| Thiếu căn cứ | "Chưa đủ căn cứ để trả lời. Các tài liệu được phép truy cập chưa có quy định phù hợp với câu hỏi này." |
| Không tìm thấy/không quyền | "Chưa tìm thấy tài liệu được phép truy cập." |
| Tiền đề sai | "Không có [Điều X] trong [tên văn bản]. Văn bản này có Điều 1 đến Điều [N]." |
| Giải thích lỗi | "Giải thích tạm thời không khả dụng. Các căn cứ bên dưới đã được kiểm tra nguồn." |
| Snapshot stale | "Dữ liệu hiệu lực đang được cập nhật. Chưa thể khẳng định hiệu lực tại ngày này." |
| Kết quả cũ | "Kết quả dựa trên dữ kiện trước đó" · "Cần kiểm lại vì dữ liệu hiệu lực đã thay đổi" |
| Fallback viewer | "Chưa tô sáng chính xác vị trí đoạn này trên trang." |
| Banner sửa đổi | "Khoản này trên PDF gốc đã được sửa đổi/bãi bỏ bởi [văn bản] từ ngày [ngày]." + "Xem văn bản sửa đổi" |
| Hiệu lực chưa rõ | "Hiệu lực chưa xác minh. Hệ thống chưa kết luận khoản này còn hay hết hiệu lực." |
| Nguồn ngoài danh mục | "Nguồn ngoài danh mục đã chọn" |
| Sao chép | "Sao chép kèm phạm vi" → thông báo "Đã sao chép, kèm phạm vi và cảnh báo." |
| Lưu ý cuối kết quả | "Kết quả hỗ trợ tra cứu và tham mưu, không thay thế quyết định của người có thẩm quyền." |
| Phản hồi | "Căn cứ sai" · "Thiếu căn cứ" · "Văn bản hết hiệu lực" · "Trích dẫn sai đoạn" |
| Domain bị chặn | "Tên miền này chưa nằm trong danh sách cho phép. Nhờ quản trị viên thêm tên miền sau khi xác minh." |
| Xung đột revision | "Mục này vừa được người khác sửa. Tải lại để xem thay đổi." |
| Xác nhận hiệu lực | "Thay đổi này ảnh hưởng cách hệ thống trả lời với các ngày từ [ngày]. Hành động được ghi nhật ký." → "Duyệt" / "Quay lại" |
| Xóa bộ nhớ | "Xóa toàn bộ bộ nhớ của bạn? Hành động này không hoàn tác." → "Xóa bộ nhớ" / "Giữ lại" |
| Chế độ không lưu | "Hội thoại này sẽ không được ghi nhớ." |
| Bộ nhớ (giải thích) | "Bộ nhớ giúp trợ lý hiểu câu hỏi nối tiếp. Câu trả lời luôn lấy căn cứ lại từ kho tài liệu." |
| Danh mục trống | "Danh mục chưa có tài liệu đã duyệt. Nhờ người phụ trách nạp tài liệu." |
| Mất kết nối | "Mất kết nối tới máy chủ. Nội dung bạn nhập vẫn được giữ." + "Thử lại" |
| Huy hiệu Local Mode | "Local Mode · offline" (tooltip: "Mọi xử lý chạy trên máy chủ nội bộ, không gửi dữ liệu ra ngoài.") |
| Huy hiệu API Mode | "API Mode" (tooltip: "Chỉ dữ liệu được chính sách cho phép mới được gửi tới nhà cung cấp AI.") |

Cấm dùng trong giao diện: "Đã khóa X căn cứ xác thực", "Đã xác minh X căn cứ" (khi chưa chứng minh hiệu lực và độ phủ), phần trăm độ chính xác, "chắc chắn", "AI đảm bảo".

### D.9 Trợ năng và hiệu năng giao diện

**Trợ năng (WCAG 2.2 AA tối thiểu)**

- Mọi chức năng thao tác được bằng bàn phím; thứ tự focus theo thứ tự đọc; focus luôn nhìn thấy (3px, offset 2px).
- Chat Agent: launcher là `button`; panel là `role="dialog"` **không modal** (`aria-modal="false"`) khi docked, `aria-labelledby` tới tiêu đề; mở panel chuyển focus vào ô nhập; `Esc` đóng và trả focus về launcher; không bẫy focus trừ khi toàn màn hình trên điện thoại; luồng stream nằm trong vùng `aria-live="polite"`, chỉ thông báo mốc quan trọng (đã có căn cứ, đã có kết quả), không đọc từng token.
- Mục tiêu chạm ≥ 44×44px trên điện thoại; hỗ trợ zoom tới 200% mà không mất chức năng; không cuộn ngang ở 320px.
- Màu không là tín hiệu duy nhất; biểu đồ có bảng dữ liệu thay thế.
- `prefers-reduced-motion` tắt chuyển động trượt/mờ.
- Nội dung tiếng Việt có dấu hiển thị đúng; thuộc tính `lang="vi"`; copy văn bản kèm nguồn.

**Hiệu năng giao diện**

- Launcher gần như không tốn tải trang: bundle panel, PDF viewer, biểu đồ **tải lười** (code-splitting); prefetch khi hover launcher hoặc khi nhập vào ô hỏi.
- PDF viewer dựng theo trang (virtualized), chỉ render trang đang xem và lân cận; prefetch trang được trích khi hover `[n]`.
- Danh sách dài (tài liệu, hàng đợi, case Gold) dùng phân trang hoặc cuộn ảo.
- Local Mode: không tải tài nguyên từ bên ngoài (CDN, font, analytics, telemetry).
- Ngân sách tải trang đo trước/sau khi thêm widget (WP 4.7); không tuyên bố số trước khi đo.

### D.10 Kiểm thử giao diện (bắt buộc)

- **Snapshot ảnh** cho: trạng thái hiệu lực (`active/modified/repealed/suspended/not_yet_effective/unknown`), nhãn kết quả (4 + không tìm thấy), FactChip (3 loại + dirty), Sticky Amendment Banner (mở/thu gọn), EvidenceCard, panel Chat Agent (đóng/mở/thu nhỏ/điện thoại), skeleton hai pha, fallback viewer.
- **Contrast test tự động** cho mọi cặp màu/trạng thái (token); không đạt thì chỉnh token.
- **Lint** cấm HEX cứng trong component.
- **Kiểm tra trợ năng tự động** (axe hoặc tương đương) trên mọi màn hình + kiểm thủ công bàn phím/screen reader cho S1, S3, S6.
- **E2E**: luồng L-1 đến L-7 (C.11); Local Mode không phát sinh request ra ngoài; chuyển trang giữ hội thoại; mở citation cũ kiểm lại quyền.
- **Nội dung**: test chuỗi cấm ở D.8 không xuất hiện trong bundle.
- **Desktop USER:** kiểm thực tế login → Orb → chat → PDF/workspace → thu/mở → tray → logout/exit; Orb tròn không nền vuông/bóng dư, nền login/panel đục, vùng kéo không đè chữ, resize được, không console. Kiểm DPI 100/125/150/200%, đổi màn hình/work area, zoom 200%, các bề rộng 320/768/1024/1280px và thu/mở không mất nội dung.
