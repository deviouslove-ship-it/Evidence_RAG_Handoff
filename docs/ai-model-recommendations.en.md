**Language / Ngôn ngữ:** [Tiếng Việt](ai-model-recommendations.md) · English

English counterpart of `docs/ai-model-recommendations.md`. The Vietnamese file is the original.

# Recommended AI models, by configuration item

Updated 2026-11-06 (a note on the state of the source code, dated 2026-11-11, was added below). This is a reference report. **No model had been configured** in the app when the report was written. Model names and prices change quickly; confirm them again on the provider’s site before choosing. Local running speed is an estimate and has not been measured on the target machine (how to measure it is in section 5).

> **Current state of the source code (updated after the G1.0–G5 round of 2026-11-07 to 2026-11-09; see [implementation-status.md](implementation-status.md), [ADR-007](architecture-decisions/ADR-007-stage-policy-hybrid-auto.md), and [ADR-009](architecture-decisions/ADR-009-comprehensive-search-synthesis.md)):**
> - **The stages in the Model Registry are fully wired in code (`ACTIVE_STAGES` in `backend/app/model_registry/stages.py`):** `answer`, `summarize` (“Diễn giải AI” (AI interpretation), checked by code), `expand` (concept expansion), `relation` (a proposal for an effectivity (hiệu lực) relation), `label` (a proposal for a content label), `embedding` (building a vector through `storage/embeddings.py` and `storage/embedding_jobs.py`), and `rerank` (optional re-ranking through an LLM or `scripts/local_reranker_server.py`, off by default with `EVIDENCE_RERANK_DEFAULT=false`).
> - **The API-key store (`secret_store.py`):** besides the `env:TEN_BIEN` syntax (`env:` plus the variable name), the Admin Portal already accepts an API key typed in directly and stores it encrypted with Windows DPAPI (`secret:<tên>` (`secret:<name>`) under `EVIDENCE_SECRET_STORE_DIR`).
> - **Vector dimensions (`0012_comprehensive_search.sql`):** the `node_embeddings` table no longer fixes 768 dimensions. It supports a separate HNSW index per model and per dimension count in `embedding_indices` (a reference configuration that was tried used `qwen3-embedding:0.6b` at 1,024 dimensions through Ollama).
> - The hardware and model estimate tables in sections 1 through 7 below are kept as they were, as a reference for the state on 2026-11-06.

## 1. Which configuration items the app has

| # | Configuration item (where it is set) | Uses a model? | Status |
|---|---|---|---|
| 1 | Admin Portal → “Mô hình AI” (AI models) → mode **LOCAL**, stage `answer` | Yes | Usable |
| 2 | Admin Portal → “Mô hình AI” (AI models) → mode **API**, stage `answer` | Yes | Usable |
| 3 | OCR of a scanned page (`EVIDENCE_OCR_EXECUTABLE`, `EVIDENCE_OCR_LANGUAGES`) | Yes (Tesseract) | Usable; it has to be installed separately |
| 4 | Question analysis, search, the evidence (căn cứ) check, and effectivity (hiệu lực) | No | Handled by the app’s own code (rules + PostgreSQL) |
| 5 | An LLM stage `analyze`, plus `embedding`, `rerank`, and `verify` | Present in the design | **Not wired in code**; the Admin Portal does not offer a choice yet |

The `answer` stage currently does only one thing: it receives at most 8 evidence items (each evidence item is cut to 1,200 characters, about 3,000 to 4,000 tokens) and returns JSON `{"evidence_ids":[...]}` choosing at most 3 evidence items. The model does not write the answer and does not write a citation. A large model is therefore unnecessary. What is needed is an understanding of legal Vietnamese, compliance with the JSON format, and a response within 15 seconds (the setting `EVIDENCE_AI_TIMEOUT_SECONDS`, maximum 30).

## 2. Item 1: LOCAL, stage `answer`

This runs through Ollama (`ollama_local`), vLLM (`vllm_local`), or llama.cpp (`llama_cpp_local`). The endpoint has the form `http://127.0.0.1:<cổng>/v1` (`<cổng>` is the port).

