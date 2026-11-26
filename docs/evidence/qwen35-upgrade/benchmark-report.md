# Báo cáo kiểm chứng Gate A1: `qwen3.5:4b` trên Ollama 0.40.15

Ngày kiểm chứng: 16/11/2026

## 1. Môi trường kiểm chứng và baseline

- **Ollama runtime**: `0.40.15` (cùng bản đóng trong gói r4; hỗ trợ kiến trúc `qwen35` và vision projector, không cần thay runtime).
- **Kho model kiểm thử**: thư mục `models/ollama` trong dự án (tách biệt với `<ProgramsRoot>` mặc định).
- **Baseline DB (`evidence_rerank_eval`)**:
  - `documents`: `105`
  - `document_versions`: `105`
  - `document_nodes`: `7447`
  - `node_embeddings`: `7447`
  - `embedding_indices`: `1` (`qwen3-embedding:0.6b`, 1.024 chiều)
  - `source_pages`: `1566`
  - `schema_migrations`: `0015_ocr_page_review.sql`
  - Đã sao lưu đầy đủ và kiểm chứng phục hồi sang DB thử nghiệm `evidence_qwen35_test` (`105` văn bản, `7447` vector).

## 2. Thông tin weights và manifest

| Model | Manifest digest | Tổng dung lượng blobs | Projector / Vision layer | Kiến trúc / Quantization |
|---|---|---|---|---|
| `qwen3:1.7b` | `sha256:0f45bae8cd2fec097cf09b400b078cf42388a1f5702f4058d2d6d641a09db46d` | 1.359.294.303 bytes | Không (`has_vision_layer=false`) | `qwen3` (2.0B, `Q4_K_M`) |
| `qwen3.5:4b` | `sha256:e0b8c85c75aad2573ff49bec177ebb1013772fba665a53d64c04266439a2222d` | 3.324.175.492 bytes | Có (`application/vnd.ollama.image.projector`, `sha256:e56a899b1540860385465756dd308c84417410b94dbc1c380adffd20a921ca60`, 675.569.120 bytes) + weights (`sha256:a9d0a3e1d8c91732a3812becd31f8d4a8ff57414903f226306069f0437e2ac50`, 2.648.593.216 bytes) | `qwen35` (4.2B, `Q4_K_M`, capabilities: `completion`, `vision`, `tools`, `thinking`) |

## 3. Kết quả đo đồng điều kiện (`scripts/benchmark_qwen35.py`)

| Hạng mục đo | `qwen3:1.7b` | `qwen3.5:4b` | Nhận xét |
|---|---|---|---|
| Text JSON cold start (`think=false`) | 7.641 ms | 4.938 ms | Hợp lệ JSON, không sinh reasoning thừa |
| Text JSON warm median (2 lượt) | 320,0 ms (312 / 328 ms) | 812,5 ms (812 / 813 ms) | Đạt ngưỡng timeout 30s của stage text |
| Vision OCR PNG tổng hợp (`think=false`, schema) | Không hỗ trợ | 20.125 ms (177 tokens) | Đọc đúng số hiệu `17/2026` và ngày `16/11/2026` |
| Embedding `qwen3-embedding:0.6b` | — | — | Hoạt động bình thường, trả về đúng 1.024 chiều |

**Kết luận Gate A1:** Đạt. Runtime Ollama `0.40.15` + `qwen3.5:4b` chạy được đầy đủ text, JSON schema, `think=false`, vision OCR và giữ nguyên `qwen3-embedding:0.6b` 1.024 chiều.

## Đối chiếu sau rà soát 17/11/2026

Giữ nguyên các số đo ngày 16/11 ở trên. SHA file manifest `e0b8…` khác digest model `d8b0…` do native `/api/tags` trả về: manifest trong store chứa các layer manifest lồng nhau. Runtime đã được sửa để lưu digest từ API native, đồng thời giữ fingerprint cấu hình; xem [báo cáo rà soát](REVIEW_FIXES_2026-11-17.md). Nguồn định dạng metadata: [Ollama List models](https://docs.ollama.com/api/tags).
