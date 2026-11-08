# Dữ liệu thử

## `van-ban/`

Văn bản chính thức dùng để thử ứng dụng, sao chép từ thư mục nguồn do owner cung cấp. Mỗi thư mục con là
một danh mục; tệp nằm đúng thư mục gốc của nó. Văn bản công khai trên Internet, nên danh mục được tạo với
`remote_processing_allowed` bật (tắt bằng `--no-remote` khi nạp).

| Thư mục | Danh mục (mã) | Tệp |
|---|---|---|
| `Luat` | Luật (`LUAT`) | 2 |
| `Nghi_dinh` | Nghị định (`NGHI_DINH`) | 18 |
| `Quyet_dinh` | Quyết định (`QUYET_DINH`) | 70 |
| `Thong_tu` | Thông tư (`THONG_TU`) | 196 |
| `Thong_tu_lien_tich` | Thông tư liên tịch (`THONG_TU_LIEN_TICH`) | 5 |
| `Chi_thi` | Chỉ thị (`CHI_THI`) | 2 |
| `Cac_loai_van_ban_khac` | Các loại văn bản khác (`CAC_LOAI_VAN_BAN_KHAC`) | 2 |

Chỉ sao chép tệp **có chữ đọc được**: 53 PDF có lớp chữ, 210 `.doc`, 30 `.docx`, và 2 tệp `.txt` là bản
ghi thông tin (số ký hiệu, trích yếu, ngày ban hành, link) đi kèm văn bản cùng số hiệu. Không sao chép:
324 PDF scan (cần OCR), 1 PDF có lớp chữ rất ít, 30 tệp nén, 7 ảnh, 2 bảng tính, 54 bản ghi `.txt` không
có nội dung văn bản, 2 tệp `.doc` thực chất là HTML, 1 `.docx` không có chữ, 1 `.docx` trùng nội dung.
Lý do từng tệp ở `van-ban/_selection.json`. Tên tệp dạng `[mã]_tiêu_đề.đuôi`; số hiệu lấy từ `[mã]`
(`01_2012_TT-BCA` → `01/2012/TT-BCA`, `Ð` → `Đ`).

## Nạp vào ứng dụng

```powershell
$env:DATABASE_URL = '<chuỗi kết nối PostgreSQL>'
$env:EVIDENCE_DOCUMENT_STORE_ROOT = '<đường dẫn tuyệt đối kho tài liệu>'

python scripts/import_official_corpus.py                      # chạy thử: chỉ đọc và chuyển đổi, không ghi
python scripts/import_official_corpus.py --apply              # tạo danh mục, cấp quyền, nạp bản nháp
python scripts/import_official_corpus.py --apply --approve    # (chỉ dữ liệu thử) gửi duyệt và duyệt
```

`--apply` chỉ tạo bản nháp do tài khoản `curator` gửi; không tự duyệt. `--approve` duyệt bằng tài khoản
`reviewer` theo đúng quy tắc duyệt hiện hành và ghi vào nhật ký rằng đây là dữ liệu thử. Chạy lại không
nạp trùng (so mã băm PDF). Danh mục đã bị quản trị viên xóa không bị tạo lại.
