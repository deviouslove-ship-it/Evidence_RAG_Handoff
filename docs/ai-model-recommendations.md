# Đề xuất mô hình AI theo từng mục cấu hình

Cập nhật 06/11/2026 (bổ sung ghi chú trạng thái mã nguồn 11/11/2026 bên dưới). Đây là báo cáo tham khảo, **chưa cấu hình mô hình nào** trong app tại thời điểm lập báo cáo. Tên mô hình và giá
đổi nhanh; xác nhận lại trên trang nhà cung cấp trước khi chọn. Tốc độ chạy Local là ước tính, chưa đo trên
máy đích (cách đo ở mục 5).

> **Trạng thái mã nguồn hiện hành (cập nhật sau đợt G1.0–G5 ngày 07–09/11/2026, xem [implementation-status.md](implementation-status.md), [ADR-007](architecture-decisions/ADR-007-stage-policy-hybrid-auto.md), [ADR-009](architecture-decisions/ADR-009-comprehensive-search-synthesis.md)):**
> - **Các giai đoạn trong Model Registry đã nối mã đầy đủ (`ACTIVE_STAGES` trong `backend/app/model_registry/stages.py`):** `answer`, `summarize` (Diễn giải AI có kiểm chứng bằng mã), `expand` (mở rộng khái niệm), `relation` (đề xuất quan hệ hiệu lực), `label` (đề xuất nhãn nội dung), `embedding` (tạo vector qua `storage/embeddings.py` và `storage/embedding_jobs.py`), `rerank` (xếp hạng lại tùy chọn qua LLM hoặc `scripts/local_reranker_server.py`, mặc định tắt `EVIDENCE_RERANK_DEFAULT=false`).
> - **Kho khóa API (`secret_store.py`):** ngoài cú pháp `env:TEN_BIEN`, Admin Portal đã hỗ trợ nhập trực tiếp API Key và lưu mã hóa bằng Windows DPAPI (`secret:<tên>` trong `EVIDENCE_SECRET_STORE_DIR`).
> - **Chiều vector (`0012_comprehensive_search.sql`):** bảng `node_embeddings` đã bỏ cố định 768 chiều, hỗ trợ chỉ mục HNSW riêng theo từng model và số chiều trong `embedding_indices` (cấu hình tham chiếu đã thử dùng `qwen3-embedding:0.6b` 1024 chiều qua Ollama).
> - Các bảng ước tính phần cứng và mô hình từ mục 1 đến mục 7 bên dưới được giữ nguyên làm tài liệu tham khảo thời điểm 06/11/2026.

## 1. App có những mục cấu hình nào

| # | Mục cấu hình (nơi đặt) | Dùng mô hình? | Trạng thái |
|---|---|---|---|
| 1 | Admin Portal → Mô hình AI → chế độ **LOCAL**, giai đoạn `answer` | Có | Dùng được |
| 2 | Admin Portal → Mô hình AI → chế độ **API**, giai đoạn `answer` | Có | Dùng được |
| 3 | OCR trang scan (`EVIDENCE_OCR_EXECUTABLE`, `EVIDENCE_OCR_LANGUAGES`) | Có (Tesseract) | Dùng được, cần cài ngoài |
| 4 | Phân tích câu hỏi, tìm kiếm, kiểm tra căn cứ, hiệu lực | Không | Do mã của app xử lý (quy tắc + PostgreSQL) |
| 5 | Giai đoạn `analyze` bằng LLM, `embedding`, `rerank`, `verify` | Có trong thiết kế | **Chưa nối mã**, Admin Portal chưa cho chọn |

Giai đoạn `answer` hiện tại chỉ làm một việc: nhận tối đa 8 căn cứ (mỗi căn cứ cắt 1.200 ký tự, khoảng 3.000 đến
4.000 token) và trả JSON `{"evidence_ids":[...]}` chọn tối đa 3 căn cứ. Mô hình không viết câu trả lời, không
viết trích dẫn. Vì vậy không cần mô hình lớn; cần hiểu tiếng Việt pháp lý, tuân thủ định dạng JSON và phản hồi
trong 15 giây (cấu hình `EVIDENCE_AI_TIMEOUT_SECONDS`, tối đa 30).

