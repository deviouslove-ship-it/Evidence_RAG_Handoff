# Bộ hồ sơ bàn giao — Vietnamese Evidence RAG Agent

Hồ sơ gốc lập 21/10/2026 · Hồ sơ 1.1 · SRS v1.3. Các tài liệu bàn giao đã được tích hợp
vào `docs/` (bản duy nhất, không còn bản sao ở thư mục gốc). Trạng thái triển khai hiện
hành ghi tại `docs/implementation-status.md`; cách chạy và cấu trúc repo ở `README.md`.

## Thứ tự đọc và bản hiện hành

1. `docs/HOSO_BAN_GIAO.md` — hồ sơ chính A–G; B.7 chốt phương án cho 8 góp ý; C.12 và
   D.5 S14 mô tả desktop USER.
2. `docs/SRS_v1.3.md` — kỹ thuật hiện hành; §25 đồng bộ hợp đồng cho 8 góp ý, LLM
   API/Local và desktop; §26 là hợp đồng Search v1 (cập nhật owner 05/11 ở §26.8).
3. `docs/architecture-decisions/ADR-000.md` — quyết định, mặc định kỹ thuật và ranh giới
   nghiệm thu; ADR-001…009 ghi các quyết định triển khai sau đó.
4. `docs/PROMPT_KHOI_DONG.md` — prompt chung và phân công đủ 56 WP.
5. `docs/KE_HOACH_TRIEN_KHAI_TIM_KIEM_V1_Evidence_RAG.md` — kế hoạch Search v1 owner chốt.
6. `docs/TAI_LIEU_MO_TA_HE_THONG.md` và `docs/HUONG_DAN_SU_DUNG_VA_CAU_HINH_AI.md` —
   mô tả hệ thống và hướng dẫn vận hành Admin, gồm Quản lý văn bản.

`docs/history/SRS_v1.2.1.md` giữ nguyên byte làm bản lịch sử. Các quyết định cũ trong
file đó không phải yêu cầu hiện hành; không dùng nó để chọn lại mode/OS/Gold hoặc quyền
duyệt.

Ưu tiên: chỉ đạo mới của owner → B.4/B.7/B.8 → hồ sơ chính → SRS v1.3. ADR ghi lại quyết
định, không tạo nguồn đặc tả cạnh tranh.

## Ý định sản phẩm đã đối chiếu lịch sử

- USER mở app Windows và đăng nhập trong app; sau đó dùng Orb tròn góc phải desktop, bấm
  mở/thu chat, mở PDF/workspace cùng phiên, có stop/retry/tray/logout/exit.
- Admin Portal riêng cho tài liệu, danh mục, ingestion, tài khoản/quyền, AI Configuration,
  monitoring/audit và evaluation; USER chỉ thấy chức năng sử dụng trong quyền.
- Desktop/web/admin dùng chung authentication, backend, PostgreSQL, kho tài liệu và RAG;
  không chatbot hoặc DB riêng trên từng máy USER.
- LLM cấu hình API hoặc Local qua Registry/Router; không hardcode provider/model/endpoint/
  key/path. Owner tự nhập key sau. Local ngắt Internet, vẫn được kết nối endpoint LAN nội
  bộ đã duyệt; không tự chuyển API.
- Giữ theme Navy/Blue và tokens; chữ đọc được trên toàn app, Orb không nền vuông/bóng dư,
  login/panel nền đục, drag/resize không đè nội dung.
- Lịch sử chỉ dùng hiểu yêu cầu; không chuyển tài khoản test, secret, đường dẫn máy hoặc
  kết quả test cũ sang bộ mới.

## PATH, LLM và thư mục cài công cụ

- Không hardcode PATH/executable/model path hoặc LLM/provider/endpoint/key trong
  source/script.
- Owner chốt toàn bộ công cụ/tool/runtime dự án cài dưới `E:\Programs`; root đọc từ
  deployment profile `installation.programs_root` hoặc `EVIDENCE_PROGRAMS_ROOT`, không là
  hằng đường dẫn trong app.
- Manifest xác định app/runtime/database/tool/model store/cache dưới root; không dùng
  fallback PATH global/Program Files/AppData hoặc tự đổi ổ khi thiếu root. Chỉ cài thành
  phần cần theo role máy; máy USER không cài DB riêng.
- PDF/dữ liệu nghiệp vụ/log/backup dùng cấu hình riêng; không tự di chuyển dữ liệu. Chi
  tiết: hồ sơ B.8, SRS §25.9 và ADR-000.13.

## Thư mục parts/

Ba bản trích được sinh từ hồ sơ chính; chỉ khác tiêu đề bao ngoài và dấu phân cách cuối
phần. Khi cập nhật, sửa `docs/HOSO_BAN_GIAO.md` rồi sinh lại cả ba, không sửa độc lập.

| File | Nội dung | Dành cho |
|---|---|---|
| `P1_Mo_ta_tinh_nang_A-C.md` | Quyết định, 8 phương án, tính năng, desktop USER | Mọi luồng |
| `P2_Thiet_ke_UX_UI_D.md` | Design system, S1–S14, portal/desktop, responsive, trợ năng | Frontend/desktop |
| `P3_API_va_Plan_trien_khai_E-G.md` | API/SSE/permission matrix, 56 WP/gate, prompt | Backend/retrieval/evaluation |

Mọi đường dẫn triển khai lấy từ cấu hình/môi trường/platform API; không sao chép
host/port/path máy cũ.

## Việc cần owner/người nắm nghiệp vụ

F.11 nêu đủ: duyệt nguyên tắc nghiệp vụ quan trọng của ERD; duyệt Gold/trap; quyền tài
liệu và egress; domain; retention hội thoại/backup; ngưỡng chất lượng sau baseline; cung
cấp máy Windows đích và tự nhập provider/key hoặc model local. Chưa có key/model không cản
hoàn thiện các phần độc lập, nhưng gate AI thật vẫn chưa đạt. Chưa có chính sách retention
thì không lưu hội thoại dài hạn.
