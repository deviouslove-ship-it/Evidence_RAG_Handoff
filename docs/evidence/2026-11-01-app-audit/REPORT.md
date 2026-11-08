# Rà soát độ đúng, độ đầy đủ và độ ổn định — 01/11/2026

Đã rà soát backend, tìm kiếm văn bản, truy xuất chat, SSE, kiểm soát quá tải,
quản lý phiên, biên xử lý PDF, giao diện và vỏ Windows. Sửa các lỗi có bằng chứng
tái hiện; không coi kiểm thử xanh là nghiệm thu nghiệp vụ hoặc bảo đảm máy không
thể treo trong mọi điều kiện.

## Lỗi và thay đổi

| Vấn đề xác nhận | Sửa tại nguyên nhân |
|---|---|
| Mất kết quả sau 5.000 ứng viên; tổng và trang khoản không đầy đủ | PostgreSQL tính tổng và phân trang document/clause trước khi truyền nội dung; bỏ cắt tập ứng viên ở 5.000 |
| Từ khóa không dấu bỏ sót nội dung có dấu | Tìm đủ từ trên cả chỉ mục gốc và folded |
| Từ khóa ngoài ngoặc kép bị bỏ qua | Parser giữ các từ; tầng phrase áp dụng điều kiện từ khóa đi kèm |
| Số hiệu có tiền tố hoặc `NĐ/ND` không nhất quán | Tách phần số khỏi tên loại văn bản; chuẩn hóa `đ/Đ` trước SQL `lower` |
| Chat có cụm từ bỏ mất số hiệu nên chọn văn bản khác | Adapter giữ số hiệu, dùng phân trang/xếp hạng chung trước giới hạn trả về |
| Chữ hoa tiếng Việt và biến thể backfill bị gắn sai tầng | Lấy ứng viên bằng folded GIN, xác minh trên nội dung chuẩn hóa riêng, không phụ thuộc locale C |
| Chờ pool, ACL hoặc đếm không chịu hạn chung | Một ngân sách thời gian bao trùm phần DB; trả `SEARCH_TIMEOUT`, giải phóng slot khi hủy |
| Tìm kiếm có thể xếp hàng không giới hạn | Giới hạn 4 lượt DB tìm kiếm/process; từ chối quá tải sau khoảng 100 ms bằng `SEARCH_BUSY` |
| Khóa audit kéo dài thời gian trả kết quả đọc | Audit tìm kiếm có hạn 250 ms; hết hạn ghi cảnh báo và trả kết quả |
| SSE đã hoàn tất nhưng UI chờ đóng kết nối | Dừng đọc/hủy reader khi có `answer_complete`; vẫn kiểm tra đủ evidence/analysis |
| Truy xuất chat khoảng 5,6 giây trên corpus lớn | Lọc ACL document trước, lấy ứng viên bằng chỉ mục/metadata rồi hydrate, tránh materialize security view UNION rộng; giữ tìm tiêu đề/nhãn của bản ghi cũ |

Đã kiểm ACL âm, draft/provenance, hiệu lực, số hiệu, không dấu, chữ hoa, kì/kỳ,
phrase xuyên breadcrumb, tiêu đề/nhãn chưa có trong index, tổng 5.003 khoản và cửa
sổ khoản sau vị trí 5.000. Không đổi nội dung chứng cứ gốc, tự duyệt nguồn hoặc
thay định tuyến model.

## Đo hiệu năng

Corpus **HƯ CẤU**: 1.000 văn bản × 100 khoản = 100.000 node; schema riêng, cùng
máy/cấu hình planner, có warm-up. Đây là thời gian dịch vụ truy xuất dữ liệu,
không bao gồm model AI thật hay toàn bộ thao tác UI.

| Luồng | p95 trước | p95 sau | Số mẫu/lần |
|---|---:|---:|---:|
| Cụm từ | 333,97 ms | 82,46 ms | 12 |
| Từ khóa | 327,05 ms | 60,57 ms | 12 |
| Truy xuất chat không ngoặc kép | 5.663,26 ms | 1.810,39 ms | 5 |

Nguồn: `benchmark-before/benchmark.json`, `benchmark-final/benchmark.json`
(chat trước tối ưu), `benchmark-accepted/benchmark.json` (SQL được giữ lại).
Chat ở corpus này vẫn khoảng 1,8 giây p95, chưa phải tức thì. Các thư mục benchmark
khác là phép đo trung gian/thử nghiệm; không thay số liệu mã cuối nêu trên.