## 2. Mục 1: LOCAL, giai đoạn `answer`

Chạy qua Ollama (`ollama_local`), vLLM (`vllm_local`) hoặc llama.cpp (`llama_cpp_local`). Endpoint dạng
`http://127.0.0.1:<cổng>/v1`.

| Bậc máy | Cấu hình tối thiểu | Mô hình đề xuất | Dung lượng tải về* | Ghi chú |
|---|---|---|---|---|
| A. Máy văn phòng, không GPU rời | CPU 8 nhân trở lên, RAM 16 GB (khuyến nghị 32 GB), SSD | `gemma4:e2b` hoặc `gemma4:e4b` | 4,6 đến 7,5 GB (e2b); 6,6 đến 9,5 GB (e4b) | Chỉ để thử. Đọc 4.000 token trên CPU có thể vượt 15 giây (mục 5) |
| B. GPU 8 đến 12 GB VRAM | GPU NVIDIA 8 GB trở lên, RAM 16 GB | `gemma4:e4b` hoặc `gemma4:12b` | 6,6 đến 9,5 GB; 7,7 đến 8,0 GB | Cấu hình nhỏ nhất nên dùng cho người thử |
| C. GPU 24 GB VRAM | GPU 24 GB (RTX 4090/3090 hoặc tương đương), RAM 32 GB | `gemma4:26b` (MoE, 3,8B tham số hoạt động) hoặc `qwen3.6:27b` | 16 đến 19 GB; 18 đến 19 GB | Cân bằng chất lượng và tốc độ |
| D. GPU 32 GB trở lên hoặc 2 GPU | 32 GB VRAM hoặc 2×24 GB, RAM 64 GB | `gemma4:31b`, `qwen3.6:35b` (23 GB) | 19 đến 20 GB; 23 GB | Dùng vLLM nếu nhiều người hỏi đồng thời |

\* Kích thước tệp mô hình trên thư viện Ollama. Dung lượng bộ nhớ khi chạy lớn hơn tệp khoảng 2 đến 4 GB do
bộ nhớ ngữ cảnh. Một GPU phải chứa được tệp mô hình cộng phần này, nếu không Ollama chuyển một phần sang CPU và
chậm đi rõ rệt. Ổ đĩa dành cho mô hình: bằng tổng tệp các mô hình định giữ, cộng 10 GB dư.

Lý do chọn:

