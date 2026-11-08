# Kiểm thử bao phủ (D15, G5)

Không phải bộ Gold QA. Mỗi chủ đề có vài cách hỏi và danh sách căn cứ **bắt buộc tìm thấy**
(số hiệu + Điều), lấy từ `test-data/cau-hoi-kiem-thu-vong-1.md` và bộ `test-data/van-ban`.
Căn cứ do AI soạn từ chữ của tệp; cần cán bộ chuyên môn xác nhận trước khi dùng làm chuẩn.

| Tệp | Nội dung |
|---|---|
| `topics.json` | 17 chủ đề, 50 cách hỏi, 74 cặp (câu hỏi, căn cứ bắt buộc). 8 chủ đề đầu (24 câu, `set` vắng = `v1`) là bộ G5 gốc; 9 chủ đề `"set": "v2"` (26 câu) soạn bổ sung 07/11/2026 từ chữ của 100 văn bản thử, trước khi chạy bất kỳ lần tìm nào trên chúng. Căn cứ do tác tử soạn, chưa được cán bộ xác nhận |
| `run_coverage.py` | Gọi API tìm toàn diện thật; đo tỷ lệ tìm thấy với đủ kênh và từng kênh riêng; đọc toàn bộ kết quả qua phân trang; xuất báo cáo JSON |
| `g3_relations_reference.json` | 31 quan hệ cấp Điều/Khoản/Điểm đối chiếu nguyên văn (người lập: tác tử, chưa được cán bộ xác nhận) |
| `measure_g3_relations.py` | Độ chính xác, độ phủ của bộ đọc quan hệ cấp Điều/Khoản |

```powershell
$env:EVIDENCE_EVAL_USERNAME = '<tài khoản USER>'; $env:EVIDENCE_EVAL_PASSWORD = '<mật khẩu>'
python evaluation/coverage/run_coverage.py --base-url http://127.0.0.1:8000 --out coverage.json
$env:DATABASE_URL = '<chuỗi kết nối>'; python evaluation/coverage/measure_g3_relations.py --out g3.json
```

Đổi model embedding rồi đo lại: `python scripts/build_embeddings.py --rebuild` (chỉ mục mới thay
chỉ mục cũ khi đã đủ vector), sau đó chạy lại `run_coverage.py` và so hai báo cáo.

**Mặc định của "Tìm toàn diện" là RRF thuần, không rerank** (`EVIDENCE_RERANK_DEFAULT=false`). Hai phương án
rerank giữ nguyên và dùng khi cần: LLM local theo lô (giai đoạn `rerank` trong Model Registry,
`EVIDENCE_RERANK_BACKEND=llm`) hoặc Qwen3-Reranker-0.6B trên CPU
(`EVIDENCE_RERANK_BACKEND=cross_encoder`). Một yêu cầu có thể gửi `"rerank": true` để bật cho riêng nó;
đặt `EVIDENCE_RERANK_DEFAULT=true` để bật cho mọi yêu cầu không nêu rõ. Ngưỡng tương đồng của kênh theo
nghĩa mặc định 0,8 (`EVIDENCE_SEMANTIC_RELATIVE_THRESHOLD`); 0,6 chỉ dùng khi thử nghiệm.

## So sánh reranker (thử nghiệm)

| Tệp | Nội dung |
|---|---|
| `select_subset.py` | Chọn tập con cố định N tệp (mặc định 100): mọi tệp thuộc số hiệu có trong `topics.json`, phần còn lại theo SHA-256 của tên tệp; ghi `subset-manifest.json` |
| `run_rerank_benchmark.py` | Một phương án xếp hạng: Recall@10/20/50, MRR@10, NDCG@10, P@10, thời gian, RAM (API, Ollama, dịch vụ rerank) |
| `compare_rerank.py` | Gộp báo cáo RRF thuần, LLM hiện tại, Qwen3; bảng cùng nhóm ứng viên, khoảng tin cậy bootstrap, AUC điểm rerank, thí nghiệm bổ sung |
| `summarize_rrf.py` | Tóm tắt một lần chạy RRF thuần: bộ gốc, bộ bổ sung, từng chủ đề, căn cứ ngoài 10 kết quả đầu |
| `compare_reproduction.py` | So hai lần chạy cùng bộ câu hỏi theo (số hiệu, nhãn khoản): nhóm ứng viên, vị trí, hạng căn cứ; dùng để kiểm tái lập sau khi dựng lại hoặc khôi phục CSDL |
| `../../scripts/verify_db_restore.py` | So CSDL gốc với bản khôi phục từ `pg_dump`: số dòng, tổng kiểm văn bản và vector, chỉ mục, truy vấn HNSW |
| `diagnose_missing.py` | Một căn cứ vắng mặt: lỗi truy xuất ứng viên hay lỗi xếp hạng (vị trí vector thật, ngưỡng kênh theo nghĩa, vị trí trong từng kênh) |

Dịch vụ Qwen3-Reranker (venv riêng có `torch` bản CPU, `transformers`, `psutil`; venv của ứng dụng không cần):

```powershell
python scripts/local_reranker_server.py --model-dir <thư mục model Qwen3-Reranker-0.6B> --threads 8
$env:EVIDENCE_RERANK_BACKEND = 'cross_encoder'                 # mặc định: llm
$env:EVIDENCE_CROSS_ENCODER_URL = 'http://127.0.0.1:8791'      # chỉ nhận địa chỉ loopback
# tùy chọn: EVIDENCE_CROSS_ENCODER_TIMEOUT_SECONDS (120), EVIDENCE_CROSS_ENCODER_INSTRUCTION
```

Mỗi phương án chạy riêng với một API khởi động theo cấu hình tương ứng (RRF thuần: `--rerank off`):

```powershell
python evaluation/coverage/run_rerank_benchmark.py --variant rrf --rerank off --base-url <api> `
  --pid-file api=<tệp pid> --out bench-rrf.json
python evaluation/coverage/compare_rerank.py --rrf bench-rrf.json --llm bench-llm.json --ce bench-ce.json `
  --out-json compare.json --out-md compare.md
```

Kết quả lần chạy 07/11/2026 (100 tệp): `docs/evidence/2026-11-07-g5-rerank/REPORT.md`.