| Machine tier | Minimum configuration | Suggested model | Download size* | Notes |
|---|---|---|---|---|
| A. An office machine, no discrete GPU | A CPU with 8 cores or more, 16 GB of RAM (32 GB recommended), an SSD | `gemma4:e2b` or `gemma4:e4b` | 4.6 to 7.5 GB (e2b); 6.6 to 9.5 GB (e4b) | For a trial only. Reading 4,000 tokens on a CPU can exceed 15 seconds (section 5) |
| B. A GPU with 8 to 12 GB of VRAM | An NVIDIA GPU of 8 GB or more, 16 GB of RAM | `gemma4:e4b` or `gemma4:12b` | 6.6 to 9.5 GB; 7.7 to 8.0 GB | The smallest configuration that should be used by someone trying the system |
| C. A GPU with 24 GB of VRAM | A 24 GB GPU (RTX 4090/3090 or equivalent), 32 GB of RAM | `gemma4:26b` (MoE, 3.8B active parameters) or `qwen3.6:27b` | 16 to 19 GB; 18 to 19 GB | A balance of quality and speed |
| D. A GPU of 32 GB or more, or 2 GPUs | 32 GB of VRAM, or 2×24 GB, and 64 GB of RAM | `gemma4:31b`, `qwen3.6:35b` (23 GB) | 19 to 20 GB; 23 GB | Use vLLM if many people ask at the same time |

\* The size of the model file in the Ollama library. Memory use while running is about 2 to 4 GB larger than the file, because of context memory. One GPU has to hold the model file plus this extra amount; otherwise Ollama moves part of the model to the CPU and it becomes markedly slower. Disk set aside for models: the sum of the files of the models that will be kept, plus 10 GB spare.

Reasons for the choice:

- **Gemma 4** (Google, Apache 2.0, according to [this comparison](https://codersera.com/blog/gemma-3-vs-qwen-3-in-depth-comparison-of-two-leading-open-source-llms/)): the [Ollama](https://ollama.com/library/gemma4) page lists an MMMLU score (multilingual) of 88.4% for 31B, 86.3% for 26B-A4B, 76.6% for E4B, and 67.4% for E2B. This is a general multilingual score, **not a score for Vietnamese alone**.
- **Qwen 3.6** ([Ollama](https://ollama.com/library/qwen3.6)): the 27B and 35B builds, with a 256K context. Many sources place the Qwen line among the leaders for Vietnamese support (for example [SiliconFlow](https://www.siliconflow.com/articles/en/best-open-source-LLM-for-Vietnamese)), but that source is a comparison written by a service provider, not an independent evaluation.
- Specialized Vietnamese models (Vistral, PhoGPT, SeaLLM, Sailor2) are not the default recommendation, because the standing of the 2026 builds cannot be verified and they do not have JSON support or long-context support of the same kind.

**Make the final choice by measuring on a real set of questions** (20 questions in Vietnamese, each with an evidence (căn cứ) answer chosen by the person who holds the business knowledge): compare the rate of choosing the correct evidence and the time taken. Do not choose from a general score table alone.

Suggested parameters in the Admin Portal: `temperature` from 0 to 0.2; `max_tokens` 512; turn on “Ép đầu ra JSON” (Force JSON output); reasoning level `none` if the server accepts this parameter. Ollama and vLLM can turn thinking mode off; if it cannot be turned off, raise `max_tokens` to 1,024 so the thinking portion does not cut the JSON short. The app strips a `<think>` block when the model emits one on its own.

## 3. Item 2: API, stage `answer`

Shared conditions for sending content outside the machine (every condition has to hold):

1. `AI_OPERATING_MODE=API` and `EVIDENCE_REMOTE_PROCESSING_ALLOWED=true` in the backend environment.
2. The host name is listed in `EVIDENCE_AI_ALLOWED_REMOTE_DOMAINS`.
3. The AI profile has data zone `public`, an HTTPS address, and a key of the form `env:TEN_BIEN` (the key lives in an environment variable of the backend process; it is not typed into the app).
4. The user has the permission `remote_ai_allowed` (Admin Portal → “Tài khoản” (Accounts)).
5. Every source category of the question has `remote_processing_allowed` turned on.

| Provider | Endpoint (Admin Portal) | Reference model | Domain that must be allowed | Configuration notes |
|---|---|---|---|---|
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-3.5-flash` (about $1.50 in / $9 out per million tokens); the Flash-Lite build is cheaper (about $0.30 / $2.50) | `generativelanguage.googleapis.com` | Reasoning level `low`, `max_tokens` 1,024 (thinking tokens count against the allowance). Take the exact ID with the “Kiểm tra kết nối” (Check connection) button |
| OpenAI | `https://api.openai.com/v1` | The GPT-5.5 family (the flagship is about $5 / $30); use the mini or nano build if one is available | `api.openai.com` | Choose the token-limit field `max_completion_tokens`; do not set `temperature`; reasoning level `low` |
| Anthropic Claude | Not used directly | Through an intermediary gateway that is compatible with OpenAI | The gateway’s domain | Claude’s own API does not follow the OpenAI protocol; the app blocks this connector |
| Groq, OpenRouter | `.../openai/v1`, `.../api/v1` | Depends on the account | The corresponding domain | The path is allowed, but it has not been tested against the real service |

Sources: [Gemini’s OpenAI-compatibility documentation](https://ai.google.dev/gemini-api/docs/openai), [Gemini 3.5](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.5), and [OpenAI GPT-5.5](https://developers.openai.com/api/docs/models/gpt-5.5). The prices are taken from third-party roundups and are only for estimating. Each question sends about 4,000 tokens in and under 100 tokens out, which is a few thousandths of a US dollar with a Flash-class model.

A sample Gemini profile: provider `openai_compatible`; zone `public`; key `env:GEMINI_API_KEY`; JSON on; reasoning level `low`; `max_tokens` 1,024. In the Admin Portal, choose the “API — Google Gemini” template at the top of the form to fill these fields in, then enter the model name.

## 4. Item 3: OCR of a scanned page

| Tool | Status | Machine configuration | Notes |
|---|---|---|---|
| **Tesseract 5 with `vie` + `eng`** | Wired in code | A CPU, 4 GB of RAM, no GPU required | A trial measurement of 1.3 to 1.7 seconds per A4 page (200 dpi) on a Ryzen 9 6900HX. It reads seals and document numbers poorly; the document number has to be taken from the file name |
| PaddleOCR (a Vietnamese model) | Not wired in code | A 4-core CPU, 8 GB of RAM; a GPU is optional | Usually more accurate than Tesseract on a skewed page or a page with many columns |
| A vision model (Gemma 4, Qwen3.6) | Not wired in code | As in section 2 | Gemma 4 has OmniDocBench results on the [Ollama page](https://ollama.com/library/gemma4) (31B: 0.131; E4B: 0.181; lower is better) |

OCR runs only while a document is being loaded, not while a user is asking a question, so a weak machine is still enough if a slow load is acceptable.

## 5. How to measure whether a Local model is fast enough

One evidence-selection (căn cứ) turn is about 4,000 input tokens and under 100 output tokens.

- Time ≈ 4,000 ÷ prompt-read speed (tokens/second) + 100 ÷ generation speed (tokens/second).
- It has to stay under 15 seconds. The prompt-read speed needs to be about 400 tokens/second or higher.
- Measure with `ollama run <mô hình> --verbose` (`<mô hình>` is the model name). Paste a prompt of about 12,000 Vietnamese characters, and read the `prompt eval rate` line and the `eval rate` line.
- A CPU usually reads a prompt at a few tens to a few hundred tokens per second, so tier A is at risk of going over the limit. When it does, the app skips the model for 60 seconds and still returns the evidence in search-rank order; it does not hang.

## 6. Item 5: stages not yet wired in code (the roadmap)

Configuring them now has no effect. They are written down so the right choice is ready when they are wired.

| Stage | Local | API | Local machine configuration | Notes |
|---|---|---|---|---|
| `embedding` (search by meaning) | `BAAI/bge-m3`; or [`Vietnamese_Embedding_v2`](https://huggingface.co/akitara/Vietnamese_Embedding_v2) (fine-tuned from BGE-M3 for Vietnamese) | The embedding API of Gemini or OpenAI | A CPU is acceptable; 4 GB of RAM; a GPU makes reloading the index faster | The vector column in the database is `vector(768)`. BGE-M3 outputs 1,024 dimensions (to the best of my knowledge; confirm this when wiring it), so a migration is needed, or a 768-dimension model has to be chosen |
| `rerank` (re-rank the candidates) | `BAAI/bge-reranker-v2-m3`; [ViRanker](https://arxiv.org/abs/2509.09131) (a cross-encoder for Vietnamese) | The provider’s rerank service | An 8-core CPU, 4 GB of RAM; a GPU if more than 50 candidates are re-ranked per question | Local Mode has to run on the local machine |
| `analyze` by an LLM (split out the facts, rewrite the sentence) | As in section 2 | As in section 3 | As in section 2 | It currently runs by rules, and does not use an LLM |
| `verify` (whether a claim is supported by evidence (căn cứ)) | A small multilingual entailment model | As in section 3 | A CPU is acceptable | Designed for P1. It needs Gold [Not implemented — see ADR-010] so it can be measured before it is turned on |

## 7. A suggested starting set

| Situation | LOCAL `answer` | API `answer` |
|---|---|---|
| A quick trial on the machine at hand | `gemma4:e4b` (measure the time first) | Gemini Flash-Lite or Flash |
| A LAN trial with 5 to 20 people | `gemma4:26b` on a 24 GB GPU | Gemini Flash |
| Real operation, with the data staying on the machine | `gemma4:31b` or `qwen3.6:35b` on vLLM | Not used |

Every profile should have one fallback profile in the same data zone (at most 1). After saving, press “Kiểm tra kết nối” (Check connection).