- **Gemma 4** (Google, Apache 2.0 theo [bài so sánh](https://codersera.com/blog/gemma-3-vs-qwen-3-in-depth-comparison-of-two-leading-open-source-llms/)): trang
  [Ollama](https://ollama.com/library/gemma4) ghi điểm MMMLU (đa ngôn ngữ) 88,4% cho 31B, 86,3% cho 26B-A4B,
  76,6% cho E4B, 67,4% cho E2B. Đây là điểm đa ngôn ngữ chung, **không phải điểm tiếng Việt riêng**.
- **Qwen 3.6** ([Ollama](https://ollama.com/library/qwen3.6)): bản 27B và 35B, ngữ cảnh 256K. Dòng Qwen được
  nhiều nguồn xếp trong nhóm đầu về hỗ trợ tiếng Việt (ví dụ [SiliconFlow](https://www.siliconflow.com/articles/en/best-open-source-LLM-for-Vietnamese)), nhưng nguồn
  này là bài so sánh của một nhà cung cấp dịch vụ, không phải đánh giá độc lập.
- Các mô hình tiếng Việt chuyên biệt (Vistral, PhoGPT, SeaLLM, Sailor2) không được đề xuất mặc định vì không
  kiểm chứng được tình trạng bản 2026 và không có hỗ trợ JSON/ngữ cảnh dài tương đương.

**Chọn cuối cùng bằng phép đo trên bộ câu hỏi thật** (20 câu tiếng Việt, mỗi câu có đáp án căn cứ do người nắm
nghiệp vụ chọn): so tỷ lệ chọn đúng căn cứ và thời gian. Không chọn chỉ bằng bảng điểm chung.

Tham số đề xuất trong Admin Portal: `temperature` 0 đến 0,2; `max_tokens` 512; bật "Ép đầu ra JSON"; mức suy
luận `none` nếu máy chủ nhận tham số này. Ollama và vLLM cho phép tắt chế độ suy nghĩ; nếu không tắt được, tăng
`max_tokens` lên 1.024 để phần suy nghĩ không làm cụt JSON. App có bóc tách khối `<think>` khi mô hình tự sinh.

## 3. Mục 2: API, giai đoạn `answer`

Điều kiện chung để gửi nội dung ra ngoài (mọi điều kiện phải đúng):

1. `AI_OPERATING_MODE=API` và `EVIDENCE_REMOTE_PROCESSING_ALLOWED=true` trong môi trường backend.
2. Tên máy chủ nằm trong `EVIDENCE_AI_ALLOWED_REMOTE_DOMAINS`.
3. Hồ sơ AI có vùng dữ liệu `public`, địa chỉ HTTPS, khóa dạng `env:TEN_BIEN` (khóa nằm trong biến môi trường của
   tiến trình backend, không nhập vào app).
4. Người dùng có quyền `remote_ai_allowed` (Admin Portal → Tài khoản).
5. Mọi danh mục nguồn của câu hỏi có `remote_processing_allowed` bật.

| Nhà cung cấp | Endpoint (Admin Portal) | Mô hình tham khảo | Tên miền cần cho phép | Lưu ý cấu hình |
|---|---|---|---|---|
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-3.5-flash` (khoảng $1,50 vào / $9 ra mỗi triệu token); bản Flash-Lite rẻ hơn (khoảng $0,30 / $2,50) | `generativelanguage.googleapis.com` | Mức suy luận `low`, `max_tokens` 1.024 (token suy nghĩ tính vào hạn mức). Lấy đúng ID bằng nút "Kiểm tra kết nối" |
| OpenAI | `https://api.openai.com/v1` | Họ GPT-5.5 (flagship khoảng $5 / $30); dùng bản mini/nano nếu có | `api.openai.com` | Chọn trường giới hạn token `max_completion_tokens`; không đặt `temperature`; mức suy luận `low` |
| Anthropic Claude | Không dùng trực tiếp | Qua cổng trung gian tương thích OpenAI | Tên miền của cổng | API gốc của Claude không theo giao thức OpenAI; app chặn bộ kết nối này |
| Groq, OpenRouter | `.../openai/v1`, `.../api/v1` | Tùy tài khoản | Tên miền tương ứng | Đường dẫn được cho phép nhưng chưa kiểm thử với dịch vụ thật |

Nguồn: [tài liệu tương thích OpenAI của Gemini](https://ai.google.dev/gemini-api/docs/openai),
[Gemini 3.5](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.5),
[OpenAI GPT-5.5](https://developers.openai.com/api/docs/models/gpt-5.5). Giá lấy từ các bài tổng hợp của bên
thứ ba, chỉ để ước lượng. Mỗi câu hỏi gửi khoảng 4.000 token vào và dưới 100 token ra, tức vài phần nghìn USD
với mô hình hạng Flash.

Hồ sơ Gemini mẫu: nhà cung cấp `openai_compatible`; vùng `public`; khóa `env:GEMINI_API_KEY`; JSON bật; mức suy
luận `low`; `max_tokens` 1.024. Trong Admin Portal chọn mẫu "API — Google Gemini" ở đầu biểu mẫu để điền sẵn
các ô này, rồi nhập tên mô hình.

## 4. Mục 3: OCR trang scan

| Công cụ | Trạng thái | Cấu hình máy | Ghi chú |
|---|---|---|---|
| **Tesseract 5 với `vie` + `eng`** | Đã nối mã | CPU, RAM 4 GB, không cần GPU | Đo thử 1,3 đến 1,7 giây/trang A4 (200 dpi) trên Ryzen 9 6900HX. Đọc con dấu và số hiệu kém; số hiệu phải lấy từ tên tệp |
| PaddleOCR (mô hình tiếng Việt) | Chưa nối mã | CPU 4 nhân, RAM 8 GB; GPU tùy chọn | Thường chính xác hơn Tesseract trên trang nghiêng, nhiều cột |
| Mô hình thị giác (Gemma 4, Qwen3.6) | Chưa nối mã | Như mục 2 | Gemma 4 có kết quả OmniDocBench trên [trang Ollama](https://ollama.com/library/gemma4) (31B: 0,131; E4B: 0,181; càng thấp càng tốt) |

OCR chỉ chạy lúc nạp tài liệu, không chạy lúc người dùng hỏi, nên máy yếu vẫn đủ nếu chấp nhận nạp chậm.

## 5. Cách đo mô hình Local có đủ nhanh không

Một lượt chọn căn cứ gồm khoảng 4.000 token đầu vào và dưới 100 token đầu ra.

- Thời gian ≈ 4.000 ÷ tốc độ đọc prompt (token/giây) + 100 ÷ tốc độ sinh (token/giây).
- Phải dưới 15 giây. Cần tốc độ đọc prompt từ khoảng 400 token/giây trở lên.
- Đo bằng `ollama run <mô hình> --verbose`, dán một prompt khoảng 12.000 ký tự tiếng Việt, đọc dòng
  `prompt eval rate` và `eval rate`.
- CPU thường đọc prompt ở mức vài chục đến vài trăm token/giây, nên bậc A có nguy cơ vượt giới hạn. Khi vượt,
  app bỏ qua mô hình trong 60 giây và vẫn trả căn cứ theo xếp hạng tìm kiếm, không treo.

## 6. Mục 5: các giai đoạn chưa nối mã (lộ trình)

Chưa có tác dụng nếu cấu hình bây giờ. Ghi sẵn để chọn đúng khi nối.

| Giai đoạn | Local | API | Cấu hình máy Local | Ghi chú |
|---|---|---|---|---|
| `embedding` (tìm theo ngữ nghĩa) | `BAAI/bge-m3`; hoặc [`Vietnamese_Embedding_v2`](https://huggingface.co/akitara/Vietnamese_Embedding_v2) (tinh chỉnh từ BGE-M3 cho tiếng Việt) | API embedding của Gemini hoặc OpenAI | CPU được; RAM 4 GB; GPU làm nhanh việc nạp lại chỉ mục | Cột vector trong DB là `vector(768)`. BGE-M3 xuất 1.024 chiều (theo hiểu biết của tôi, cần xác nhận khi nối), nên cần migration hoặc chọn mô hình 768 chiều |
| `rerank` (xếp lại ứng viên) | `BAAI/bge-reranker-v2-m3`; [ViRanker](https://arxiv.org/abs/2509.09131) (cross-encoder cho tiếng Việt) | Dịch vụ rerank của nhà cung cấp | CPU 8 nhân, RAM 4 GB; GPU nếu xếp lại hơn 50 ứng viên mỗi câu | Local Mode bắt buộc chạy cục bộ |
| `analyze` bằng LLM (tách dữ kiện, viết lại câu) | Như mục 2 | Như mục 3 | Như mục 2 | Hiện chạy bằng quy tắc, không dùng LLM |
| `verify` (claim có được căn cứ hỗ trợ) | Mô hình entailment đa ngôn ngữ cỡ nhỏ | Như mục 3 | CPU được | Thiết kế để P1, cần Gold [Không triển khai – xem ADR-010] để đo trước khi bật |

## 7. Bộ cấu hình khởi đầu đề xuất

| Tình huống | LOCAL `answer` | API `answer` |
|---|---|---|
| Thử nhanh trên máy hiện tại | `gemma4:e4b` (đo thời gian trước) | Gemini Flash-Lite hoặc Flash |
| Chạy thử LAN với 5 đến 20 người | `gemma4:26b` trên GPU 24 GB | Gemini Flash |
| Vận hành thật, dữ liệu không rời máy | `gemma4:31b` hoặc `qwen3.6:35b` trên vLLM | Không dùng |

Mọi hồ sơ nên đặt một hồ sơ dự phòng cùng vùng dữ liệu (tối đa 1) và bấm "Kiểm tra kết nối" sau khi lưu.