Tải dồn 16 lượt tìm kiếm trên 100.000 node: 4 hoàn tất, 12 nhận `SEARCH_BUSY`;
slot trở về 4/4, DB còn phản hồi. Khoảng cách heartbeat event loop lớn nhất khoảng
46 ms; không phải đo độ trễ khung hình WebView hay hệ điều hành. Plan SQL trang
phrase thực tế dùng `document_nodes_search_folded_gin`, không ép tắt seqscan.

## Kiểm chứng

- `scripts/verify.ps1`: **12/12** đạt; **193 backend + 73 frontend** test, không
  skip PostgreSQL. Lint, typing, build và hợp đồng OpenAPI đạt.
- **17 native Rust test** đạt. Đã build release với `custom-protocol`, lockfile và
  runtime/cache hiện hữu; mở cửa sổ, quan sát chat và chuyển sang trang tìm kiếm,
  xác nhận phản hồi rồi dừng đúng tiến trình smoke.
- HTTP thật qua Uvicorn/schema riêng: đăng nhập, tìm 3 văn bản fixture approved,
  thiếu auth, SSE, **35 lượt chat liên tiếp**, 20 health request đồng thời, đăng
  xuất và từ chối token đã thu hồi. Không lỗi; server còn sống sau chạy.
- Test hiện hữu kiểm hủy lượt, timeout, mất phiên, cô lập crash/timeout PDF worker,
  dọn tệp tạm. Test mới kiểm cạn pool, hủy khi chờ pool, từ chối quá tải và khóa
  audit thật. Chrome E2E với fixture API được chạy lại sau build.
- Bằng chứng: `verification/summary.json`, các log `*-red.txt`, `native-tests.log`,
  `native-release-build.log`, `native-smoke.json`, `native-ui.txt`,
  `http/http-smoke.json`, `browser-e2e.json.log` và các thư mục benchmark.

## Giới hạn còn lại

- DB dev kiểm trực tiếp: **0 approved version, 0 provenance verified, 0 model ready**
  (`dev-data-status.json`). Chưa nghiệm thu độ đúng/đủ trên văn bản nghiệp vụ thật
  hoặc thời gian chọn căn cứ bằng model AI thật.
- HTTP smoke dùng dữ liệu/trạng thái duyệt HƯ CẤU; PDF chỉ là sentinel kiểm hash và
  biên byte, không nghiệm thu rendering/provenance nghiệp vụ. Schema và tệp tạm
  được dọn sau chạy.
- Native smoke chưa đăng nhập/kết nối backend ở cổng mặc định; HTTP được kiểm riêng,
  Chrome dùng API fixture. Chưa có phiên Windows xuyên suốt tới dữ liệu/model thật.
- Không tái hiện crash/treo trong các ca đã chạy; chưa soak nhiều giờ, thử OOM/toàn
  hệ điều hành hoặc chứng minh không rò rỉ bộ nhớ trong mọi điều kiện.
- Số RAM ở `native-smoke.json` chỉ là tiến trình vỏ Windows, không gồm WebView2,
  PostgreSQL hay model.
- Giới hạn độ sâu trang văn bản và timeout cấu hình vẫn áp dụng rõ bằng mã lỗi;
  vượt ngưỡng cần thu hẹp truy vấn. Admission/rate limit hiện theo process.
- Đã build executable release cục bộ; chưa tạo/ký/phát hành bộ cài NSIS mới.

## Chạy lại

Đặt `EVIDENCE_PROGRAMS_ROOT`, `EVIDENCE_TEST_DATABASE_URL`; giải executable từ
`configs/development-toolchain.json`. Benchmark dùng DSN ở `DATABASE_URL`.

```text
scripts/verify.ps1 -ProgramsRoot <ProgramsRoot>
python scripts/benchmark_search.py --documents 1000 --nodes-per-document 100 --iterations 12 --concurrency 16 --output <output>
python scripts/smoke_app_runtime.py --output <output> --soak-turns 35
cargo test --offline --locked --manifest-path src-tauri/Cargo.toml
cargo build --release --offline --locked --features custom-protocol --manifest-path src-tauri/Cargo.toml
```

Dùng `CARGO_HOME`/`CARGO_TARGET_DIR` từ runtime/cache dự án. Không thêm đường dẫn
tuyệt đối vào mã nguồn hoặc đổi dependency/lockfile.
