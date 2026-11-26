**Language / Ngôn ngữ:** [Tiếng Việt](README.md) · English

English counterpart of `test-data/README.md`. The Vietnamese file is the original.

# Trial data

## `van-ban/`

Official administrative documents (văn bản) used to try the application, copied from the source directory supplied by the owner. Each subdirectory is one category (danh mục). Each file sits in the correct root folder of that category. The administrative documents are public on the Internet, so the categories are created with `remote_processing_allowed` turned on (turn it off with `--no-remote` when loading).

| Directory | Category (danh mục) (code) | Files |
|---|---|---|
| `Luat` | Law (Luật) (`LUAT`) | 2 |
| `Nghi_dinh` | Decree (Nghị định) (`NGHI_DINH`) | 18 |
| `Quyet_dinh` | Decision (Quyết định) (`QUYET_DINH`) | 70 |
| `Thong_tu` | Circular (Thông tư) (`THONG_TU`) | 196 |
| `Thong_tu_lien_tich` | Joint circular (Thông tư liên tịch) (`THONG_TU_LIEN_TICH`) | 5 |
| `Chi_thi` | Directive (Chỉ thị) (`CHI_THI`) | 2 |
| `Cac_loai_van_ban_khac` | Other types of administrative documents (Các loại văn bản khác) (`CAC_LOAI_VAN_BAN_KHAC`) | 2 |

Only files **with readable text** were copied: 53 PDFs with a text layer, 210 `.doc`, 30 `.docx`, and 2 `.txt` files that are information records (reference number, abstract, date of issue, link) accompanying the administrative document with the same document number. Not copied: 324 scanned PDFs (OCR required), 1 PDF with very little text in its text layer, 30 archives, 7 images, 2 spreadsheets, 54 `.txt` records with no administrative-document content, 2 `.doc` files that are actually HTML, 1 `.docx` with no text, and 1 `.docx` with duplicate content. The reason for each file is in `van-ban/_selection.json`. File names have the form `[mã]_tiêu_đề.đuôi` (`[code]_title.extension`). The document number is taken from `[mã]` (`[code]`) (`01_2012_TT-BCA` → `01/2012/TT-BCA`, `Ð` → `Đ`).

## Load into the application

```powershell
$env:DATABASE_URL = '<chuỗi kết nối PostgreSQL>'
$env:EVIDENCE_DOCUMENT_STORE_ROOT = '<đường dẫn tuyệt đối kho tài liệu>'

python scripts/import_official_corpus.py                      # chạy thử: chỉ đọc và chuyển đổi, không ghi
python scripts/import_official_corpus.py --apply              # tạo danh mục, cấp quyền, nạp bản nháp
python scripts/import_official_corpus.py --apply --approve    # (chỉ dữ liệu thử) gửi duyệt và duyệt
```

`--apply` only creates a draft submitted by the `curator` account. It does not approve on its own. `--approve` approves with the `reviewer` account under the current approval rules and writes in the log that this is trial data. Running it again does not import duplicates (PDF hashes are compared). A category that an administrator has deleted is not created again.
